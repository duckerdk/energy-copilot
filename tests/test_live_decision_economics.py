"""Live SOC feedback and actual future demand govern profitable discharge."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from custom_components.energy_copilot.horizon_optimizer import optimize_horizon
from custom_components.energy_copilot.planner import Plant, Quarter
from custom_components.energy_copilot.replay import build_replay, simulate_replay

START = datetime(2026, 10, 29, 15, tzinfo=UTC)
LOW_RISK = {
    "hours_evaluated": 168,
    "peak_hours_evaluated": 42,
    "mae_kwh_per_hour": 0.25,
    "peak_bias_kwh_per_hour": -0.05,
    "peak_positive_underprediction_p75_kwh_per_hour": 0.2,
}


def plant(soc):
    return Plant(
        battery_capacity_dc_kwh=10.24,
        initial_soc_pct=soc,
        battery_voltage_v=52.0,
        charge_limit_a=50.0,
        grid_charge_limit_a=50.0,
        eta_pv_to_ac=0.95,
        eta_pv_to_battery=0.95,
        eta_grid_to_battery=0.95,
        eta_battery_to_ac=0.95,
        terminal_value_dkk_per_kwh_dc=0.0,
    )


def periods(early_kwh, expensive_kwh):
    result = []
    for i in range(8):
        start = START + timedelta(minutes=15 * i)
        buy = 4.37 if i < 4 else 6.405
        result.append(
            Quarter(
                start,
                start + timedelta(minutes=15),
                buy,
                max(0.0, buy - 0.50),
                0.0,
                (early_kwh if i < 4 else expensive_kwh) / 4.0,
                True,
            )
        )
    return tuple(result)


def total_before_peak(result):
    return sum(q.grid_import_kwh for q in result.candidate.quarters[:4])


def discharged_before_peak(result):
    return sum(d.battery_to_home_dc_kwh for d in result.dispatches[:4])


def test_soc_96_vs_83_release_extra_energy_before_peak():
    quarters = periods(2.0, 5.0)
    low = optimize_horizon(
        plant(83.0),
        quarters,
        terminal_value_override=0.0,
        load_risk_accuracy=LOW_RISK,
    )
    high = optimize_horizon(
        plant(96.0),
        quarters,
        terminal_value_override=0.0,
        load_risk_accuracy=LOW_RISK,
    )
    assert total_before_peak(low) > 0.5
    assert total_before_peak(high) < 0.20
    assert discharged_before_peak(high) > discharged_before_peak(low)
    assert high.robust_policy["status"] == "scenario_selected"
    assert high.candidate.final_soc_pct >= 20.0


def test_two_kwh_buy_at_four_cannot_be_justified_by_one_kwh_demand_at_six():
    # 50% SOC leaves ~3.07 kWh DC above the physical 20% floor, nearly
    # enough to serve 2 kWh now and 1 kWh at the later peak.
    quarters = periods(2.0, 1.0)
    plan = optimize_horizon(
        plant(50.0),
        quarters,
        terminal_value_override=0.0,
        load_risk_accuracy=LOW_RISK,
    )
    assert total_before_peak(plan) < 0.4
    assert discharged_before_peak(plan) > 1.8
    assert sum(q.grid_import_kwh for q in plan.candidate.quarters[4:]) < 0.3
    assert plan.robust_policy["status"] == "scenario_selected"


def test_ha_replay_accepts_partial_active_quarter_with_real_duration():
    quarters = periods(2.0, 1.0)
    first = replace(
        quarters[0],
        start=quarters[0].start + timedelta(minutes=7),
        home_ac_kwh=quarters[0].home_ac_kwh * 8 / 15,
    )
    quarters = (first, *quarters[1:])
    battery = plant(96.0)
    planned = optimize_horizon(
        battery,
        quarters,
        terminal_value_override=0.0,
        load_risk_accuracy=LOW_RISK,
    )
    frozen = build_replay(
        battery, quarters, planned, metadata={"load_risk_accuracy": LOW_RISK}
    )
    compared = simulate_replay(frozen)
    assert compared["identical"], compared["mismatches"][:3]
