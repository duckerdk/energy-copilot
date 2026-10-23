"""Whole-horizon optimizer regression: multi-hour cycles, PV and reserve value."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.energy_copilot.horizon_optimizer import (
    optimize_horizon,
    optimize_horizon_discrete,
)
from custom_components.energy_copilot.planner import (
    Plant,
    Quarter,
    simulate_candidate,
)


def plant(soc=50):
    return Plant(
        battery_capacity_dc_kwh=10.24,
        initial_soc_pct=soc,
        battery_voltage_v=51.2,
        charge_limit_a=50,
        discharge_limit_a=100,
        grid_charge_limit_a=50,
        eta_pv_to_ac=0.95,
        eta_pv_to_battery=0.95,
        eta_grid_to_battery=0.95,
        eta_battery_to_ac=0.95,
        terminal_value_dkk_per_kwh_dc=0,
    )


def series(prices, *, pv=None, load=0.6, export=False):
    start = datetime(2026, 10, 22, 12, tzinfo=UTC)
    return tuple(
        Quarter(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            price,
            0.5 if export else 0,
            pv[i] if pv is not None else 0,
            load,
            export,
        )
        for i, price in enumerate(prices)
    )


def test_charges_over_multiple_hours_and_discharges_over_multiple_quarters():
    p = plant(25)
    qs = series([0.5] * 12 + [2.8] * 16)
    result = optimize_horizon(p, qs)
    grid_charging = [
        i for i, d in enumerate(result.dispatches) if d.grid_to_battery_ac_kwh > 0.01
    ]
    discharging = [
        i for i, d in enumerate(result.dispatches) if d.battery_to_home_dc_kwh > 0.01
    ]
    assert len(grid_charging) >= 5
    assert len(discharging) >= 5
    assert max(grid_charging) < min(discharging)
    assert result.reference.objective_dkk - result.candidate.objective_dkk > 2
    assert result.candidate.status == "physical_candidate_only_tou_unverified"
    assert result.executable is False
    assert result.candidate.final_soc_pct >= 20


def test_saves_battery_during_cheaper_hours_instead_of_discharge():
    p = plant(80)
    qs = series([1.2] * 8 + [2.9] * 8)
    result = optimize_horizon(p, qs)
    assert all(d.battery_to_home_dc_kwh == 0 for d in result.dispatches[:8])
    assert sum(d.battery_to_home_dc_kwh for d in result.dispatches[8:]) > 0


def test_pv_surplus_changes_dispatch_and_only_pv_is_exported():
    p = plant(35)
    qs = series(
        [0.8] * 8 + [3.0] * 8,
        pv=[1.4] * 8 + [0.0] * 8,
        export=True,
    )
    result = optimize_horizon(p, qs)
    assert sum(d.pv_to_battery_dc_kwh for d in result.dispatches[:8]) > 0
    assert sum(d.battery_to_home_dc_kwh for d in result.dispatches[8:]) > 0
    for q, d, observed in zip(
        qs, result.dispatches, result.candidate.quarters, strict=True
    ):
        assert not (observed.grid_import_kwh > 1e-7 and observed.grid_export_kwh > 1e-7)
        assert d.battery_to_home_dc_kwh * p.eta_battery_to_ac <= q.home_ac_kwh + 1e-7
    assert simulate_candidate(
        Plant(
            **{
                **vars(p),
                "terminal_value_dkk_per_kwh_dc": result.terminal_value_dkk_per_kwh_dc,
            }
        ),
        qs,
        result.dispatches,
    ).objective_dkk == pytest.approx(result.candidate.objective_dkk)


def test_terminal_soc_not_forced_equal_to_initial_soc():
    p = plant(90)
    qs = series([0.7] * 8 + [3.5] * 16)
    result = optimize_horizon(p, qs)
    assert result.candidate.final_soc_pct < p.initial_soc_pct
    assert result.terminal_value_dkk_per_kwh_dc >= 0


def test_all_day_horizon_not_just_a_pair_of_quarters():
    p = plant(45)
    qs = series([0.5] * 24 + [1.1] * 32 + [2.5] * 40 + [0.8] * 48)
    result = optimize_horizon(p, qs)
    assert len(result.dispatches) == 144
    assert result.evaluated_transitions > 0
    assert result.soc_resolution_dc_kwh == 0.0
    assert sum(d.grid_to_battery_ac_kwh for d in result.dispatches) > 0
    assert result.reference.objective_dkk >= result.candidate.objective_dkk - 1e-7


def test_near_equal_prices_do_not_create_unprofitable_extra_cycles():
    p = plant(50)
    qs = series([1.5] * 24)
    result = optimize_horizon(p, qs)
    assert not any(d.grid_to_battery_ac_kwh > 1e-7 for d in result.dispatches)
    assert not any(d.battery_to_home_dc_kwh > 1e-7 for d in result.dispatches)


def test_no_battery_export_even_with_high_export_price():
    qs = series([0.4] * 8 + [3] * 8, pv=[0] * 16, load=0.3, export=True)
    result = optimize_horizon(plant(75), qs)
    assert all(
        d.battery_to_home_dc_kwh * 0.95 <= q.home_ac_kwh
        for q, d in zip(qs, result.dispatches)
    )
    assert all(row.grid_export_kwh == 0 for row in result.candidate.quarters)


def test_exact_fractional_discharge_avoids_unnecessary_expensive_grid_purchase():
    p = plant(80)
    qs = series(
        [4.5, 4.5, 4.5, 4.5, 0.5],
        pv=[0.25] * 4 + [0.0],
        load=0.30,
        export=True,
    )
    new = optimize_horizon(p, qs)
    old = optimize_horizon_discrete(p, qs)
    assert new.soc_resolution_dc_kwh == 0.0
    assert all(r.grid_import_kwh < 1e-7 for r in new.candidate.quarters[:4])
    assert sum(r.grid_import_kwh for r in old.candidate.quarters[:4]) > 0.0
    assert new.candidate.objective_dkk <= old.candidate.objective_dkk + 1e-6
    assert new.executable is False


def test_continuous_dispatch_is_independently_physical_and_pv_only_export():
    p = plant(75)
    qs = series(
        [1.0] * 8 + [4.2] * 8 + [2.0] * 8,
        pv=[1.6] * 8 + [0.0] * 16,
        load=0.65,
        export=True,
    )
    result = optimize_horizon(p, qs)
    assert result.soc_resolution_dc_kwh == 0.0
    for d, q, actual in zip(result.dispatches, qs, result.candidate.quarters):
        assert d.pv_to_export_dc_kwh <= q.pv_dc_kwh + 1e-8
        assert not (d.grid_to_battery_ac_kwh > 1e-7 and d.battery_to_home_dc_kwh > 1e-7)
        assert actual.soc_end_pct >= 20 - 1e-6
        assert actual.soc_end_pct <= 100 + 1e-6


def test_terminal_override_can_protect_future_value_without_fixed_soc():
    p = plant(80)
    qs = series([2.0] * 8 + [3.0] * 8, load=0.4)
    low = optimize_horizon(p, qs, terminal_value_override=0.3)
    high = optimize_horizon(p, qs, terminal_value_override=3.5)
    assert high.candidate.final_soc_pct >= low.candidate.final_soc_pct
    assert high.terminal_value_dkk_per_kwh_dc == pytest.approx(3.5)
    assert low.terminal_value_dkk_per_kwh_dc == pytest.approx(0.3)
