"""Regression for 23 Oct 2026 Forecast.Solar day missing hourly night keys.

Actual published W/Wh values are those supplied by the integration user.
No private location or household measurements are included in this fixture.
"""

from datetime import timedelta

import pytest

from custom_components.energy_copilot.forecast_quality import forecast_coverage
from custom_components.energy_copilot.models import PriceSlot
from custom_components.energy_copilot.solar import (
    complete_night_forecast_edges,
    solar_evidence,
)
from custom_components.energy_copilot.validation import forecast, utc

# Public approximate coordinates for testing solar times, not the user's address.
LOCATION = {"latitude": 56, "longitude": 9}
WATTS = [
    ("08:12:46", 0, 0),
    ("09:00:00", 707, 278),
    ("10:00:00", 1606, 1157),
    ("11:00:00", 2422, 2014),
    ("12:00:00", 2806, 2614),
    ("13:00:00", 2493, 2650),
    ("14:00:00", 1897, 2195),
    ("15:00:00", 1315, 1606),
    ("16:00:00", 730, 1023),
    ("17:00:00", 345, 538),
    ("18:00:00", 100, 223),
    ("18:01:35", 0, 1),
]


def response():
    return {
        "watts": {f"2026-10-23T{t}+02:00": w for t, w, _ in WATTS},
        "wh_period": {f"2026-10-23T{t}+02:00": wh for t, _, wh in WATTS},
    }


def test_user_oct23_forecast_stays_raw_but_night_fills_to_full_price_day():
    first_day = utc("2026-10-23T00:00:00+02:00")
    now = utc("2026-10-23T01:02:00+02:00")
    end = first_day + timedelta(hours=24)
    raw = forecast(response(), now)
    assert raw.first_watts_zero and raw.last_watts_zero
    assert raw.night_zero_filled_seconds == 0
    assert len(raw.periods) == len(WATTS) - 1
    assert raw.periods[-1].kwh == 0.001
    original = raw.periods
    prices = tuple(
        PriceSlot(
            first_day + timedelta(hours=i), first_day + timedelta(hours=i + 1), 1, 1
        )
        for i in range(24)
    )
    sun = solar_evidence(LOCATION, now, end, now)
    completed = complete_night_forecast_edges(raw, sun, now, end)
    coverage = forecast_coverage(completed, prices, now, solar=sun)
    assert raw.periods == original
    assert completed.version == raw.version
    assert completed.source_start == raw.source_start
    assert completed.source_end == raw.source_end
    assert completed.periods[0].start == now
    assert completed.periods[0].end == utc("2026-10-23T08:12:46+02:00")
    assert completed.periods[0].kwh == 0
    assert completed.periods[-1].start == utc("2026-10-23T18:01:35+02:00")
    assert completed.periods[-1].end == end
    assert completed.periods[-1].kwh == 0
    assert coverage["missing_intervals"] == []
    assert coverage["coverage_fraction"] == pytest.approx(1.0)
    assert completed.night_zero_filled_seconds > 11 * 3600
    assert coverage["night_zero_filled_seconds"] == completed.night_zero_filled_seconds


def test_missing_daytime_energy_remains_missing_not_fabricated():
    data = response()
    del data["wh_period"]["2026-10-23T13:00:00+02:00"]
    now = utc("2026-10-23T01:02:00+02:00")
    end = utc("2026-10-24T00:00:00+02:00")
    raw = forecast(data, now)
    sun = solar_evidence(LOCATION, now, end, now)
    completed = complete_night_forecast_edges(raw, sun, now, end)
    covered = forecast_coverage(completed, (PriceSlot(now, end, 1, 1),), now, solar=sun)
    assert any(
        m["reason"] == "missing_energy_period" for m in covered["missing_intervals"]
    )
    assert all(p.kwh == 0 for p in completed.periods if p not in raw.periods)


def test_only_solar_confirmed_zero_watt_edges_are_eligible():
    now = utc("2026-10-23T01:02:00+02:00")
    end = utc("2026-10-24T00:00:00+02:00")
    sun = solar_evidence(LOCATION, now, end, now)
    source = response()
    source["watts"]["2026-10-23T08:12:46+02:00"] = 100
    raw = forecast(source, now)
    completed = complete_night_forecast_edges(raw, sun, now, end)
    assert completed.periods[0].start == raw.periods[0].start
    assert completed.periods[-1].end == end  # Sunset zero remains confirmed.
    source = response()
    source["watts"]["2026-10-23T18:01:35+02:00"] = 25
    raw = forecast(source, now)
    completed = complete_night_forecast_edges(raw, sun, now, end)
    assert completed.periods[0].start == now
    assert completed.periods[-1].end == raw.periods[-1].end
    assert complete_night_forecast_edges(raw, None, now, end) == raw


def test_noon_zero_does_not_backfill_morning_or_midday():
    data = response()
    original_first = "2026-10-23T08:12:46+02:00"
    data["watts"].pop(original_first)
    data["wh_period"].pop(original_first)
    first = "2026-10-23T11:00:00+02:00"
    data["watts"][first] = 0
    data["wh_period"][first] = 0
    now = utc("2026-10-23T01:02:00+02:00")
    end = utc("2026-10-24T00:00:00+02:00")
    raw = forecast(data, now)
    sun = solar_evidence(LOCATION, now, end, now)
    completed = complete_night_forecast_edges(raw, sun, now, end)
    assert completed.periods[0].start == raw.periods[0].start


def test_dst_midnight_boundary_is_local_day_not_always_24_utc_hours():
    # This verifies UTC-local-midnight handling even on 25-hour autumn days.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Copenhagen")
    day = datetime(2026, 10, 25, tzinfo=zone)
    now = utc(day)
    end = utc(datetime(2026, 10, 26, tzinfo=zone))
    sunrise = utc("2026-10-25T07:12:00+01:00")
    sunset = utc("2026-10-25T17:00:00+01:00")
    raw = forecast(
        {
            "watts": {sunrise.isoformat(): 0, sunset.isoformat(): 0},
            "wh_period": {sunrise.isoformat(): 0, sunset.isoformat(): 0},
        },
        now,
    )
    sun = solar_evidence(LOCATION, now, end, now)
    completed = complete_night_forecast_edges(raw, sun, now, end)
    assert completed.periods[-1].end == end
    assert end - now == timedelta(hours=25)
