"""Economic materiality, SOC tolerance and non-BOOST cheap-window scheduling."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.energy_copilot.economic_policy import (
    CHANGE_STRATEGY_BENEFIT_DKK,
    ECONOMIC_TIE_DKK,
    SOC_TARGET_TOLERANCE_PCT,
    START_GRID_CHARGE_BENEFIT_DKK,
    material_grid_charge,
)
from custom_components.energy_copilot.horizon_optimizer import optimize_horizon
from custom_components.energy_copilot.planner import Plant, Quarter, simulate_candidate


def _result(cost):
    return SimpleNamespace(candidate=SimpleNamespace(objective_dkk=cost))


def _plant(soc=25):
    return Plant(10.24, soc, 51.2, 50, 100, 50, 0.95, 0.95, 0.95, 0.95, 0)


def _quarters(prices, *, load=0.6):
    start = datetime(2026, 10, 28, tzinfo=UTC)
    return tuple(
        Quarter(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            price,
            0,
            0,
            load,
            False,
        )
        for i, price in enumerate(prices)
    )


def test_economic_thresholds_are_material_not_numerical_rounding():
    assert ECONOMIC_TIE_DKK == pytest.approx(0.01)
    assert START_GRID_CHARGE_BENEFIT_DKK == pytest.approx(0.10)
    assert CHANGE_STRATEGY_BENEFIT_DKK == pytest.approx(0.05)
    assert SOC_TARGET_TOLERANCE_PCT == pytest.approx(1.0)
    assert not material_grid_charge(_result(10.0), _result(10.0096), soc_pct=70)
    assert not material_grid_charge(_result(10.0), _result(10.099), soc_pct=70)
    assert material_grid_charge(_result(10.0), _result(10.11), soc_pct=70)
    assert not material_grid_charge(
        _result(10.0), _result(10.049), soc_pct=70, already_charging=True
    )
    assert material_grid_charge(
        _result(10.0), _result(10.051), soc_pct=70, already_charging=True
    )
    assert not material_grid_charge(_result(10.0), _result(11.0), soc_pct=99)


def test_soc99_prevents_last_percent_grid_charge_even_when_prices_favor_it():
    p = _plant(99)
    q = _quarters([0.20] * 4 + [4.0] * 8)
    scheduled = optimize_horizon(p, q)
    assert all(d.grid_to_battery_ac_kwh < 1e-7 for d in scheduled.dispatches[:4])
    assert scheduled.candidate.final_soc_pct <= 100 + 1e-7


def test_cheap_five_hour_window_spreads_grid_charging_without_costly_boost():
    plant = _plant(25)
    quarters = _quarters([0.50] * 20 + [3.0] * 16)
    planned = optimize_horizon(plant, quarters)
    first = [d.grid_to_battery_ac_kwh for d in planned.dispatches[:20]]
    assert sum(first) > 0.5
    nonzero = [amount for amount in first if amount > 0.01]
    assert len(nonzero) >= 8
    assert (
        max(first)
        < plant.battery_voltage_v
        * plant.grid_charge_limit_a
        / 4000
        / plant.eta_grid_to_battery
    )
    assert sum(first) == pytest.approx(
        sum(d.grid_to_battery_ac_kwh for d in planned.dispatches[:20]), abs=1e-7
    )
    checked = simulate_candidate(
        Plant(
            **{
                **vars(plant),
                "terminal_value_dkk_per_kwh_dc": planned.terminal_value_dkk_per_kwh_dc,
            }
        ),
        quarters,
        planned.dispatches,
    )
    assert checked.objective_dkk == pytest.approx(planned.candidate.objective_dkk)


def test_charging_not_started_for_negligible_horizon_arbitrage():
    plant = _plant(50)
    # The future avoided purchase is barely above cycle losses/degradation.
    quarters = _quarters([1.00] * 4 + [1.47] * 4)
    planned = optimize_horizon(plant, quarters, terminal_value_override=0.0)
    assert sum(d.grid_to_battery_ac_kwh for d in planned.dispatches[:4]) < 1e-6
