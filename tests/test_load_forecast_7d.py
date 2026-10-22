"""Seven-day model unit tests using synthetic history only, never future leakage."""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.energy_copilot.load_forecast import (
    HourlyLoad,
    danish_public_holidays,
    forecast_seven_days,
    train_load_model,
)
from custom_components.energy_copilot.load_statistics import (
    _convert_hour,
    _read_power_means,
    _read_single,
)
from custom_components.energy_copilot.planning_inputs import PlanningInputError

LOCAL = ZoneInfo("Europe/Copenhagen")


def history(now, count=60, workday=0.4, free=1.2):
    start = now - timedelta(days=count)
    start = start.replace(minute=0, second=0, microsecond=0)
    result = []
    while start + timedelta(hours=1) <= now:
        day = start.astimezone(LOCAL).date()
        is_free = day.weekday() >= 5 or day in danish_public_holidays(day.year)
        result.append(HourlyLoad(start, free if is_free else workday))
        start += timedelta(hours=1)
    return tuple(result)


def test_danish_holidays_include_easter_and_exclude_abolished_great_prayer_day():
    holidays = danish_public_holidays(2026)
    assert datetime(2026, 4, 3).date() in holidays
    assert datetime(2026, 4, 6).date() in holidays
    assert datetime(2026, 12, 25).date() in holidays
    assert datetime(2026, 5, 1).date() not in holidays


def test_forecast_seven_days_separates_weekday_and_weekend():
    now = datetime(2026, 10, 22, 10, 1, tzinfo=UTC)
    model = train_load_model(history(now), now, "synthetic")
    result = forecast_seven_days(model, now)
    assert len(result.projection.periods) == 672
    assert result.projection.periods[0].start == datetime(
        2026, 10, 22, 10, 15, tzinfo=UTC
    )
    assert result.projection.periods[-1].end - result.projection.periods[0].start == timedelta(days=7)
    saturday = next(p for p in result.projection.periods if p.start.astimezone(LOCAL).weekday() == 5)
    monday = next(p for p in result.projection.periods if p.start.astimezone(LOCAL).weekday() == 0)
    assert saturday.kwh > monday.kwh
    assert sum(p.kwh for p in result.projection.periods) == pytest.approx(
        sum(p.kwh for p in result.hourly)
    )
    assert result.projection.method.endswith("_unverified")


def test_spring_and_autumn_dst_keep_contiguous_utc_quarters():
    for at in (datetime(2026, 3, 28, 10, tzinfo=UTC), datetime(2026, 10, 24, 10, tzinfo=UTC)):
        model = train_load_model(history(at), at, "synthetic")
        periods = forecast_seven_days(model, at).projection.periods
        assert len(periods) == 672
        assert all(left.end == right.start for left, right in zip(periods, periods[1:]))
        assert all(p.kwh >= 0 for p in periods)


def test_invalid_and_insufficient_history_never_become_zero():
    now = datetime(2026, 10, 22, tzinfo=UTC)
    with pytest.raises(PlanningInputError, match="load:insufficient_hourly_statistics"):
        train_load_model((HourlyLoad(now - timedelta(hours=2), 0.3),), now, "test")
    rows = (*history(now, count=16), HourlyLoad(now + timedelta(hours=1), 999))
    model = train_load_model(rows, now, "test")
    assert all(p.start < now for p in model.samples)
    with pytest.raises(PlanningInputError, match="load:duplicate_hour"):
        train_load_model((*history(now, count=16), history(now, count=16)[0]), now, "test")


def test_energy_and_power_statistics_have_explicit_units_and_missing_gaps():
    at = datetime(2026, 10, 20, tzinfo=UTC)
    row = {"start": at.timestamp(), "end": (at + timedelta(hours=1)).timestamp(), "mean": 1000.0, "change": 1.5}
    assert _convert_hour(row, "W") == 1.0
    assert _convert_hour(row, "kWh") == 1.5
    assert _convert_hour({"mean": None}, "W") is None
    assert _convert_hour({"change": -1}, "kWh") is None
    assert _read_single({"sensor.a": [row]}, "sensor.a", "kWh", at + timedelta(hours=2)) == {at: 1.5}
    assert _read_power_means({"sensor.a": [row]}, "sensor.a", "W", at + timedelta(hours=2)) == {at: 1000.0}
