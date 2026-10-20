from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.energy_copilot.forecast_quality import forecast_coverage
from custom_components.energy_copilot.models import PriceSlot
from custom_components.energy_copilot.validation import forecast, utc

from .conftest import NOW
from .test_validation import forecast_response


def test_started_hour_is_preserved_without_prorating_or_backdating():
    received = NOW + timedelta(minutes=31)
    snapshot = forecast(forecast_response(), received)
    result = forecast_coverage(
        snapshot, (PriceSlot(NOW, NOW + timedelta(hours=1), 1, 1),), received
    )
    assert snapshot.periods[0].start == NOW and snapshot.periods[0].kwh == 1
    assert snapshot.captured_at == received
    assert result["partially_elapsed_periods"] == 1
    assert result["expected_seconds"] == result["covered_seconds"] == 29 * 60
    assert result["missing_intervals"] == []


def test_reported_evening_horizon_is_not_extended_with_fake_night_zeros():
    times = [NOW + timedelta(hours=2), NOW + timedelta(hours=6, minutes=6, seconds=30)]
    source = {
        "watts": {t.isoformat(): 100 for t in times},
        "wh_period": {times[0].isoformat(): 500, times[1].isoformat(): 0},
    }
    snapshot = forecast(source, NOW)
    prices = tuple(
        PriceSlot(NOW + timedelta(hours=h), NOW + timedelta(hours=h + 1), 1, 1)
        for h in range(1, 12)
    )
    result = forecast_coverage(snapshot, prices, NOW)
    assert result["missing_intervals"] == [
        {
            "start_utc": (NOW + timedelta(hours=1)).isoformat(),
            "end_utc": times[0].isoformat(),
            "reason": "before_published_forecast",
            "zero_production_verified": False,
        },
        {
            "start_utc": times[1].isoformat(),
            "end_utc": (NOW + timedelta(hours=12)).isoformat(),
            "reason": "after_published_forecast",
            "zero_production_verified": False,
        },
    ]
    assert len(snapshot.periods) == 1


def test_internal_missing_energy_and_final_unbounded_energy_remain_visible():
    source = forecast_response()
    source["watts"][(NOW + timedelta(hours=3)).isoformat()] = 0
    del source["wh_period"][(NOW + timedelta(hours=1)).isoformat()]
    source["wh_period"][(NOW + timedelta(hours=3)).isoformat()] = 100
    snapshot = forecast(source, NOW)
    result = forecast_coverage(
        snapshot, (PriceSlot(NOW, NOW + timedelta(hours=3), 1, 1),), NOW
    )
    assert result["missing_intervals"][0]["reason"] == "missing_energy_period"
    assert result["missing_energy_timestamps_utc"] == [
        (NOW + timedelta(hours=1)).isoformat()
    ]
    assert result["unbounded_energy_timestamps_utc"] == [
        (NOW + timedelta(hours=3)).isoformat()
    ]


@pytest.mark.parametrize("day,hours", [("2026-03-29", 23), ("2026-10-25", 25)])
def test_dst_missing_hours_use_actual_utc_durations(day, hours):
    zone = ZoneInfo("Europe/Copenhagen")
    first = utc(datetime.fromisoformat(day).replace(tzinfo=zone))
    points = [first + timedelta(hours=i) for i in range(hours + 1)]
    source = {
        "watts": {t.astimezone(zone).isoformat(): 0 for t in points},
        "wh_period": {t.astimezone(zone).isoformat(): 0 for t in points},
    }
    snapshot = forecast(source, first)
    slots = tuple(PriceSlot(a, b, 1, 1) for a, b in zip(points, points[1:]))
    result = forecast_coverage(snapshot, slots, first)
    assert result["missing_intervals"] == []
    assert result["covered_seconds"] == hours * 3600


def test_missing_energy_at_leading_boundary_is_not_conflated_with_unpublished_hours():
    source = forecast_response()
    del source["wh_period"][NOW.isoformat()]
    snapshot = forecast(source, NOW - timedelta(hours=1))
    result = forecast_coverage(
        snapshot,
        (PriceSlot(NOW - timedelta(hours=1), NOW + timedelta(hours=2), 1, 1),),
        NOW - timedelta(hours=1),
    )
    assert [gap["reason"] for gap in result["missing_intervals"]] == [
        "before_published_forecast",
        "missing_energy_period",
    ]
    assert result["missing_intervals"][0]["end_utc"] == NOW.isoformat()
