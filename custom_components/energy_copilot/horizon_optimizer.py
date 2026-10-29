"""Whole-horizon continuous HA dry-run dispatch and legacy discrete benchmark.

No inverter commands are issued; all candidates undergo independent validation.
"""

from dataclasses import dataclass, replace
from math import ceil, floor

from .planner import (
    DEGRADATION_DKK_PER_KWH_DC,
    EPS,
    MIN_SOC,
    PV_EXPORT_MIN_DKK_PER_KWH,
    CandidateResult,
    Dispatch,
    InfeasibleCandidate,
    Plant,
    Quarter,
    reference_no_battery,
    simulate_candidate,
)

SOC_STEP_DC_KWH = 0.10
COST_TIE_DKK = 1e-8


@dataclass(frozen=True)
class HorizonResult:
    candidate: CandidateResult
    reference: CandidateResult
    dispatches: tuple[Dispatch, ...]
    terminal_value_dkk_per_kwh_dc: float
    evaluated_transitions: int
    soc_resolution_dc_kwh: float = SOC_STEP_DC_KWH
    method: str = "whole_horizon_soc_dynamic_programming_grid_0_10_kwh"
    executable: bool = False
    pv_headroom: tuple = ()
    pv_underprediction_kwh: float | None = None
    pv_headroom_enabled: bool = False
    economic_policy_reason: str | None = None
    economic_policy_benefit_dkk: float | None = None
    load_risk_policy: dict | None = None


def _dispatch(
    plant: Plant, q: Quarter, delta_dc: float
) -> tuple[Dispatch, float] | None:
    """Cost the best solar-first flow for a single battery energy transition.

    Positive delta stores DC energy, negative delta feeds the home. A positive
    delta uses surplus PV before grid; no battery-to-grid flow exists.
    """
    pv_home = min(q.pv_dc_kwh, q.home_ac_kwh / plant.eta_pv_to_ac)
    pv_surplus = max(0.0, q.pv_dc_kwh - pv_home)
    grid_home = max(0.0, q.home_ac_kwh - pv_home * plant.eta_pv_to_ac)
    pv_battery = 0.0
    grid_battery = 0.0
    battery_home = 0.0
    if delta_dc > EPS:
        pv_battery = min(pv_surplus, delta_dc / plant.eta_pv_to_battery)
        remaining_dc = max(0.0, delta_dc - pv_battery * plant.eta_pv_to_battery)
        grid_battery = remaining_dc / plant.eta_grid_to_battery
        limit_dc = (
            plant.battery_voltage_v
            * min(plant.charge_limit_a, plant.grid_charge_limit_a)
            / 4000
        )
        if delta_dc > plant.battery_voltage_v * plant.charge_limit_a / 4000 + EPS:
            return None
        if grid_battery * plant.eta_grid_to_battery > limit_dc + EPS:
            return None
    elif delta_dc < -EPS:
        battery_home = -delta_dc
        if battery_home * plant.eta_battery_to_ac > grid_home + EPS:
            return None
        grid_home = max(0.0, grid_home - battery_home * plant.eta_battery_to_ac)
    remaining_pv = max(0.0, pv_surplus - pv_battery)
    sell_ok = q.pv_export_enabled and q.sell_dkk_per_kwh >= PV_EXPORT_MIN_DKK_PER_KWH
    pv_export = remaining_pv if sell_ok else 0.0
    if pv_export > EPS and grid_home + grid_battery > EPS:
        return None
    d = Dispatch(
        pv_to_home_dc_kwh=pv_home,
        pv_to_battery_dc_kwh=pv_battery,
        pv_to_export_dc_kwh=pv_export,
        pv_curtailed_dc_kwh=remaining_pv - pv_export,
        grid_to_battery_ac_kwh=grid_battery,
        battery_to_home_dc_kwh=battery_home,
    )
    cost = (
        (grid_home + grid_battery) * q.buy_dkk_per_kwh
        - pv_export * plant.eta_pv_to_ac * q.sell_dkk_per_kwh
        + battery_home * DEGRADATION_DKK_PER_KWH_DC
    )
    return d, cost


def optimize_horizon_discrete(
    plant: Plant, quarters: tuple[Quarter, ...]
) -> HorizonResult:
    """Find minimum model cost over all available contiguous quarters.

    No max duration or single-charge/single-discharge restriction. End SOC may
    differ from initial SOC; remaining energy is given a transparent, uncertain
    conservative terminal replacement value from the cheapest published hour.
    Grid/PV power and SOC constraints are checked again by the existing
    independent quarter-by-quarter simulator.
    """
    if not quarters:
        raise InfeasibleCandidate("horizon:empty")
    # Validate plant and time-aligned inputs through the independent evaluator.
    if plant.initial_soc_pct < MIN_SOC:
        raise InfeasibleCandidate("soc:below_minimum")
    terminal_price = min(q.buy_dkk_per_kwh for q in quarters)
    terminal_value = max(0.0, terminal_price / plant.eta_grid_to_battery)
    calibrated = Plant(
        **{
            **vars(plant),
            "terminal_value_dkk_per_kwh_dc": terminal_value,
        }
    )
    reference = reference_no_battery(calibrated, quarters)
    initial_energy = plant.battery_capacity_dc_kwh * plant.initial_soc_pct / 100
    min_energy = plant.battery_capacity_dc_kwh * MIN_SOC / 100
    lower = ceil((min_energy - initial_energy - EPS) / SOC_STEP_DC_KWH)
    upper = floor(
        (plant.battery_capacity_dc_kwh - initial_energy + EPS) / SOC_STEP_DC_KWH
    )
    # Each stored state includes actual economic cost and secondary charging
    # stress metric. Economic costs take precedence over lower current.
    costs: dict[int, tuple[float, float]] = {0: (0.0, 0.0)}
    trace: list[dict[int, tuple[int, Dispatch]]] = []
    transitions = 0
    for q in quarters:
        next_costs = {}
        predecessors = {}
        for change in range(-upper + lower, upper - lower + 1):
            if change == 0:
                pass
            delta = change * SOC_STEP_DC_KWH
            result = _dispatch(calibrated, q, delta)
            if result is None:
                continue
            dispatch, incremental = result
            extra_stress = (
                (delta * 4000 / calibrated.battery_voltage_v) ** 2 if delta > 0 else 0.0
            )
            for previous, (current_cost, current_stress) in costs.items():
                target = previous + change
                if not lower <= target <= upper:
                    continue
                transitions += 1
                proposed = (current_cost + incremental, current_stress + extra_stress)
                incumbent = next_costs.get(target)
                if (
                    incumbent is None
                    or proposed[0] < incumbent[0] - COST_TIE_DKK
                    or (
                        abs(proposed[0] - incumbent[0]) <= COST_TIE_DKK
                        and proposed[1] < incumbent[1]
                    )
                ):
                    next_costs[target] = proposed
                    predecessors[target] = (previous, dispatch)
        if not next_costs:
            raise InfeasibleCandidate("horizon:no_feasible_dispatch")
        costs = next_costs
        trace.append(predecessors)
    objectives = {
        state: cost[0] - terminal_value * (initial_energy + state * SOC_STEP_DC_KWH)
        for state, cost in costs.items()
    }
    minimum_objective = min(objectives.values())
    # Treat only numerical cost ties as equal; then avoid unnecessary charging.
    best = min(
        (
            state
            for state in costs
            if objectives[state] <= minimum_objective + COST_TIE_DKK
        ),
        key=lambda state: (costs[state][1], abs(state), objectives[state]),
    )
    selected = []
    current = best
    for predecessors in reversed(trace):
        previous, dispatch = predecessors[current]
        selected.append(dispatch)
        current = previous
    selected.reverse()
    if current != 0:
        raise InfeasibleCandidate("horizon:trace_inconsistent")
    dispatches = tuple(selected)
    verified = simulate_candidate(calibrated, quarters, dispatches)
    return HorizonResult(
        candidate=verified,
        reference=reference,
        dispatches=dispatches,
        terminal_value_dkk_per_kwh_dc=terminal_value,
        evaluated_transitions=transitions,
    )


def optimize_horizon(
    plant: Plant,
    quarters: tuple[Quarter, ...],
    *,
    terminal_value_override: float | None = None,
    pv_underprediction_kwh: float | None = None,
    enable_pv_headroom: bool = True,
    audit_forbid_first_action: str | None = None,
    audit_force_first_pv_curtail: bool = False,
    audit_forbid_grid_charge_prefix: int = 0,
    grid_charge_already_active: bool = False,
    load_risk_accuracy: dict | None = None,
) -> HorizonResult:
    """Primary HA dry-run optimizer: continuous flow, no 0.1 kWh SOC grid.

    Keep optimize_horizon_discrete for comparison on identical inputs only.
    The returned continuous dispatch is independently checked for every slot.
    """
    from .continuous_optimizer import optimize_continuous

    result = optimize_continuous(
        plant,
        quarters,
        terminal_value_override=terminal_value_override,
        pv_underprediction_kwh=pv_underprediction_kwh,
        enable_pv_headroom=enable_pv_headroom,
        audit_forbid_first_action=audit_forbid_first_action,
        audit_force_first_pv_curtail=audit_force_first_pv_curtail,
        audit_forbid_grid_charge_prefix=audit_forbid_grid_charge_prefix,
    )
    if audit_forbid_first_action is not None or audit_forbid_grid_charge_prefix:
        return result
    from .economic_policy import (
        CHEAP_WINDOW_PRICE_TOLERANCE_DKK_PER_KWH,
        MAX_SPREAD_QUARTERS,
        hedge_load_forecast_risk,
        material_grid_charge,
        spread_grid_charge_over_cheap_window,
    )

    if result.dispatches and result.dispatches[0].grid_to_battery_ac_kwh > 1e-7:
        # Compare the entire inexpensive window, not the first quarter only.
        # A first-quarter veto alone would keep postponing charging forever.
        price = quarters[0].buy_dkk_per_kwh
        window = 0
        for quarter in quarters[:MAX_SPREAD_QUARTERS]:
            if (
                abs(quarter.buy_dkk_per_kwh - price)
                > CHEAP_WINDOW_PRICE_TOLERANCE_DKK_PER_KWH
            ):
                break
            window += 1
        no_cheap_charge = optimize_continuous(
            plant,
            quarters,
            terminal_value_override=terminal_value_override,
            pv_underprediction_kwh=pv_underprediction_kwh,
            enable_pv_headroom=enable_pv_headroom,
            audit_forbid_grid_charge_prefix=window,
        )
        if not material_grid_charge(
            result,
            no_cheap_charge,
            soc_pct=plant.initial_soc_pct,
            already_charging=grid_charge_already_active,
        ):
            result = replace(
                no_cheap_charge,
                economic_policy_reason=(
                    "soc_99_satisfies_grid_charge_target"
                    if plant.initial_soc_pct >= 99.0
                    else "grid_charge_below_materiality_threshold"
                ),
                economic_policy_benefit_dkk=(
                    no_cheap_charge.candidate.objective_dkk
                    - result.candidate.objective_dkk
                ),
            )
        else:
            result = spread_grid_charge_over_cheap_window(plant, quarters, result)
    if load_risk_accuracy is not None:
        result = hedge_load_forecast_risk(
            plant, quarters, result, load_risk_accuracy
        )
    return result
