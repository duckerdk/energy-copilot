"""M3 candidate evaluator: deterministic, explicit and read-only."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.energy_copilot.planner import (
    Dispatch,
    InfeasibleCandidate,
    Plant,
    Quarter,
    lowest_cost_candidate,
    reference_no_battery,
    simulate_candidate,
    spread_grid_charge_evenly,
)

START = datetime(2026, 10, 21, 10, tzinfo=UTC)
END = START + timedelta(minutes=15)
# Synthetic efficiencies and terminal value; these are NOT calibrated HA data.
PLANT = Plant(
    battery_capacity_dc_kwh=10.24,
    initial_soc_pct=50.0,
    battery_voltage_v=51.2,
    charge_limit_a=50.0,
    grid_charge_limit_a=50.0,
    eta_pv_to_ac=0.95,
    eta_pv_to_battery=0.95,
    eta_grid_to_battery=0.90,
    eta_battery_to_ac=0.90,
    terminal_value_dkk_per_kwh_dc=0.20,
)


def quarter(**kwargs):
    return replace(
        Quarter(START, END, 1.0, 0.45, 0.0, 0.45, False),
        **kwargs,
    )


def dispatch(**kwargs):
    return replace(Dispatch(0.0, 0.0, 0.0, 0.0, 0.0, 0.0), **kwargs)


def run(q=None, d=None, plant=PLANT):
    return simulate_candidate(plant, (q or quarter(),), (d or dispatch(),))


def test_no_dispatch_import_and_terminal_value_are_accounted_once():
    result = run()
    assert result.status == "physical_candidate_only_tou_unverified"
    assert result.quarters[0].grid_import_kwh == pytest.approx(0.45)
    assert result.energy_cost_dkk == pytest.approx(0.45)
    assert result.degradation_cost_dkk == 0
    assert result.terminal_battery_value_dkk == pytest.approx(5.12 * 0.2)
    assert result.objective_dkk == pytest.approx(0.45 - 1.024)
    assert result.final_soc_pct == pytest.approx(50)


def test_discharge_degradation_is_charged_on_dc_energy_not_ac():
    r = run(d=dispatch(battery_to_home_dc_kwh=0.5))
    assert r.quarters[0].grid_import_kwh == 0
    assert r.degradation_cost_dkk == pytest.approx(0.2)
    assert r.final_soc_pct == pytest.approx(100 * (5.12 - 0.5) / 10.24)
    assert r.objective_dkk == pytest.approx(0.2 - (5.12 - 0.5) * 0.2)


def test_charge_from_grid_changes_soc_after_explicit_conversion_loss():
    q = quarter(home_ac_kwh=0)
    r = run(q=q, d=dispatch(grid_to_battery_ac_kwh=0.3))
    assert r.quarters[0].grid_import_kwh == pytest.approx(0.3)
    assert r.quarters[0].grid_export_kwh == 0
    assert r.final_soc_pct == pytest.approx(100 * (5.12 + 0.27) / 10.24)
    assert r.degradation_cost_dkk == 0


def test_pv_can_be_split_between_home_and_battery_without_double_count():
    q = quarter(pv_dc_kwh=0.8, home_ac_kwh=0.38)
    d = dispatch(pv_to_home_dc_kwh=0.4, pv_to_battery_dc_kwh=0.4)
    r = run(q=q, d=d)
    assert r.quarters[0].grid_import_kwh == 0
    assert r.final_soc_pct == pytest.approx(100 * (5.12 + 0.38) / 10.24)


def test_pv_export_receives_only_ac_proceeds_at_allowed_price():
    q = quarter(pv_dc_kwh=1, home_ac_kwh=0, pv_export_enabled=True)
    r = run(q=q, d=dispatch(pv_to_export_dc_kwh=1))
    assert r.quarters[0].grid_export_kwh == pytest.approx(0.95)
    assert r.energy_cost_dkk == pytest.approx(-0.95 * 0.45)


@pytest.mark.parametrize("price", [0.399, -0.1])
def test_pv_export_blocked_below_040(price):
    with pytest.raises(InfeasibleCandidate, match="pv_export:policy"):
        run(
            q=quarter(
                pv_dc_kwh=1,
                home_ac_kwh=0,
                pv_export_enabled=True,
                sell_dkk_per_kwh=price,
            ),
            d=dispatch(pv_to_export_dc_kwh=1),
        )


def test_pv_export_not_implicitly_authorized_by_price():
    with pytest.raises(InfeasibleCandidate, match="pv_export:policy"):
        run(
            q=quarter(pv_dc_kwh=1, home_ac_kwh=0),
            d=dispatch(pv_to_export_dc_kwh=1),
        )


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("charge_limit_a", 51, "charge_limit_a:policy_limit"),
        ("grid_charge_limit_a", 51, "grid_charge_limit_a:policy_limit"),
        ("initial_soc_pct", 19.99, "initial_soc:policy_limit"),
        ("eta_battery_to_ac", 1.01, "eta_battery_to_ac:outside_0_to_1"),
        ("battery_capacity_dc_kwh", 0, "capacity:zero"),
    ],
)
def test_equipment_and_policy_parameters_are_not_silently_clipped(field, value, reason):
    with pytest.raises(InfeasibleCandidate, match=reason):
        run(plant=replace(PLANT, **{field: value}))


def test_soc_cannot_go_below_20_even_for_one_quarter():
    with pytest.raises(InfeasibleCandidate, match="battery:soc_policy_limit"):
        run(
            plant=replace(PLANT, initial_soc_pct=20),
            d=dispatch(battery_to_home_dc_kwh=0.1),
        )


def test_soc_cannot_exceed_100():
    with pytest.raises(InfeasibleCandidate, match="battery:soc_policy_limit"):
        run(
            plant=replace(PLANT, initial_soc_pct=100),
            q=quarter(home_ac_kwh=0),
            d=dispatch(grid_to_battery_ac_kwh=0.1),
        )


def test_battery_charge_and_grid_charge_current_limits_are_enforced():
    with pytest.raises(InfeasibleCandidate, match="battery:charge_current_limit"):
        run(
            q=quarter(pv_dc_kwh=1, home_ac_kwh=0),
            d=dispatch(pv_to_battery_dc_kwh=1),
        )
    with pytest.raises(InfeasibleCandidate, match="battery:grid_charge_current_limit"):
        run(
            plant=replace(PLANT, grid_charge_limit_a=5),
            q=quarter(home_ac_kwh=0),
            d=dispatch(grid_to_battery_ac_kwh=0.2),
        )


def test_discharge_uses_soc_and_home_energy_not_a_current_setting():
    result = run(
        q=quarter(home_ac_kwh=3),
        d=dispatch(battery_to_home_dc_kwh=1.5),
    )
    assert result.final_soc_pct == pytest.approx((5.12 - 1.5) / 10.24 * 100)


def test_simultaneous_battery_charge_and_discharge_is_forbidden():
    with pytest.raises(InfeasibleCandidate, match="battery:simultaneous"):
        run(
            q=quarter(home_ac_kwh=0.45, pv_dc_kwh=0.2),
            d=dispatch(pv_to_battery_dc_kwh=0.2, battery_to_home_dc_kwh=0.1),
        )


def test_simultaneous_grid_import_and_export_is_forbidden():
    with pytest.raises(InfeasibleCandidate, match="grid:simultaneous"):
        run(
            q=quarter(pv_dc_kwh=1, pv_export_enabled=True),
            d=dispatch(pv_to_export_dc_kwh=1),
        )


def test_pv_balance_and_home_oversupply_must_be_physical():
    with pytest.raises(InfeasibleCandidate, match="pv:balance"):
        run(
            q=quarter(pv_dc_kwh=1),
            d=dispatch(pv_curtailed_dc_kwh=0.9),
        )
    with pytest.raises(InfeasibleCandidate, match="home:oversupply"):
        run(
            q=quarter(pv_dc_kwh=1),
            d=dispatch(pv_to_home_dc_kwh=1),
        )


def test_negative_prices_are_permitted_but_negative_energy_is_not():
    r = run(q=quarter(buy_dkk_per_kwh=-0.4))
    assert r.energy_cost_dkk == pytest.approx(-0.18)
    with pytest.raises(InfeasibleCandidate, match="pv:negative"):
        run(q=quarter(pv_dc_kwh=-1))


def test_nan_and_boolean_values_are_rejected():
    with pytest.raises(InfeasibleCandidate, match="buy_price:nonfinite"):
        run(q=quarter(buy_dkk_per_kwh=float("nan")))
    with pytest.raises(InfeasibleCandidate, match="pv:not_numeric"):
        run(q=quarter(pv_dc_kwh=True))


def test_strict_utc_and_quarter_alignment_without_dst_guessing():
    with pytest.raises(InfeasibleCandidate, match="time:timezone_required"):
        run(q=quarter(start=START.replace(tzinfo=None)))
    with pytest.raises(InfeasibleCandidate, match="time:quarter_alignment"):
        run(q=quarter(end=END + timedelta(minutes=1)))


def test_consecutive_quarters_preserve_energy_and_soc():
    q1 = quarter(home_ac_kwh=0)
    q2 = replace(q1, start=END, end=END + timedelta(minutes=15), home_ac_kwh=0)
    r = simulate_candidate(
        PLANT,
        (q1, q2),
        (dispatch(grid_to_battery_ac_kwh=0.1), dispatch(grid_to_battery_ac_kwh=0.1)),
    )
    assert len(r.quarters) == 2
    assert r.final_soc_pct == pytest.approx(100 * (5.12 + 0.18) / 10.24)
    assert r.quarters[1].soc_start_pct == pytest.approx(r.quarters[0].soc_end_pct)
    with pytest.raises(InfeasibleCandidate, match="time:nonconsecutive"):
        simulate_candidate(PLANT, (q1, q1), (dispatch(), dispatch()))


def test_missing_forecasts_are_not_treated_as_zero():
    with pytest.raises(InfeasibleCandidate, match="pv:not_numeric"):
        run(q=quarter(pv_dc_kwh=None))
    with pytest.raises(InfeasibleCandidate, match="home:not_numeric"):
        run(q=quarter(home_ac_kwh=None))


def test_no_candidate_without_matching_quarters():
    with pytest.raises(InfeasibleCandidate, match="quarters:missing"):
        simulate_candidate(PLANT, (), ())


def test_reference_without_battery_is_explicit_not_fake_deye_baseline():
    q = quarter(pv_dc_kwh=1.0, home_ac_kwh=0.38, pv_export_enabled=True)
    r = reference_no_battery(PLANT, (q,))
    assert r.quarters[0].grid_import_kwh == 0
    assert r.quarters[0].grid_export_kwh == pytest.approx(0.57)
    assert r.final_soc_pct == 50
    assert r.status == "physical_candidate_only_tou_unverified"


def test_reference_curtailed_pv_if_below_export_price_threshold():
    q = quarter(
        pv_dc_kwh=1.0,
        home_ac_kwh=0.38,
        sell_dkk_per_kwh=0.399,
        pv_export_enabled=True,
    )
    r = reference_no_battery(PLANT, (q,))
    assert r.quarters[0].grid_import_kwh == 0
    assert r.quarters[0].grid_export_kwh == 0
    assert r.final_soc_pct == 50


def test_ranking_compares_real_energy_degradation_and_terminal_value():
    idle = dispatch()
    discharge = dispatch(battery_to_home_dc_kwh=0.5)
    index, result = lowest_cost_candidate(PLANT, (quarter(),), ((idle,), (discharge,)))
    assert index == 1
    assert result.degradation_cost_dkk == pytest.approx(0.2)
    cheap = quarter(buy_dkk_per_kwh=0.1)
    index, result = lowest_cost_candidate(PLANT, (cheap,), ((idle,), (discharge,)))
    assert index == 0
    assert result.degradation_cost_dkk == 0


def test_candidate_ranking_never_labels_dispatch_as_executable_tou():
    index, result = lowest_cost_candidate(PLANT, (quarter(),), ((dispatch(),),))
    assert index == 0
    assert result.status == "physical_candidate_only_tou_unverified"


def test_candidate_ranking_rejects_empty_or_nonphysical_candidates():
    with pytest.raises(InfeasibleCandidate, match="candidates:missing"):
        lowest_cost_candidate(PLANT, (quarter(),), ())
    with pytest.raises(InfeasibleCandidate, match="home:oversupply"):
        lowest_cost_candidate(
            PLANT,
            (quarter(pv_dc_kwh=1),),
            ((dispatch(pv_to_home_dc_kwh=1),),),
        )


def charge_window(hours=2, *, first_price=1.0, second_price=1.0):
    q1 = quarter(home_ac_kwh=0, buy_dkk_per_kwh=first_price)
    q2 = replace(
        q1,
        start=END,
        end=END + timedelta(minutes=15),
        buy_dkk_per_kwh=second_price,
    )
    return (q1, q2)


def test_even_charging_uses_25a_instead_of_50a_when_two_quarters_available():
    slots = charge_window()
    spread = spread_grid_charge_evenly(PLANT, slots, 0.64, (True, True))
    result = simulate_candidate(PLANT, slots, spread)
    assert [r.charge_current_a for r in result.quarters] == pytest.approx([25, 25])
    assert [r.grid_charge_current_a for r in result.quarters] == pytest.approx([25, 25])
    assert result.final_soc_pct == pytest.approx(100 * (5.12 + 0.64) / 10.24)


def test_one_available_quarter_needs_50a_but_never_more():
    slots = charge_window()
    spread = spread_grid_charge_evenly(PLANT, slots, 0.64, (True, False))
    result = simulate_candidate(PLANT, slots, spread)
    assert [r.charge_current_a for r in result.quarters] == pytest.approx([50, 0])
    with pytest.raises(InfeasibleCandidate, match="charge_window:insufficient_time"):
        spread_grid_charge_evenly(PLANT, slots, 0.641, (True, False))


def test_current_is_even_lower_with_four_eligible_quarters():
    slots = charge_window()
    extra = tuple(
        replace(
            q, start=q.start + timedelta(minutes=30), end=q.end + timedelta(minutes=30)
        )
        for q in slots
    )
    all_slots = slots + extra
    spread = spread_grid_charge_evenly(PLANT, all_slots, 0.64, (True,) * 4)
    r = simulate_candidate(PLANT, all_slots, spread)
    assert [q.charge_current_a for q in r.quarters] == pytest.approx([12.5] * 4)


def test_cost_tie_selects_lower_charging_current_even_when_fast_candidate_is_first():
    slots = charge_window()
    fast = spread_grid_charge_evenly(PLANT, slots, 0.64, (True, False))
    slow = spread_grid_charge_evenly(PLANT, slots, 0.64, (True, True))
    i, result = lowest_cost_candidate(PLANT, slots, (fast, slow))
    assert i == 1
    assert [q.charge_current_a for q in result.quarters] == pytest.approx([25, 25])
    assert simulate_candidate(PLANT, slots, fast).objective_dkk == pytest.approx(
        result.objective_dkk
    )


def test_economic_savings_take_priority_over_lower_charge_current():
    slots = charge_window(first_price=0.1, second_price=1.0)
    fast = spread_grid_charge_evenly(PLANT, slots, 0.64, (True, False))
    slow = spread_grid_charge_evenly(PLANT, slots, 0.64, (True, True))
    i, result = lowest_cost_candidate(PLANT, slots, (slow, fast))
    assert i == 1
    assert [q.charge_current_a for q in result.quarters] == pytest.approx([50, 0])


def test_spreading_does_not_invent_a_charge_window_or_override_limits():
    slots = charge_window()
    with pytest.raises(InfeasibleCandidate, match="charge_window:no_eligible_quarters"):
        spread_grid_charge_evenly(PLANT, slots, 0.2, (False, False))
    with pytest.raises(
        InfeasibleCandidate, match="charge_window:missing_or_mismatched"
    ):
        spread_grid_charge_evenly(PLANT, slots, 0.2, (True,))
    with pytest.raises(InfeasibleCandidate, match="charge_window:invalid_flag"):
        spread_grid_charge_evenly(PLANT, slots, 0.2, (1, False))
    with pytest.raises(InfeasibleCandidate, match="charge_window:insufficient_time"):
        spread_grid_charge_evenly(
            replace(PLANT, grid_charge_limit_a=10),
            slots,
            0.64,
            (True, True),
        )


def test_spreading_validates_pv_export_not_allowed_during_grid_import():
    q = quarter(home_ac_kwh=0, pv_dc_kwh=1, pv_export_enabled=True)
    with pytest.raises(InfeasibleCandidate, match="grid:simultaneous_import_export"):
        spread_grid_charge_evenly(PLANT, (q,), 0.1, (True,))


def test_zero_charge_target_has_no_unnecessary_cycling():
    slots = charge_window()
    spread = spread_grid_charge_evenly(PLANT, slots, 0, (False, False))
    r = simulate_candidate(PLANT, slots, spread)
    assert all(q.charge_current_a == 0 for q in r.quarters)
    assert r.final_soc_pct == 50
