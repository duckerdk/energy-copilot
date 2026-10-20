"""Post-0.1.2 aggregates reproduced synthetically, without private household data."""

import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.energy_copilot.const import DEFAULT_ENTITIES, HISTORY_ROLES
from custom_components.energy_copilot.history import (
    RecorderHistoryReader,
    rejection_audit,
)
from custom_components.energy_copilot.home_quality import negative_home_audit
from custom_components.energy_copilot.recorder_reconstruction import (
    RecordingRun,
    reconstruct_history,
)

from .conftest import NOW, make_state

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "issue5_post_012_quality.json").read_text()
)


def constructed_post_012_day():
    start = NOW - timedelta(days=1)
    rows = {DEFAULT_ENTITIES[r]: [] for r in HISTORY_ROLES}

    def seed(at):
        for role in HISTORY_ROLES:
            rows[DEFAULT_ENTITIES[role]].append(
                make_state(role, 200 if role in {"grid", "home"} else 0, at=at)
            )

    seed(start)
    for quarter in FIXTURE["negative_quarters"]:
        for sec in range(1, 4):
            at = start + timedelta(minutes=15 * quarter, seconds=sec)
            for role in ("home", "grid"):
                rows[DEFAULT_ENTITIES[role]].append(make_state(role, -10 - sec, at=at))
        for role in ("home", "grid"):
            rows[DEFAULT_ENTITIES[role]].append(
                make_state(
                    role, 200, at=start + timedelta(minutes=15 * quarter, seconds=6)
                )
            )
    runs, previous = [], start
    for quarter, offset, seconds in zip(
        FIXTURE["gap_quarters"],
        FIXTURE["gap_offsets_seconds"],
        FIXTURE["gap_seconds"],
        strict=True,
    ):
        gap_start = start + timedelta(minutes=15 * quarter, seconds=offset)
        gap_end = gap_start + timedelta(seconds=seconds)
        runs.append(RecordingRun(previous, gap_start, recorded_end=gap_start))
        seed(gap_end)
        previous = gap_end
    runs.append(RecordingRun(previous, NOW))
    return start, rows, tuple(runs)


def test_nine_negative_quarters_plus_three_short_gaps_are_twelve_not_zero_filled():
    start, rows, runs = constructed_post_012_day()
    slots = reconstruct_history(rows, DEFAULT_ENTITIES, start, NOW, runs)
    audit = rejection_audit(slots, runs)
    assert len(slots) == 96
    assert (
        sum(s.home_kwh is not None for s in slots) == FIXTURE["expected_valid_quarters"]
    )
    assert audit["rejected_slots"] == FIXTURE["expected_rejected_quarters"]
    assert audit["rejection_reason_slots"]["negative_home_power"] == 9
    assert audit["rejection_reason_slots"]["recorder_recording_gap"] == 3
    assert audit["negative_home_and_recording_gap_slots"] == 0
    assert (
        negative_home_audit(rows, DEFAULT_ENTITIES, start, NOW, runs)["records"] == 27
    )
    assert sum(s.unobserved_seconds for s in slots) == pytest.approx(
        9 * 5 + sum(FIXTURE["gap_seconds"])
    )
    assert sum(s.observed_seconds + s.unobserved_seconds for s in slots) == 86400
    for quarter, duration in zip(
        FIXTURE["gap_quarters"], FIXTURE["gap_seconds"], strict=True
    ):
        slot = slots[quarter]
        assert slot.home_kwh is None
        assert slot.observed_home_kwh == pytest.approx(0.2 * (900 - duration) / 3600)
        assert slot.unobserved_seconds == pytest.approx(duration)
        assert len(slot.unobserved_intervals) == 1
        gap = slot.unobserved_intervals[0]
        assert (gap.end - gap.start).total_seconds() == pytest.approx(duration)
        assert dict(slot.unobserved_reason_seconds)[
            "recorder_recording_gap"
        ] == pytest.approx(duration)
    assert all(s.home_kwh is None for s in slots if s.unobserved_seconds)


async def test_recent_reader_distinguishes_quarter_loss_from_unobserved_time(
    hass, freezer
):
    freezer.move_to(NOW)
    start, rows, runs = constructed_post_012_day()
    hass.config.components.add("recorder")
    instance = SimpleNamespace(keep_days=10, enabled=True)
    instance.async_add_executor_job = AsyncMock(side_effect=lambda job: job())
    reader = RecorderHistoryReader(hass, DEFAULT_ENTITIES)
    with (
        patch("homeassistant.components.recorder.get_instance", return_value=instance),
        patch.object(reader, "_query_recorded_states", return_value=(rows, runs, ())),
    ):
        await reader.async_read_window(start, NOW)
    result = reader.last_read_summary
    assert result["valid_slots"] == 84
    assert result["partial_slots"] == 12
    assert result["negative_home_records_in_window"] == 27
    assert result["coverage_fraction"] == 0.875
    assert result["observed_time_fraction"] == pytest.approx(
        (86400 - 45 - sum(FIXTURE["gap_seconds"])) / 86400
    )
    assert result["unobserved_reason_seconds"][
        "recorder_recording_gap"
    ] == pytest.approx(sum(FIXTURE["gap_seconds"]))
    assert result["physical_consumption_verified"] is False
    assert result["partial_energy_extrapolated"] is False
    assert result["negative_home_audit"]["context_counts"]["template_sum_matches"] == 27
    assert result["negative_home_audit"]["events_truncated"] is True
    assert all(r["closed_incorrect"] is False for r in result["recording_runs"])
    assert (
        result["device_freshness_verified"]
        is result["recording_pause_history_verified"]
        is result["historical_filter_changes_verified"]
        is False
    )


def test_numeric_template_during_unavailable_sources_is_not_usable_energy():
    start = NOW - timedelta(minutes=15)
    rows = {
        DEFAULT_ENTITIES[r]: [make_state(r, 200 if r == "home" else 0, at=start)]
        for r in HISTORY_ROLES
    }
    at = start + timedelta(minutes=1)
    rows[DEFAULT_ENTITIES["grid"]].append(make_state("grid", "unavailable", at=at))
    rows[DEFAULT_ENTITIES["home"]].append(make_state("home", -20, at=at))
    later = at + timedelta(seconds=1)
    rows[DEFAULT_ENTITIES["grid"]].append(make_state("grid", -20, at=later))
    rows[DEFAULT_ENTITIES["home"]].append(make_state("home", -20, at=later))
    audit = negative_home_audit(
        rows, DEFAULT_ENTITIES, start, NOW, (RecordingRun(start, NOW),)
    )
    assert audit["events"][0]["invalid_sources"] == {"grid": "invalid_input"}
    assert audit["events"][0]["template_residual_w"] is None  # No future row lookahead.
    assert audit["events"][1]["template_sum_matches_within_1w"] is True
    assert audit["events"][1]["different_source_change_times"] is True
    assert audit["causal_conclusion"] == "not_identifiable_from_state_changes_alone"
    assert audit["timestamp_basis"] == "recorder_state_change_not_device_report"
    slot = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, (RecordingRun(start, NOW),)
    )[0]
    assert slot.home_kwh is None
    assert slot.observed_seconds == 60
    assert slot.observed_home_kwh == pytest.approx(0.2 / 60)


def test_no_evidence_is_not_observed_zero_and_audit_details_are_bounded():
    start = NOW - timedelta(minutes=15)
    slot = reconstruct_history({}, DEFAULT_ENTITIES, start, NOW)[0]
    assert slot.observed_home_kwh is None
    assert slot.observed_seconds == 0 and slot.unobserved_seconds == 900
    rows = {DEFAULT_ENTITIES[r]: [make_state(r, 0, at=start)] for r in HISTORY_ROLES}
    for second in range(100):
        rows[DEFAULT_ENTITIES["home"]].append(
            make_state(
                "home", -1 if second % 2 else 100, at=start + timedelta(seconds=second)
            )
        )
    slot = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, (RecordingRun(start, NOW),)
    )[0]
    assert len(slot.unobserved_intervals) == 32
    assert slot.unobserved_intervals_truncated
    assert slot.observed_seconds + slot.unobserved_seconds == 900


def test_short_run_gap_and_startup_unavailability_have_separate_durations():
    start = NOW - timedelta(minutes=15)
    rows = {
        DEFAULT_ENTITIES[r]: [
            make_state(r, 200 if r in {"grid", "home"} else 0, at=start)
        ]
        for r in HISTORY_ROLES
    }
    gap_start, restarted = (
        start + timedelta(seconds=300),
        start + timedelta(seconds=310),
    )
    for role in HISTORY_ROLES:
        rows[DEFAULT_ENTITIES[role]].append(
            make_state(role, 0 if role == "home" else "unavailable", at=restarted)
        )
    rows[DEFAULT_ENTITIES["home"]].append(
        make_state("home", 0, at=start + timedelta(seconds=311))
    )
    for role, second in [("pv", 320), ("grid", 322), ("battery", 324), ("home", 326)]:
        rows[DEFAULT_ENTITIES[role]].append(
            make_state(
                role,
                200 if role in {"grid", "home"} else 0,
                at=start + timedelta(seconds=second),
            )
        )
    runs = (RecordingRun(start, gap_start), RecordingRun(restarted, NOW))
    slot = reconstruct_history(rows, DEFAULT_ENTITIES, start, NOW, runs)[0]
    assert slot.home_kwh is None
    assert slot.unobserved_seconds == 26
    reasons = dict(slot.unobserved_reason_seconds)
    assert reasons["recorder_recording_gap"] == 10
    assert reasons["invalid_input"] == 14
    assert reasons["home_predates_source_recovery"] == 2
    assert slot.observed_home_kwh == pytest.approx(0.2 * (900 - 26) / 3600)
