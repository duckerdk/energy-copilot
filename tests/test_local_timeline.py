"""Canonical Copenhagen presentation uses the same instants as UTC execution."""

from datetime import UTC, datetime

from custom_components.energy_copilot.sensor import (
    local_hourly_plan,
    local_timestamp,
)


def test_utc_plan_is_displayed_at_danish_local_wall_time():
    rows = [{"start": "2026-10-27T23:00:00+00:00", "grid_charge_kwh": 1.0}]
    result = local_hourly_plan(rows)
    assert result[0]["start"] == "2026-10-28T00:00:00+01:00"
    assert result[0]["grid_charge_kwh"] == 1.0
    assert rows[0]["start"] == "2026-10-27T23:00:00+00:00"


def test_local_date_and_offset_in_summer():
    assert local_timestamp(datetime(2026, 7, 1, 22, tzinfo=UTC)) == (
        "2026-07-02T00:00:00+02:00"
    )


def test_local_offset_change_fall_dst():
    assert local_timestamp("2026-10-25T00:30:00+00:00") == ("2026-10-25T02:30:00+02:00")
    assert local_timestamp("2026-10-25T01:30:00+00:00") == ("2026-10-25T02:30:00+01:00")
