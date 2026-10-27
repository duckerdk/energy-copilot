"""Yesterday saving is a measured-history counterfactual, not optimizer preview."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from custom_components.energy_copilot.actual_saving import (
    compute_yesterday,
    yesterday_bounds,
)

ENTITIES = {
    "grid": "sensor.grid",
    "battery": "sensor.battery",
    "buy": "sensor.buy",
    "sell": "sensor.sell",
}


def state(at, value, unit):
    return SimpleNamespace(
        state=str(value),
        last_updated=at,
        attributes={"unit_of_measurement": unit},
    )


def dataset(start, *, grid=1000, battery=1000, buy=2, sell=1):
    return {
        ENTITIES["grid"]: [state(start, grid, "W")],
        ENTITIES["battery"]: [state(start, battery, "W")],
        ENTITIES["buy"]: [state(start, buy, "DKK/kWh")],
        ENTITIES["sell"]: [state(start, sell, "DKK/kWh")],
    }


def test_discharge_saving_on_household_consumption():
    start = datetime(2026, 10, 26, tzinfo=UTC)
    result = compute_yesterday(
        dataset(start), ENTITIES, start, start + timedelta(hours=24), "2026-10-26"
    )
    assert result.reason is None
    assert result.coverage == 1.0
    assert result.actual_cost == 48.0
    assert result.baseline_cost == 93.6
    assert result.value == 45.6


def test_charging_can_be_negative_saving():
    start = datetime(2026, 10, 26, tzinfo=UTC)
    result = compute_yesterday(
        dataset(start, grid=1000, battery=-950),
        ENTITIES,
        start,
        start + timedelta(hours=24),
        "2026-10-26",
    )
    assert result.value == -48.0


def test_missing_prices_never_make_up_saving():
    start = datetime(2026, 10, 26, tzinfo=UTC)
    rows = dataset(start)
    del rows[ENTITIES["sell"]]
    result = compute_yesterday(
        rows, ENTITIES, start, start + timedelta(hours=24), "2026-10-26"
    )
    assert result.value is None
    assert result.reason == "history:missing_source"


def test_danish_daylight_saving_uses_actual_day_length():
    start, end, date = yesterday_bounds(datetime(2026, 10, 26, 12, tzinfo=UTC))
    assert date == "2026-10-25"
    assert (end - start) == timedelta(hours=25)


def test_forecast_horizon_not_used_for_historical_saving():
    start = datetime(2026, 10, 26, tzinfo=UTC)
    rows = dataset(start, grid=-1000, battery=0, sell=1.4)
    result = compute_yesterday(
        rows, ENTITIES, start, start + timedelta(hours=24), "2026-10-26"
    )
    assert result.value == 0.0
