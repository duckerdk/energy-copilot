"""Energy Co-Pilot 2.0 synthetic regression: waiting for PV and peak reserve.

Only invented household load shapes; no diagnostic or Recorder data committed.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.energy_copilot.horizon_optimizer import optimize_horizon
from custom_components.energy_copilot.planner import (
    Plant,
    Quarter,
    simulate_candidate,
)
from custom_components.energy_copilot.planning_preview import _terminal_proxy
from custom_components.energy_copilot.replay import build_replay, simulate_replay
from custom_components.energy_copilot.tou_projection import validate_tou_projection

START = datetime(2026, 10, 30, 0, 0, tzinfo=UTC)
LOAD_RISK = {
    "hours_evaluated": 168,
    "peak_hours_evaluated": 42,
    "mae_kwh_per_hour": 0.64,
    "peak_bias_kwh_per_hour": -0.27,
    "peak_positive_underprediction_p75_kwh_per_hour": 0.47,
}


def _plant(soc=55):
    return Plant(
        battery_capacity_dc_kwh=10.24,
        initial_soc_pct=soc,
        battery_voltage_v=53.0,
        charge_limit_a=50.0,
        grid_charge_limit_a=50.0,
        eta_pv_to_ac=0.95,
        eta_pv_to_battery=0.95,
        eta_grid_to_battery=0.95,
        eta_battery_to_ac=0.95,
        terminal_value_dkk_per_kwh_dc=0.0,
    )


def _input(*, flat=False):
    # 37 hours with a low-price night, several PV hours, a cheap 14:00
    # alternative, and a pronounced afternoon spike the next day.
    # Values are synthetic; only the price shape resembles the issue report.
    rows = []
    for i in range(148):
        at = START + timedelta(minutes=15 * i)
        local_hour = (at.hour + 1) % 24
        # Copenhagen is UTC+1 on these dates, after DST.
        if local_hour in (2, 3, 4):
            buy = 2.41
        elif 10 <= local_hour <= 12:
            buy = 2.50
        elif local_hour == 13:
            buy = 2.52
        elif local_hour == 14:
            buy = 2.70
        elif local_hour == 15:
            buy = 3.12
        elif local_hour == 16:
            buy = 3.49
        elif local_hour == 17:
            buy = 5.8
        elif local_hour in (18, 19, 20):
            buy = 4.8
        else:
            buy = 3.0
        if flat:
            buy = 2.5
        pv = (
            0.28
            if local_hour in (11, 12, 13)
            else 0.20
            if local_hour in (10, 14)
            else 0.08
            if local_hour in (9, 15)
            else 0.0
        )
        home = (
            0.35
            if local_hour in (11, 12, 13, 14)
            else 0.42
            if 17 <= local_hour <= 20
            else 0.17
        )
        rows.append(
            Quarter(
                at,
                at + timedelta(minutes=15),
                buy,
                max(0.0, buy - 0.48),
                pv,
                home,
                True,
            )
        )
    return tuple(rows)


def _charge_in_hours(plan, quarters, hours):
    return sum(
        d.grid_to_battery_ac_kwh
        for q, d in zip(quarters, plan.dispatches, strict=True)
        if (q.start.hour + 1) % 24 in hours
    )


def test_v2_compares_waiting_for_pv_against_early_network_purchase():
    plant, quarters = _plant(), _input()
    baseline = optimize_horizon(
        plant,
        quarters,
        terminal_value_override=0,
        enable_pv_headroom=False,
    )
    selected = optimize_horizon(
        plant,
        quarters,
        terminal_value_override=0,
        load_risk_accuracy=LOAD_RISK,
    )
    r = selected.robust_policy
    assert r["status"] == "scenario_selected"
    assert r["candidate_count"] >= 3
    assert r["pv_option_reserved_max_dc_kwh"] > 0
    assert r["selected_risk_adjusted_dkk"] <= r["nominal_risk_adjusted_dkk"] + 0.101, r
    # No invented home/PV flow; the selected dispatch passes the production
    # simulator on *unchanged* nominal quarter inputs.
    physical = simulate_candidate(plant, quarters, selected.dispatches)
    assert physical.objective_dkk == pytest.approx(selected.candidate.objective_dkk)
    assert all(q.soc_end_pct >= 20 - 1e-6 for q in physical.quarters)
    # The v2 reserve can deliberately purchase MORE than the nominal plan
    # before a severe peak. This is justified only if the independently
    # scored scenario beats the nominal alternative on the full horizon.
    assert r["estimated_risk_reduction_dkk"] >= 0.1
    assert any(
        "wait_for_pv" in option["strategy"]
        for option in r["alternative_scores_dkk"]
    )
    assert _charge_in_hours(baseline, quarters, {11, 12, 13}) >= 0.0


def test_v2_does_not_create_a_peak_from_flat_prices():
    plant, quarters = _plant(), _input(flat=True)
    result = optimize_horizon(
        plant,
        quarters,
        terminal_value_override=0,
        load_risk_accuracy=LOAD_RISK,
    )
    assert result.robust_policy["peak_evidence"] == []
    assert (
        result.robust_policy["scenarios"]["weights_are_calibrated_probabilities"]
        is False
    )


def test_v2_replay_and_six_tou_projection_use_identical_physical_plan():
    plant, quarters = _plant(), _input()
    result = optimize_horizon(
        plant,
        quarters,
        terminal_value_override=0,
        load_risk_accuracy=LOAD_RISK,
    )
    projection = validate_tou_projection(
        plant, quarters, result.dispatches, result.candidate
    )
    assert projection["slots"] == 6
    assert sum(projection["per_slot_quarter_counts"]) == len(quarters)
    assert projection["hardware_execution_verified"] is False
    assert projection["soc_quantization_percent"] == 1
    replay = build_replay(
        plant,
        quarters,
        result,
        metadata={"load_risk_accuracy": LOAD_RISK},
    )
    assert replay["pv_headroom_policy"] == "joint_scenarios_v2"
    comparable = simulate_replay(replay)
    assert comparable["identical"], comparable["mismatches"][:3]


def test_unpublished_terminal_price_cannot_force_a_full_battery():
    plant = _plant(35)
    q = _input()[:8]
    last = q[-1].end
    forecast = SimpleNamespace(
        periods=[
            SimpleNamespace(
                start=last + timedelta(hours=i),
                end=last + timedelta(hours=i + 1),
                kwh=0.7,
            )
            for i in range(7)
        ]
    )
    price, basis, demand = _terminal_proxy(plant, q, forecast, [])
    assert demand > 0
    assert basis == "discounted_post_horizon_demand_proxy_v2_unverified"
    assert 0 < price < min(x.buy_dkk_per_kwh for x in q) / plant.eta_grid_to_battery
    # If future prices are unknown, a positive future demand alone is
    # insufficient to justify buying now to end the horizon at 100%.
    result = optimize_horizon(plant, q, terminal_value_override=price)
    assert result.candidate.final_soc_pct < 99
