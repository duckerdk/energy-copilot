"""Economic explanation derives from a second feasible full-horizon optimization."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.energy_copilot.audit_economics import compare_first_quarter
from custom_components.energy_copilot.horizon_optimizer import optimize_horizon
from custom_components.energy_copilot.planner import Plant, Quarter
from custom_components.energy_copilot.replay import build_replay


def _plant(soc=20):
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
        terminal_value_dkk_per_kwh_dc=0.0,
    )


def _quarter(index, *, buy, sell=1.79, pv=0.0, load=0.5, export=True):
    at = datetime(2026, 10, 28, 10, tzinfo=UTC) + timedelta(minutes=15 * index)
    return Quarter(at, at + timedelta(minutes=15), buy, sell, pv, load, export)


def test_pv_storage_vs_best_plan_without_pv_charge_is_actual_solver_comparison():
    plant = _plant()
    quarters = (
        _quarter(0, buy=2.27, pv=0.7, load=0.18),
        _quarter(1, buy=3.5, load=0.7),
        _quarter(2, buy=4.0, load=0.7),
    )
    chosen = optimize_horizon(plant, quarters, terminal_value_override=0.0)
    assert chosen.dispatches[0].pv_to_battery_dc_kwh > 0.1
    replay = build_replay(plant, quarters, chosen)
    result = compare_first_quarter(replay, "pv_charge")
    candidates = (
        optimize_horizon(
            plant,
            quarters,
            terminal_value_override=0.0,
            audit_forbid_first_action="pv_charge",
            audit_force_first_pv_curtail=force_curtail,
        )
        for force_curtail in (False, True)
    )
    candidates = tuple(candidates)
    assert all(c.dispatches[0].pv_to_battery_dc_kwh == 0 for c in candidates)
    expected_cost = min(c.candidate.objective_dkk for c in candidates)
    assert result["economic_comparison_status"] == "evaluated"
    assert result["economic_saving_dkk"] == pytest.approx(
        expected_cost - chosen.candidate.objective_dkk
    )
    assert result["economic_saving_dkk"] >= -1e-6
    assert result["economic_alternative_forced_curtail"] in (True, False)
    # No audit rerun is permitted to change the original source dispatch.
    assert replay["expected"]["quarters"][0]["pv_to_battery_dc_kwh"] > 0.1


def test_grid_charge_vs_no_grid_charge_retains_original_and_validates_alternative():
    plant = _plant()
    quarters = (
        _quarter(0, buy=0.5, sell=0, load=0.7, export=False),
        _quarter(1, buy=3.5, sell=0, load=1.0, export=False),
        _quarter(2, buy=3.5, sell=0, load=1.0, export=False),
    )
    chosen = optimize_horizon(plant, quarters, terminal_value_override=0.0)
    assert chosen.dispatches[0].grid_to_battery_ac_kwh > 0.01
    replay = build_replay(plant, quarters, chosen)
    result = compare_first_quarter(replay, "grid_charge")
    assert result["economic_comparison_status"] == "evaluated"
    assert result["economic_saving_dkk"] >= -1e-6


def test_unsupported_counterfactual_is_explicit_and_does_not_guess():
    assert compare_first_quarter({}, "grid_import") == {
        "economic_comparison_status": "not_supported"
    }


def test_no_pv_storage_counterfactual_evaluates_grid_charge_with_curtail():
    plant = _plant()
    quarters = (
        _quarter(0, buy=0.20, pv=0.7, load=0.18),
        _quarter(1, buy=4.0, load=0.7),
        _quarter(2, buy=4.0, load=0.7),
    )
    chosen = optimize_horizon(plant, quarters, terminal_value_override=0.0)
    # This fixture covers both feasible *alternatives*, even when the
    # unconstrained planner selects cheap grid charging rather than PV storage.
    result = compare_first_quarter(build_replay(plant, quarters, chosen), "pv_charge")
    alternative_curtail = optimize_horizon(
        plant,
        quarters,
        terminal_value_override=0.0,
        audit_forbid_first_action="pv_charge",
        audit_force_first_pv_curtail=True,
    )
    alternative_export = optimize_horizon(
        plant,
        quarters,
        terminal_value_override=0.0,
        audit_forbid_first_action="pv_charge",
        audit_force_first_pv_curtail=False,
    )
    assert result["economic_alternative_cost_dkk"] == pytest.approx(
        min(
            alternative_curtail.candidate.objective_dkk,
            alternative_export.candidate.objective_dkk,
        )
    )
    assert not (
        alternative_curtail.candidate.quarters[0].grid_import_kwh > 1e-7
        and alternative_curtail.candidate.quarters[0].grid_export_kwh > 1e-7
    )
    assert not (
        alternative_export.candidate.quarters[0].grid_import_kwh > 1e-7
        and alternative_export.candidate.quarters[0].grid_export_kwh > 1e-7
    )
