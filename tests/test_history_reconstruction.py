"""Sparse Recorder state changes are not sparse device heartbeats."""

from datetime import timedelta

import pytest

from custom_components.energy_copilot.const import DEFAULT_ENTITIES, HISTORY_ROLES
from custom_components.energy_copilot.recorder_reconstruction import (
    RecordingRun,
    reconstruct_history,
)

from .conftest import NOW, make_state


def rows_at(at, *, pv=0, home=200):
    return {
        DEFAULT_ENTITIES[role]: [
            make_state(
                role, pv if role == "pv" else home if role == "home" else 0, at=at
            )
        ]
        for role in HISTORY_ROLES
    }


def test_constant_night_pv_and_home_are_held_inside_recording_run():
    start = NOW - timedelta(hours=1)
    rows = rows_at(start - timedelta(hours=2))
    runs = [RecordingRun(start - timedelta(hours=3), NOW)]
    slots = reconstruct_history(rows, DEFAULT_ENTITIES, start, NOW, runs)
    assert len(slots) == 4
    assert all(
        slot.home_kwh == pytest.approx(0.05) and not slot.issues for slot in slots
    )


def test_independent_last_change_times_do_not_imply_snapshot_skew():
    start = NOW - timedelta(minutes=15)
    rows = rows_at(start - timedelta(hours=2))
    rows[DEFAULT_ENTITIES["grid"]] = [
        make_state("grid", 0, at=start - timedelta(minutes=10))
    ]
    rows[DEFAULT_ENTITIES["battery"]] = [
        make_state("battery", 0, at=start - timedelta(seconds=20))
    ]
    slots = reconstruct_history(
        rows,
        DEFAULT_ENTITIES,
        start,
        NOW,
        [RecordingRun(start - timedelta(hours=3), NOW)],
    )
    assert slots[0].home_kwh == pytest.approx(0.05)
    assert not slots[0].issues


@pytest.mark.parametrize("role", ["pv", "grid", "battery", "home"])
def test_explicit_unavailable_is_never_turned_into_zero(role):
    start = NOW - timedelta(minutes=15)
    rows = rows_at(start)
    rows[DEFAULT_ENTITIES[role]].append(
        make_state(role, "unavailable", at=start + timedelta(minutes=5))
    )
    slot = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, [RecordingRun(start, NOW)]
    )[0]
    assert slot.home_kwh is None
    assert any(i.source == role and i.code == "invalid_input" for i in slot.issues)


def test_outage_and_cross_restart_carry_are_rejected():
    start = NOW - timedelta(minutes=45)
    rows = rows_at(start)
    runs = [
        RecordingRun(start, start + timedelta(minutes=15)),
        RecordingRun(start + timedelta(minutes=30), NOW),
    ]
    slots = reconstruct_history(rows, DEFAULT_ENTITIES, start, NOW, runs)
    assert slots[0].home_kwh == pytest.approx(0.05)
    assert slots[1].home_kwh is None
    assert any(i.code == "recorder_recording_gap" for i in slots[1].issues)
    assert slots[2].home_kwh is None
    assert any(
        i.source == "pv" and i.code == "historical_quality_unverifiable"
        for i in slots[2].issues
    )


def test_rows_after_restart_restore_coverage_without_using_future_rows():
    start = NOW - timedelta(minutes=30)
    rows = rows_at(start - timedelta(hours=1))
    for role in HISTORY_ROLES:
        rows[DEFAULT_ENTITIES[role]].append(
            make_state(
                role, 200 if role == "home" else 0, at=start + timedelta(minutes=15)
            )
        )
    slots = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, [RecordingRun(start, NOW)]
    )
    assert slots[0].home_kwh is None
    assert slots[1].home_kwh == pytest.approx(0.05)


def test_missing_units_and_excluded_entities_remain_diagnostic():
    start = NOW - timedelta(minutes=15)
    rows = rows_at(start)
    rows[DEFAULT_ENTITIES["pv"]] = [make_state("pv", 0, at=start, unit="kWh")]
    slot = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, [RecordingRun(start, NOW)], ["grid"]
    )[0]
    assert slot.home_kwh is None
    assert {(i.source, i.code) for i in slot.issues} >= {
        ("pv", "invalid_unit"),
        ("grid", "recorder_entity_excluded"),
    }


def test_no_run_evidence_and_unclean_run_do_not_claim_continuity():
    start = NOW - timedelta(minutes=15)
    rows = rows_at(start)
    unknown = reconstruct_history(rows, DEFAULT_ENTITIES, start, NOW)[0]
    crashed = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, [RecordingRun(start, NOW, False)]
    )[0]
    assert unknown.home_kwh is None and crashed.home_kwh is None
    assert any(i.code == "historical_quality_unverifiable" for i in unknown.issues)
    assert any(i.code == "recorder_run_uncertain" for i in crashed.issues)
