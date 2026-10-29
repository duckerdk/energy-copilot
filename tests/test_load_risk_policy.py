"""Risk-priced 0-15% SOC reserve, normal dispatch, and HA Replay parity."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.energy_copilot.horizon_optimizer import optimize_horizon
from custom_components.energy_copilot.planner import Plant, Quarter, simulate_candidate
from custom_components.energy_copilot.replay import build_replay, simulate_replay

START = datetime(2026, 10, 29, 10, 30, tzinfo=UTC)
LOAD_ACCURACY = {
    "hours_evaluated": 168,
    "peak_hours_evaluated": 42,
    "peak_bias_kwh_per_hour": -0.3,
    "peak_positive_underprediction_p75_kwh_per_hour": 0.8,
}


def _plant():
    return Plant(
        battery_capacity_dc_kwh=10.24,
        initial_soc_pct=66.0,
        battery_voltage_v=53.02,
        charge_limit_a=50.0,
        grid_charge_limit_a=50.0,
        eta_pv_to_ac=0.95,
        eta_pv_to_battery=0.95,
        eta_grid_to_battery=0.95,
        eta_battery_to_ac=0.95,
        terminal_value_dkk_per_kwh_dc=0.0,
    )


def _quarters(*, flat=False):
    rows = []
    # Solar first fills the battery, then high household demand draws
    # from the grid just before a steep evening price peak.
    for i in range(48):
        hour = (START + timedelta(minutes=15 * i)).hour
        if hour == 10:
            buy, pv, home = 2.66, 0.4885, 0.22686
        elif hour == 11:
            buy, pv, home = 2.592, 0.5555, 0.23366
        elif hour == 12:
            buy, pv, home = 2.60, 0.55325, 0.88465
        elif hour == 13:
            buy, pv, home = 2.737, 0.49525, 0.51515
        elif hour == 14:
            buy, pv, home = 3.604, 0.34475, 0.38678
        elif hour == 15:
            buy, pv, home = 4.37, 0.12435, 0.32585
        elif hour == 16:
            buy, pv, home = 6.405, 0, 0.32744
        elif hour == 17:
            buy, pv, home = 5.578, 0, 0.26981
        elif hour == 18:
            buy, pv, home = 5.189, 0, 0.19465
        elif hour == 19:
            buy, pv, home = 4.394, 0, 0.22537
        elif hour == 20:
            buy, pv, home = 3.358, 0, 0.18432
        else:
            buy, pv, home = 3.117, 0, 0.19321
        if flat:
            buy = 2.6
        at = START + timedelta(minutes=15 * i)
        rows.append(
            Quarter(
                at, at + timedelta(minutes=15), buy, max(0, buy - 0.483), pv, home, True
            )
        )
    return tuple(rows)


def test_joint_scenario_selection_prices_evening_risk_without_fake_load():
    plant, quarters = _plant(), _quarters()
    nominal = optimize_horizon(
        plant,
        quarters,
        terminal_value_override=2.078,
        enable_pv_headroom=False,
    )
    robust = optimize_horizon(
        plant,
        quarters,
        terminal_value_override=2.078,
        load_risk_accuracy=LOAD_ACCURACY,
    )
    policy = robust.robust_policy
    assert policy["status"] == "scenario_selected"
    assert policy["nominal_objective_dkk"] == pytest.approx(
        nominal.candidate.objective_dkk, abs=0.0001
    )
    assert policy["method"] == "v2_joint_scenario_receding_horizon_unverified"
    assert policy["candidate_count"] >= 1
    assert policy["estimated_risk_reduction_dkk"] >= -0.101
    assert policy["scenarios"]["weights_are_calibrated_probabilities"] is False
    assert robust.load_risk_policy["status"] == "integrated_in_v2_scenario_selection"
    assert robust.load_risk_policy["applied_extra_soc_points"] <= 15.0
    physical = simulate_candidate(
        plant.__class__(**{**vars(plant), "terminal_value_dkk_per_kwh_dc": 2.078}),
        quarters,
        robust.dispatches,
    )
    assert physical.objective_dkk == pytest.approx(robust.candidate.objective_dkk)
    assert all(q.soc_end_pct >= 20 for q in physical.quarters)
    assert sum(q.home_ac_kwh for q in quarters) > 0


def test_flat_prices_and_missing_holdout_do_not_invent_a_peak():
    plant = _plant()
    flat = optimize_horizon(
        plant,
        _quarters(flat=True),
        terminal_value_override=2.078,
        load_risk_accuracy=LOAD_ACCURACY,
    )
    assert flat.robust_policy["peak_evidence"] == []
    assert flat.load_risk_policy["status"] == "integrated_in_v2_scenario_selection"
    weak = optimize_horizon(
        plant,
        _quarters(),
        terminal_value_override=2.078,
        load_risk_accuracy={**LOAD_ACCURACY, "hours_evaluated": 12},
    )
    assert (
        weak.robust_policy["scenarios"]["weights_are_calibrated_probabilities"] is False
    )


def test_replay_repeats_hedge_with_frozen_holdout_data():
    plant, quarters = _plant(), _quarters()
    result = optimize_horizon(
        plant,
        quarters,
        terminal_value_override=2.078,
        load_risk_accuracy=LOAD_ACCURACY,
    )
    frozen = build_replay(
        plant,
        quarters,
        result,
        metadata={"load_risk_accuracy": LOAD_ACCURACY},
    )
    compared = simulate_replay(frozen)
    assert compared["identical"], compared["mismatches"][:3]
