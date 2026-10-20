"""Recorder backfills are explicit, bounded, lazy and quality checked."""

import asyncio
from contextlib import aclosing
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from custom_components.energy_copilot.const import DEFAULT_ENTITIES, HISTORY_ROLES
from custom_components.energy_copilot.history import (
    HistoryReadError,
    RecorderHistoryReader,
)
from custom_components.energy_copilot.recorder_reconstruction import RecordingRun

from .conftest import NOW, make_state


@pytest.fixture
def mock_recorder_before_hass(recorder_db_url):
    """Configure the real Recorder test database before HA initialization."""


@pytest.fixture
def fake_recorder(hass, freezer):
    freezer.move_to(NOW)
    hass.config.components.add("recorder")
    instance = SimpleNamespace(keep_days=10)
    instance.async_add_executor_job = AsyncMock(side_effect=lambda job: job())
    with (
        patch("homeassistant.components.recorder.get_instance", return_value=instance),
        patch(
            "homeassistant.components.recorder.history.get_significant_states",
            return_value={},
        ) as query,
        patch(
            "custom_components.energy_copilot.history.RecorderHistoryReader._read_recording_context",
            autospec=True,
            side_effect=lambda reader, rows, start, end: (
                rows,
                (RecordingRun(start, end),),
                (),
            ),
        ) as context,
    ):
        instance.recording_context = context
        yield query, instance


def valid_rows(start, minutes=15):
    return {
        DEFAULT_ENTITIES[role]: [
            make_state(role, at=start + timedelta(minutes=n)) for n in range(minutes)
        ]
        for role in HISTORY_ROLES
    }


async def test_lazy_multi_day_reads_in_bounded_chunks(hass, fake_recorder):
    query, instance = fake_recorder
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    start = NOW - timedelta(days=3, minutes=15)
    iterator = reader.async_iter_slots(start, NOW)
    assert not query.called
    async with aclosing(iterator):
        batches = []
        async for batch in iterator:
            batches.append((batch[0].start, batch[-1].end, len(batch)))
    assert batches == [
        (start, start + timedelta(days=1), 96),
        (start + timedelta(days=1), start + timedelta(days=2), 96),
        (start + timedelta(days=2), start + timedelta(days=3), 96),
        (start + timedelta(days=3), NOW, 1),
    ]
    assert query.call_count == 4
    assert instance.async_add_executor_job.await_count == 4
    for call in query.call_args_list:
        assert call.args[2] - call.args[1] <= timedelta(days=1)
        assert call.kwargs == {
            "entity_ids": [DEFAULT_ENTITIES[r] for r in HISTORY_ROLES],
            "include_start_time_state": False,
            "significant_changes_only": False,
            "minimal_response": False,
            "no_attributes": False,
        }
    summary = reader.last_backfill_summary
    assert summary["status"] == "completed"
    assert summary["requested_slots"] == 289
    assert summary["returned_slots"] == 289
    assert summary["valid_slots"] == 0
    assert summary["coverage_fraction"] == 0
    assert summary["configured_retention_days"] == 10
    assert summary["observed_first"] is None
    assert reader.last_read_summary is None


async def test_missing_retention_and_quality_are_not_zero(hass, fake_recorder):
    query, instance = fake_recorder
    start = NOW - timedelta(minutes=30)
    rows = valid_rows(start)
    # One source vanishes and the home's template continues reporting a number.
    rows[DEFAULT_ENTITIES["grid"]][5] = make_state(
        "grid", "unavailable", at=start + timedelta(minutes=5)
    )
    query.return_value = rows
    instance.recording_context.side_effect = lambda reader, rows, start, end: (
        rows,
        (RecordingRun(start, start + timedelta(minutes=15)),),
        (),
    )
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    slots = await reader.async_read_window(start, NOW)
    assert len(slots) == 2
    assert slots[0].home_kwh is None
    assert "invalid_input" in {i.code for i in slots[0].issues}
    assert slots[1].home_kwh is None
    assert "historical_quality_unverifiable" in {i.code for i in slots[1].issues}
    summary = reader.last_read_summary
    assert (
        summary["configured_retention_days"] == 10
    )  # Does not imply ten days of rows.
    assert summary["observed_first"] == start.isoformat()
    assert summary["observed_last"] == (start + timedelta(minutes=14)).isoformat()
    assert summary["valid_slots"] == 0
    assert "sensor.sun12k" not in str(summary)


async def test_partial_coverage_and_no_future_sample_leak(hass, fake_recorder):
    query, instance = fake_recorder
    start = NOW - timedelta(minutes=30)
    rows = valid_rows(start, minutes=16)
    # Later data is never backfilled into an earlier missing interval.
    for role in HISTORY_ROLES:
        rows[DEFAULT_ENTITIES[role]].append(
            make_state(role, at=NOW + timedelta(minutes=1))
        )
    query.return_value = rows
    instance.recording_context.side_effect = lambda reader, rows, start, end: (
        rows,
        (RecordingRun(start, start + timedelta(minutes=15)),),
        (),
    )
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    slots = await reader.async_read_window(start, NOW)
    assert slots[0].home_kwh == pytest.approx(5.234 / 4)
    assert slots[1].home_kwh is None
    assert reader.last_read_summary["coverage_fraction"] == 0.5
    assert (
        reader.last_read_summary["observed_last"]
        == (start + timedelta(minutes=15)).isoformat()
    )


async def test_early_stop_does_not_prefetch_and_recent_summary_is_separate(
    hass, fake_recorder
):
    query, _ = fake_recorder
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    async with aclosing(
        reader.async_iter_slots(NOW - timedelta(days=90), NOW)
    ) as batches:
        batch = await anext(batches)
        assert len(batch) == 96
        assert query.call_count == 1
    assert reader.last_backfill_summary["status"] == "incomplete"
    assert reader.last_backfill_summary["chunks_read"] == 1
    requested_start = reader.last_backfill_summary["requested_start"]
    await reader.async_read_window(NOW - timedelta(days=1), NOW)
    assert reader.last_backfill_summary["requested_start"] == requested_start
    assert reader.last_backfill_summary["chunks_read"] == 1
    assert reader.last_read_summary["status"] == "completed"


@pytest.mark.parametrize(
    "start,end,pattern",
    [
        (NOW - timedelta(days=367), NOW, "history_range_out_of_bounds"),
        (NOW, NOW, "history_range_out_of_bounds"),
        (NOW, NOW + timedelta(minutes=15), "history_future_range"),
        (NOW - timedelta(minutes=1), NOW, "history_quarter_hour_required"),
        (NOW.replace(tzinfo=None) - timedelta(days=1), NOW, "timezone_required"),
    ],
)
async def test_invalid_ranges_never_query(hass, fake_recorder, start, end, pattern):
    query, _ = fake_recorder
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    with pytest.raises(ValueError, match=pattern):
        await anext(reader.async_iter_slots(start, end))
    assert not query.called


async def test_single_read_is_bounded_even_when_backfill_supports_longer(
    hass, fake_recorder
):
    query, _ = fake_recorder
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    with pytest.raises(ValueError, match="history_range_out_of_bounds"):
        await reader.async_read_window(NOW - timedelta(days=2), NOW)
    assert not query.called


async def test_close_between_chunks_prevents_queries(hass, fake_recorder):
    query, _ = fake_recorder
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    async with aclosing(
        reader.async_iter_slots(NOW - timedelta(days=3), NOW)
    ) as batches:
        await anext(batches)
        await reader.async_close()
        with pytest.raises(HistoryReadError, match="history_reader_closed"):
            await anext(batches)
    assert query.call_count == 1
    assert reader.last_backfill_summary["status"] == "failed"
    with pytest.raises(HistoryReadError, match="history_reader_closed"):
        await reader.async_read_window(NOW - timedelta(days=1), NOW)


async def test_cancelled_reader_propagates_without_background_queries(
    hass, fake_recorder
):
    query, instance = fake_recorder
    started = asyncio.Event()
    blocked = asyncio.Event()

    async def blocked_executor(job):
        started.set()
        await blocked.wait()
        return job()

    instance.async_add_executor_job.side_effect = blocked_executor
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    iterator = reader.async_iter_slots(NOW - timedelta(days=30), NOW)
    task = asyncio.create_task(anext(iterator))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert reader.last_backfill_summary["status"] == "cancelled"
    assert not query.called
    await iterator.aclose()


async def test_missing_recorder_and_database_failure(hass, freezer):
    freezer.move_to(NOW)
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    with pytest.raises(HistoryReadError, match="recorder_unavailable"):
        await reader.async_read_window(NOW - timedelta(days=1), NOW)
    assert reader.last_read_summary["error"] == "recorder_unavailable"
    hass.config.components.add("recorder")
    instance = SimpleNamespace(
        async_add_executor_job=AsyncMock(side_effect=SQLAlchemyError("test"))
    )
    with patch("homeassistant.components.recorder.get_instance", return_value=instance):
        with pytest.raises(HistoryReadError, match="recorder_query_failed"):
            await reader.async_read_window(NOW - timedelta(days=1), NOW)
    assert reader.last_read_summary["error"] == "recorder_query_failed"


async def test_concurrent_reads_serialize_database_jobs(hass, fake_recorder):
    _, instance = fake_recorder
    started = asyncio.Event()
    proceed = asyncio.Event()
    active, maximum = 0, 0

    async def executor(job):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        started.set()
        await proceed.wait()
        active -= 1
        return job()

    instance.async_add_executor_job.side_effect = executor
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    first = asyncio.create_task(reader.async_read_window(NOW - timedelta(days=1), NOW))
    await started.wait()
    second = asyncio.create_task(reader.async_read_window(NOW - timedelta(days=1), NOW))
    await asyncio.sleep(0)
    assert instance.async_add_executor_job.await_count == 1
    proceed.set()
    await asyncio.gather(first, second)
    assert maximum == 1


async def test_real_recorder_history_is_validated_in_stream(
    hass, populated_hass, freezer, async_setup_recorder_instance
):
    from pytest_homeassistant_custom_component.components.recorder.common import (
        async_wait_recording_done,
    )

    freezer.move_to(NOW - timedelta(minutes=15))
    await async_setup_recorder_instance(hass)
    await hass.async_start()
    for minute in range(16):
        freezer.move_to(NOW - timedelta(minutes=15 - minute))
        for role in HISTORY_ROLES:
            state = make_state(role)
            hass.states.async_set(
                state.entity_id, state.state, {**state.attributes, "sequence": minute}
            )
        await hass.async_block_till_done()
        await async_wait_recording_done(hass)
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    async with aclosing(
        reader.async_iter_slots(NOW - timedelta(days=2), NOW)
    ) as iterator:
        batches = [batch async for batch in iterator]
    assert len(batches) == 2
    assert batches[-1][-1].home_kwh == pytest.approx(5.234 / 4)
    assert batches[0][0].home_kwh is None
    assert reader.last_backfill_summary["valid_slots"] == 1
    assert reader.last_backfill_summary["returned_slots"] == 192
    assert reader.last_backfill_summary["configured_retention_days"] == 10


async def test_wrong_units_preserved_for_history_quality(hass, fake_recorder):
    query, _ = fake_recorder
    start = NOW - timedelta(minutes=15)
    rows = valid_rows(start)
    rows[DEFAULT_ENTITIES["grid"]] = [
        make_state("grid", at=start + timedelta(minutes=n), unit="kWh")
        for n in range(15)
    ]
    query.return_value = rows
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    slots = await reader.async_read_window(start, NOW)
    assert slots[0].home_kwh is None
    assert reader.last_read_summary["issue_counts"]["invalid_unit"] == 1


async def test_close_during_read_discards_results(hass, fake_recorder):
    _, instance = fake_recorder
    started, proceed = asyncio.Event(), asyncio.Event()

    async def executor(job):
        started.set()
        await proceed.wait()
        return job()

    instance.async_add_executor_job.side_effect = executor
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    task = asyncio.create_task(reader.async_read_window(NOW - timedelta(days=1), NOW))
    await started.wait()
    await reader.async_close()
    proceed.set()
    with pytest.raises(HistoryReadError, match="history_reader_closed"):
        await task
    assert reader.last_read_summary["returned_slots"] == 0


async def test_disabled_recorder_is_explicit_and_never_queried(hass, fake_recorder):
    query, instance = fake_recorder
    instance.enabled = False
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    with pytest.raises(HistoryReadError, match="recorder_disabled"):
        await reader.async_read_window(NOW - timedelta(minutes=15), NOW)
    assert not query.called
    assert reader.last_read_summary["error"] == "recorder_disabled"
    assert reader.last_read_summary["recording_pause_history_verified"] is False
    assert reader.last_read_summary["historical_filter_changes_verified"] is False


async def test_disabling_while_job_waits_does_not_read_historical_rows(
    hass, fake_recorder
):
    query, instance = fake_recorder
    instance.enabled = True

    async def executor(job):
        instance.enabled = False
        return job()

    instance.async_add_executor_job.side_effect = executor
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    with pytest.raises(HistoryReadError, match="recorder_disabled"):
        await reader.async_read_window(NOW - timedelta(minutes=15), NOW)
    assert not query.called
