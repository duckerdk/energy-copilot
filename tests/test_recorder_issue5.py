"""Anonymous constructed cases audit rejection unions; no private export is stored."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.energy_copilot.const import DEFAULT_ENTITIES, HISTORY_ROLES
from custom_components.energy_copilot.history import (
    RecorderHistoryReader,
    rejection_audit,
)
from custom_components.energy_copilot.recorder_reconstruction import (
    RecordingRun,
    reconstruct_history,
)

from .conftest import NOW, make_state


@pytest.fixture
def mock_recorder_before_hass(recorder_db_url):
    """Configure Recorder testing before the HA fixture initializes."""


def constructed_day(*, overlapping=False):
    """Mimic counts reported in #5, not timestamps or values from a private file."""
    start = NOW - timedelta(days=1)
    rows = {DEFAULT_ENTITIES[r]: [] for r in HISTORY_ROLES}

    def state_at(at, home=200):
        for role in HISTORY_ROLES:
            value = home if role in {"grid", "home"} else 0
            rows[DEFAULT_ENTITIES[role]].append(make_state(role, value, at=at))

    state_at(start)
    negative_quarters = (2, 5, 10, 15, 30, 40, 50, 60)
    # 26 negative changes over eight quarters. Every sample also satisfies the
    # template algebra, demonstrating that algebra does not prove valid demand.
    for index, quarter in enumerate(negative_quarters):
        for second in range(4 if index >= 6 else 3):
            at = start + timedelta(minutes=quarter * 15, seconds=second + 1)
            value = -10 - second
            rows[DEFAULT_ENTITIES["home"]].append(make_state("home", value, at=at))
            rows[DEFAULT_ENTITIES["grid"]].append(make_state("grid", value, at=at))
        at = start + timedelta(minutes=quarter * 15, seconds=10)
        for role in ("home", "grid"):
            rows[DEFAULT_ENTITIES[role]].append(make_state(role, 200, at=at))
    if overlapping:
        gap_start = start + timedelta(minutes=60 * 15 + 10)
        gap_end = start + timedelta(minutes=61 * 15 + 10)
    else:
        gap_start = start + timedelta(minutes=92 * 15)
        gap_end = start + timedelta(minutes=94 * 15)
    state_at(gap_end)
    runs = (
        RecordingRun(start, gap_start, recorded_end=gap_start),
        RecordingRun(gap_end, NOW),
    )
    return start, rows, runs


@pytest.mark.parametrize(
    "overlapping,expected_rejected,overlap", [(False, 10, 0), (True, 9, 1)]
)
def test_negative_home_and_recording_gap_counts_require_interval_union(
    overlapping, expected_rejected, overlap
):
    start, rows, runs = constructed_day(overlapping=overlapping)
    slots = reconstruct_history(rows, DEFAULT_ENTITIES, start, NOW, runs)
    audit = rejection_audit(slots, runs)
    assert len(slots) == 96
    assert audit["rejection_reason_slots"]["negative_home_power"] == 8
    assert audit["rejection_reason_slots"]["recorder_recording_gap"] == 2
    assert audit["negative_home_and_recording_gap_slots"] == overlap
    assert audit["negative_home_or_recording_gap_slots"] == expected_rejected
    assert audit["rejected_slots"] == expected_rejected
    assert sum(slot.home_kwh is not None for slot in slots) == 96 - expected_rejected
    assert all(
        slot.home_kwh is None
        for slot in slots
        if any(i.code == "negative_home_power" for i in slot.issues)
    )
    assert all(
        "value" not in issue
        for interval in audit["rejected_intervals"]
        for issue in interval["issues"]
    )
    assert (
        audit["recording_runs"][0]["recorded_end_utc"]
        == runs[0].recorded_end.isoformat()
    )


async def test_reader_exposes_per_quarter_reasons_and_negative_record_count(
    hass, freezer
):
    from types import SimpleNamespace

    freezer.move_to(NOW)
    start, rows, runs = constructed_day()
    hass.config.components.add("recorder")
    instance = SimpleNamespace(keep_days=10, enabled=True)
    instance.async_add_executor_job = AsyncMock(side_effect=lambda job: job())
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    with (
        patch("homeassistant.components.recorder.get_instance", return_value=instance),
        patch.object(reader, "_query_recorded_states", return_value=(rows, runs, ())),
    ):
        slots = await reader.async_read_window(start, NOW)
    summary = reader.last_read_summary
    assert summary["valid_slots"] == 86
    assert summary["rejected_slots"] == 10
    assert summary["negative_home_records_in_window"] == 26
    assert summary["source_rows"]["home"]["negative_power_records_in_window"] == 26
    assert summary["history_source_format"] == "ha_backend_state"
    assert summary["negative_home_and_recording_gap_slots"] == 0
    assert len(summary["rejected_intervals"]) == 10
    first = summary["rejected_intervals"][0]
    assert first["start_utc"] == slots[2].start.isoformat()
    assert {"code": "negative_home_power", "source": "home"} in first["issues"]
    assert {"code": "invalid_input", "source": "home"} in first["issues"]
    assert summary["recording_pause_history_verified"] is False


def test_partial_unknown_episodes_do_not_invent_restart_or_zero():
    start = NOW - timedelta(minutes=15)
    rows = {
        DEFAULT_ENTITIES[r]: [
            make_state(r, 200 if r in {"home", "grid"} else 0, at=start)
        ]
        for r in HISTORY_ROLES
    }
    at = start + timedelta(minutes=5)
    for role in ("pv", "grid", "battery"):
        state = "unknown" if role == "pv" else "unavailable"
        rows[DEFAULT_ENTITIES[role]].append(make_state(role, state, at=at))
    slots = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, [RecordingRun(start, NOW)]
    )
    assert slots[0].home_kwh is None
    assert {i.source for i in slots[0].issues if i.code == "invalid_input"} == {
        "pv",
        "grid",
        "battery",
        "home",
    }
    assert "recorder_recording_gap" not in {i.code for i in slots[0].issues}


def test_rejection_audit_is_bounded_for_long_consumers():
    start = NOW - timedelta(days=2)
    slots = reconstruct_history({}, DEFAULT_ENTITIES, start, NOW)
    audit = rejection_audit(slots)
    assert audit["rejected_slots"] == 192
    assert len(audit["rejected_intervals"]) == 96
    assert audit["rejected_intervals_truncated"] is True


def test_run_audit_retains_recorded_end_separately_from_query_clip():
    start = NOW - timedelta(minutes=15)
    actual_end = NOW + timedelta(hours=1)
    run = RecordingRun(start - timedelta(hours=2), NOW, recorded_end=actual_end)
    audit = rejection_audit((), (run,))
    assert audit["recording_runs"] == [
        {
            "start_utc": run.start.isoformat(),
            "recorded_end_utc": actual_end.isoformat(),
            "effective_end_utc": NOW.isoformat(),
            "closed_incorrect": False,
        }
    ]
