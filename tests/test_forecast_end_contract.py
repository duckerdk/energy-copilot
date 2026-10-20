"""Regression reconstruction of the observed end-indexed HA Forecast.Solar data.

The public fixture explicitly marks synthetic values. It contains no household
history and is not presented as the complete private HA export.
"""

import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest

from custom_components.energy_copilot.forecast_quality import forecast_coverage
from custom_components.energy_copilot.models import PriceSlot
from custom_components.energy_copilot.validation import forecast, utc

FIXTURE = Path(__file__).parent / "fixtures" / "forecast_solar_end_contract.json"


@pytest.fixture
def contract():
    return json.loads(FIXTURE.read_text())


def full_snapshot(contract):
    response = contract["response"]
    first = min(utc(t) for t in response["watts"])
    return forecast(response, first - timedelta(minutes=1))


def test_23_end_indexed_intervals_match_independent_watts_integral(contract):
    snapshot = full_snapshot(contract)
    assert len(snapshot.periods) == contract["expected_intervals"] == 23
    watts = {utc(t): value for t, value in contract["response"]["watts"].items()}
    energy = {utc(t): value for t, value in contract["response"]["wh_period"].items()}
    for period in snapshot.periods:
        trapezoid_wh = (
            (watts[period.start] + watts[period.end])
            / 2
            * (period.end - period.start).total_seconds()
            / 3600
        )
        assert period.kwh * 1000 == energy[period.end]
        assert (
            abs(period.kwh * 1000 - trapezoid_wh) <= contract["rounding_tolerance_wh"]
        )
    first_hour = next(
        p for p in snapshot.periods if p.end == utc("2026-10-20T10:00:00+02:00")
    )
    assert first_hour.start == utc("2026-10-20T09:00:00+02:00")
    assert first_hour.kwh == 0.614


def test_positive_last_sunset_energy_is_bounded_not_discarded(contract):
    snapshot = full_snapshot(contract)
    last = snapshot.periods[-1]
    assert last.start == utc("2026-10-21T18:00:00+02:00")
    assert last.end == utc("2026-10-21T18:06:30+02:00")
    assert last.kwh == 0.009
    assert snapshot.unbounded_energy_at == ()
    previous_sunset = next(
        p for p in snapshot.periods if p.end == utc("2026-10-20T18:08:59+02:00")
    )
    assert previous_sunset.kwh == 0.008
    assert previous_sunset.end - previous_sunset.start == timedelta(
        minutes=8, seconds=59
    )


def test_first_energy_without_predecessor_is_prior_not_future(contract):
    response = deepcopy(contract["response"])
    first = next(iter(response["watts"]))
    response["wh_period"][first] = 999
    received = utc(first) - timedelta(minutes=1)
    snapshot = forecast(response, received)
    assert snapshot.unbounded_prior_energy_at == (utc(first),)
    assert snapshot.unbounded_energy_at == ()
    assert snapshot.periods[0].start == utc(first)
    assert (
        snapshot.periods[0].kwh == 0.194
    )  # Ends at 09:00; no preceding period is invented.
    assert all(p.start >= utc(first) for p in snapshot.periods)


def test_night_14h_zero_requires_explicit_end_energy_and_boundaries(contract):
    snapshot = full_snapshot(contract)
    night = next(p for p in snapshot.periods if p.end - p.start > timedelta(hours=13))
    assert night.kwh == 0
    assert night.end - night.start == timedelta(hours=13, minutes=59)
    missing = deepcopy(contract["response"])
    night_end = next(t for t in missing["wh_period"] if utc(t) == night.end)
    del missing["wh_period"][night_end]
    incomplete = forecast(missing, snapshot.captured_at)
    assert not any(
        p.start == night.start and p.end == night.end for p in incomplete.periods
    )
    coverage = forecast_coverage(
        incomplete, (PriceSlot(night.start, night.end, 1, 1),), night.start
    )
    assert coverage["missing_intervals"] == [
        {
            "start_utc": night.start.isoformat(),
            "end_utc": night.end.isoformat(),
            "reason": "missing_energy_period",
            "zero_production_verified": False,
        }
    ]


def test_started_interval_keeps_full_wh_and_true_observation_time(contract):
    captured = utc("2026-10-20T09:31:00+02:00")
    snapshot = forecast(contract["response"], captured)
    assert snapshot.captured_at == captured
    assert snapshot.periods[0].start == utc("2026-10-20T09:00:00+02:00")
    assert snapshot.periods[0].end == utc("2026-10-20T10:00:00+02:00")
    assert snapshot.periods[0].kwh == 0.614  # No prorating of the original hour.


def test_missing_first_wh_does_not_remove_first_bounded_interval(contract):
    response = deepcopy(contract["response"])
    del response["wh_period"][next(iter(response["watts"]))]
    snapshot = forecast(response, full_snapshot(contract).captured_at)
    assert len(snapshot.periods) == 23
    assert snapshot.missing_energy_at == ()


def test_coverage_ends_at_actual_sunset_without_tail_zeros(contract):
    snapshot = full_snapshot(contract)
    start = utc("2026-10-21T18:00:00+02:00")
    end = utc("2026-10-22T00:00:00+02:00")
    coverage = forecast_coverage(snapshot, (PriceSlot(start, end, 1, 1),), start)
    assert coverage["missing_intervals"] == [
        {
            "start_utc": snapshot.source_end.isoformat(),
            "end_utc": end.isoformat(),
            "reason": "after_published_forecast",
            "zero_production_verified": False,
        }
    ]
    assert coverage["unbounded_energy_timestamps_utc"] == []


@pytest.mark.parametrize("day,hours", [("2026-03-29", 23), ("2026-10-25", 25)])
def test_dst_offset_transitions_keep_distinct_end_energy(day, hours):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Copenhagen")
    first = utc(datetime.fromisoformat(day).replace(tzinfo=zone))
    points = [first + timedelta(hours=n) for n in range(hours + 1)]
    watts = {point.astimezone(zone).isoformat(): 100 for point in points}
    # Distinct supplied Wh at every END catches start/end shifts even at repeated
    # 02:00 wall times; the first 999Wh has no predecessor and is never projected.
    values = {points[0].astimezone(zone).isoformat(): 999}
    values.update(
        {
            point.astimezone(zone).isoformat(): index
            for index, point in enumerate(points[1:], 1)
        }
    )
    snapshot = forecast({"watts": watts, "wh_period": values}, first)
    assert len(snapshot.periods) == hours
    assert [period.kwh * 1000 for period in snapshot.periods] == pytest.approx(
        range(1, hours + 1)
    )
    assert all(
        period.end - period.start == timedelta(hours=1) for period in snapshot.periods
    )
