"""Risk-priced, receding-horizon strategy selection (Energy Co-Pilot 2.0).

Choose between whole-horizon, independently verified dispatches. The selected
dispatch is calculated on the NOMINAL physical forecast. Forecast uncertainty
is costed separately, without inventing consumption or PV generation in HA.
All alternative charging decisions are reoptimized, never edited in isolation.

Scenario weights are planning assumptions, NOT learned probabilities.
Each real quarter is replanned using its latest measured SOC and forecasts.
"""

from dataclasses import dataclass, replace
from math import isfinite, sqrt

from .continuous_optimizer import optimize_continuous
from .planner import DEGRADATION_DKK_PER_KWH_DC, MIN_SOC, InfeasibleCandidate
from .pv_headroom import headroom_schedule

LOAD_RISK_WEIGHT = 0.65
PV_UPSIDE_WEIGHT = 0.55
MIN_NEW_CHARGE_BENEFIT_DKK = 0.10
MAX_EXTRA_LOAD_RESERVE_SOC_PP = 15.0
MAX_PV_OPTION_SOC_PP = 20.0


@dataclass(frozen=True)
class Peak:
    start: int
    end: int
    price_dkk_kwh: float
    cheap_dkk_kwh: float
    risk_dc_kwh: float


def _peaks(plant, quarters, accuracy):
    """Material price peaks by local date; no fabricated future tariffs."""
    from zoneinfo import ZoneInfo

    zone = ZoneInfo("Europe/Copenhagen")
    dates = {}
    for i, q in enumerate(quarters):
        dates.setdefault(q.start.astimezone(zone).date(), []).append(i)
    result = []
    for indexes in dates.values():
        # A peak matters only if some lower-price charging opportunity
        # exists inside the already published horizon.
        candidates = [
            i for i in indexes if i >= 4 and quarters[i].buy_dkk_per_kwh >= 3.0
        ]
        if not candidates:
            continue
        i = max(candidates, key=lambda k: quarters[k].buy_dkk_per_kwh)
        earlier = max(0, i - 72)
        previous = [q.buy_dkk_per_kwh for q in quarters[earlier:i]]
        if not previous:
            continue
        cheap = min(previous)
        high = quarters[i].buy_dkk_per_kwh
        if high < max(3.0, cheap * 1.3, cheap + 0.85):
            continue
        threshold = max(3.0, cheap * 1.25, cheap + 0.75)
        start = i
        while start > 0 and quarters[start - 1].buy_dkk_per_kwh >= threshold:
            start -= 1
        end = i + 1
        while end < len(quarters) and quarters[end].buy_dkk_per_kwh >= threshold:
            end += 1
        if (end - start) < 4:
            continue
        if result and start <= result[-1].end:
            continue
        try:
            count = int(accuracy.get("peak_hours_evaluated") or 0)
            overall = int(accuracy.get("hours_evaluated") or 0)
            bias = float(accuracy.get("peak_bias_kwh_per_hour") or 0)
            p75 = float(accuracy.get("peak_positive_underprediction_p75_kwh_per_hour") or 0)
        except (TypeError, ValueError):
            count = overall = 0
            bias = p75 = 0.0
        risk = 0.0
        if count >= 16 and overall >= 96 and all(isfinite(x) for x in (bias, p75)):
            h = min(8.0, (end - start) / 4.0)
            risk = (max(0.0, -bias) * h + 0.5 * max(0.0, p75) * sqrt(h))
            risk /= plant.eta_battery_to_ac
            risk = min(
                risk, plant.battery_capacity_dc_kwh * MAX_EXTRA_LOAD_RESERVE_SOC_PP / 100
                + (plant.battery_capacity_dc_kwh * 0.2)
            )
        result.append(Peak(start, end, high, cheap, risk))
    return tuple(result[:3])


def _pv_option(plant, quarters, accuracy, pv_underprediction):
    """Upside scenario: stronger PV and lower house demand at daylight.

    The upside is a deterministic stress test with explicit coefficients,
    not a weather model or a calibrated probability.
    """
    try:
        mae = float((accuracy or {}).get("mae_kwh_per_hour") or 0)
    except (TypeError, ValueError):
        mae = 0.0
    mae = min(2.0, max(0.0, mae)) if isfinite(mae) else 0.0
    empirical = (
        min(0.45, max(0.0, float(pv_underprediction)))
        if pv_underprediction is not None
        else 0.0
    )
    extra = []
    for q in quarters:
        if q.pv_dc_kwh < 0.01:
            extra.append(0.0)
            continue
        nominal = max(0.0, q.pv_dc_kwh - q.home_ac_kwh / plant.eta_pv_to_ac)
        upside = max(0.0, q.pv_dc_kwh * 1.45 + empirical
                     - max(0.0, q.home_ac_kwh - 0.5 * mae / 4)
                     / plant.eta_pv_to_ac)
        extra.append(max(0.0, upside - nominal) * plant.eta_pv_to_battery)
    return tuple(extra)


def _hard_pv_reserve(plant, quarters, upside):
    """Candidate capacity constraints, not a permanent inverter SOC ceiling."""
    capacity = plant.battery_capacity_dc_kwh
    cap = capacity * MAX_PV_OPTION_SOC_PP / 100
    return {
        i: min(cap, sum(upside[i : i + 12]))
        for i, q in enumerate(quarters)
        if q.pv_dc_kwh > 0.015 and sum(upside[i : i + 12]) > 0.03
    }


def _score(plant, quarters, candidate, peaks, upside):
    """Nominal cost plus two independently reported scenario loss estimates."""
    capacity = plant.battery_capacity_dc_kwh
    load_loss = 0.0
    for peak in peaks:
        # Fully available energy in the expensive period is NOT throttled.
        minimum_soc = min(
            q.soc_end_pct for q in candidate.candidate.quarters[peak.start : peak.end]
        )
        available_dc = max(0.0, (minimum_soc - MIN_SOC) * capacity / 100)
        shortfall = max(0.0, peak.risk_dc_kwh - available_dc)
        marginal = max(
            0.0,
            peak.price_dkk_kwh * plant.eta_battery_to_ac
            - DEGRADATION_DKK_PER_KWH_DC
            - peak.cheap_dkk_kwh / plant.eta_grid_to_battery,
        )
        load_loss += LOAD_RISK_WEIGHT * shortfall * marginal

    pv_loss = 0.0
    for i, (q, d, outcome, extra) in enumerate(
        zip(quarters, candidate.dispatches, candidate.candidate.quarters, upside, strict=True)
    ):
        if extra <= 0:
            continue
        physical_room = (
            capacity * (100.0 - outcome.soc_start_pct) / 100.0
            - d.pv_to_battery_dc_kwh * plant.eta_pv_to_battery
            - d.grid_to_battery_ac_kwh * plant.eta_grid_to_battery
        )
        lost = max(0.0, extra - max(0.0, physical_room))
        if lost <= 0:
            continue
        # Only reward extra PV that can economically replace expensive grid
        # supply rather than be sold at a similar price.
        future_high = max(x.buy_dkk_per_kwh for x in quarters[i : i + 32])
        sale = (
            q.sell_dkk_per_kwh * plant.eta_pv_to_ac / plant.eta_pv_to_battery
            if q.pv_export_enabled and q.sell_dkk_per_kwh >= 0.40
            else 0.0
        )
        value = max(
            0.0,
            future_high * plant.eta_battery_to_ac
            - DEGRADATION_DKK_PER_KWH_DC - sale
        )
        pv_loss += PV_UPSIDE_WEIGHT * lost * value

    return (
        candidate.candidate.objective_dkk + load_loss + pv_loss,
        round(load_loss, 5),
        round(pv_loss, 5),
    )


def _charge_groups(quarters, dispatches):
    """Whole economic operations, never individual 15-minute micro-gains."""
    active = [i for i, d in enumerate(dispatches) if d.grid_to_battery_ac_kwh > 1e-6]
    groups = []
    for i in active:
        if (
            groups
            and i - groups[-1][-1] <= 4
            and abs(
                quarters[i].buy_dkk_per_kwh - quarters[groups[-1][-1]].buy_dkk_per_kwh
            ) <= 0.02
        ):
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def select_strategy(
    plant,
    quarters,
    *,
    terminal_value,
    load_accuracy=None,
    pv_underprediction=None,
    allow_pv_option=True,
    audit_forbid_first_action=None,
    audit_force_first_pv_curtail=False,
    audit_forbid_grid_charge_prefix=0,
    grid_charge_already_active=False,
):
    """Bounded scenario comparison; every candidate remains a real AC/DC plan.

    The selected plan need not be globally optimal for an unknown future.
    Scenario losses and tested alternatives are explicitly recorded.
    """
    base_args = {
        "terminal_value_override": terminal_value,
        "pv_underprediction_kwh": pv_underprediction,
        "enable_pv_headroom": False,
        "audit_forbid_first_action": audit_forbid_first_action,
        "audit_force_first_pv_curtail": audit_force_first_pv_curtail,
        "audit_forbid_grid_charge_prefix": audit_forbid_grid_charge_prefix,
    }
    base = optimize_continuous(plant, quarters, **base_args)
    if audit_forbid_first_action is not None or audit_forbid_grid_charge_prefix:
        return base

    peaks = _peaks(plant, quarters, load_accuracy or {})
    upside = _pv_option(plant, quarters, load_accuracy, pv_underprediction)
    hard_reserve = _hard_pv_reserve(plant, quarters, upside) if allow_pv_option else {}
    candidates = [("nominal", base, {})]
    trial_count = 1

    def attempt(label, options):
        nonlocal trial_count
        trial_count += 1
        try:
            plan = optimize_continuous(plant, quarters, **base_args, **options)
        except InfeasibleCandidate:
            return
        candidates.append((label, plan, options))

    if hard_reserve:
        attempt("pv_option_headroom", {"minimum_pv_headroom": hard_reserve})
    # Replan purchases later if they can still fill the battery before peak.
    # No fixed 14:00 cutoff: each window is derived from the actual price
    # peak and the 50 A charging rate, and each variant is independently priced.
    for peak in peaks:
        preceding_pv = [
            i for i in range(peak.start)
            if quarters[i].pv_dc_kwh > 0.01
        ]
        if not preceding_pv:
            continue
        first = preceding_pv[0]
        for hours in (3, 2, 1):
            cutoff = max(first, peak.start - 4 * hours)
            excludes = frozenset(range(first, cutoff))
            if excludes:
                attempt(
                    f"wait_for_pv_until_{quarters[cutoff].start.isoformat()}",
                    {"grid_charge_excluded": excludes},
                )
                if hard_reserve:
                    attempt(
                        f"pv_option_wait_until_{quarters[cutoff].start.isoformat()}",
                        {
                            "grid_charge_excluded": excludes,
                            "minimum_pv_headroom": hard_reserve,
                        },
                    )

    for peak in peaks:
        before_soc = base.candidate.quarters[peak.start - 1].soc_end_pct
        minimum_soc = min(
            q.soc_end_pct for q in base.candidate.quarters[peak.start : peak.end]
        )
        available = max(0.0, (minimum_soc - MIN_SOC) * plant.battery_capacity_dc_kwh / 100)
        required = min(
            plant.battery_capacity_dc_kwh * MAX_EXTRA_LOAD_RESERVE_SOC_PP / 100,
            max(0.0, peak.risk_dc_kwh - available),
            plant.battery_capacity_dc_kwh * max(0.0, 100 - before_soc) / 100,
        )
        if required < plant.battery_capacity_dc_kwh * 0.005:
            continue
        # The LP's carry reward is applied only at entry to the expensive
        # period, so all stored energy is usable for peak discharge. Compare
        # resulting physical costs and risk loss, not synthetic reward values.
        target_soc = before_soc + 100 * required / plant.battery_capacity_dc_kwh
        low, high = 0.0, max(4.0, peak.price_dkk_kwh)
        best = None
        for _ in range(7):
            mid = (low + high) / 2.0
            opts = {"peak_entry_reward": {peak.start - 1: mid}}
            trial_count += 1
            try:
                plan = optimize_continuous(plant, quarters, **base_args, **opts)
            except InfeasibleCandidate:
                high = mid
                continue
            soc = plan.candidate.quarters[peak.start - 1].soc_end_pct
            if soc <= target_soc + 0.35:
                best = (plan, opts)
                low = mid
            else:
                high = mid
        if best is not None:
            candidates.append(("load_uncertainty_reserve", *best))
        if hard_reserve:
            attempt(
                "joint_load_and_pv_options",
                {
                    "minimum_pv_headroom": hard_reserve,
                    "peak_entry_reward": {
                        peak.start - 1: min(peak.price_dkk_kwh, 4.0)
                    },
                },
            )

    ordered = sorted(
        (
            (_score(plant, quarters, plan, peaks, upside), label, plan, options)
            for label, plan, options in candidates
        ),
        key=lambda row: (row[0][0], row[2].candidate.objective_dkk),
    )
    nominal = next(row for row in ordered if row[1] == "nominal")
    picked = ordered[0]
    if nominal[0][0] - picked[0][0] < MIN_NEW_CHARGE_BENEFIT_DKK:
        picked = nominal

    # Whole-operation materiality: a later 0.1 kWh charge is not exempt just
    # because it is not in the first quarter. Re-optimize if this entire
    # campaign is forbidden; reject only when its benefit is <10 oere.
    dropped = []
    _, label, chosen, options = picked
    for group in _charge_groups(quarters, chosen.dispatches):
        forbidden = frozenset(options.get("grid_charge_excluded", ())) | frozenset(
            range(group[0], group[-1] + 1)
        )
        changed = {**options, "grid_charge_excluded": forbidden}
        trial_count += 1
        try:
            alternative = optimize_continuous(plant, quarters, **base_args, **changed)
        except InfeasibleCandidate:
            continue
        proposed = _score(plant, quarters, alternative, peaks, upside)
        existing = _score(plant, quarters, chosen, peaks, upside)
        benefit = proposed[0] - existing[0]
        if benefit < (
            0.05 if grid_charge_already_active else MIN_NEW_CHARGE_BENEFIT_DKK
        ):
            chosen = alternative
            options = changed
            dropped.append(
                {
                    "start_utc": quarters[group[0]].start.isoformat(),
                    "energy_ac_kwh": round(
                        sum(picked[2].dispatches[i].grid_to_battery_ac_kwh for i in group), 4
                    ),
                    "benefit_dkk": round(benefit, 5),
                }
            )
    physical = _score(plant, quarters, chosen, peaks, upside)
    baseline_score = nominal[0]
    peak_evidence = []
    for peak in peaks:
        actual_soc = chosen.candidate.quarters[peak.start - 1].soc_end_pct
        nominal_soc = base.candidate.quarters[peak.start - 1].soc_end_pct
        peak_evidence.append(
            {
                "start_utc": quarters[peak.start].start.isoformat(),
                "end_utc": quarters[peak.end - 1].end.isoformat(),
                "high_price_dkk_kwh": round(peak.price_dkk_kwh, 3),
                "nominal_entry_soc_pct": round(nominal_soc, 2),
                "planned_entry_soc_pct": round(actual_soc, 2),
                "additional_entry_soc_pp": round(actual_soc - nominal_soc, 2),
            }
        )
    proof = {
        "status": "scenario_selected",
        "method": "v2_joint_scenario_receding_horizon_unverified",
        "selection": label,
        "scenarios": {
            "nominal_weight": 1.0,
            "load_underprediction_loss_weight": LOAD_RISK_WEIGHT,
            "pv_upside_loss_weight": PV_UPSIDE_WEIGHT,
            "weights_are_calibrated_probabilities": False,
            "pv_optimistic_scenario": "pv_1.45x_and_home_minus_0.5_mae",
        },
        "candidate_count": len(candidates),
        "solver_calls": trial_count,
        "nominal_objective_dkk": round(base.candidate.objective_dkk, 4),
        "selected_objective_dkk": round(chosen.candidate.objective_dkk, 4),
        "nominal_risk_adjusted_dkk": round(baseline_score[0], 4),
        "selected_risk_adjusted_dkk": round(physical[0], 4),
        "estimated_risk_reduction_dkk": round(baseline_score[0] - physical[0], 4),
        "load_risk_cost_dkk": physical[1],
        "pv_upside_risk_cost_dkk": physical[2],
        "peak_evidence": peak_evidence,
        "pv_option_reserved_max_dc_kwh": round(max(hard_reserve.values(), default=0), 4),
        "minor_charges_rejected": dropped,
        "alternative_scores_dkk": [
            {
                "strategy": row[1],
                "risk_adjusted_dkk": round(row[0][0], 4),
                "nominal_objective_dkk": round(row[2].candidate.objective_dkk, 4),
            }
            for row in ordered[:12]
        ],
        "tou_feasibility": "quarterly_rewrite_requires_live_validation",
    }
    # Diagnostic legacy fields retain a meaningful meaning without the
    # retired no_idle_prepeak_window veto or its post-hoc charge insertion.
    legacy = {
        "status": "integrated_in_v2_scenario_selection",
        "method": "v2_joint_scenario_receding_horizon_unverified",
        "peak_evidence": peak_evidence,
        "risk_weight_assumed": LOAD_RISK_WEIGHT,
        "applied_extra_soc_points": round(
            max((row["additional_entry_soc_pp"] for row in peak_evidence), default=0), 2
        ),
    }
    return replace(
        chosen,
        method=chosen.method + "_v2_joint_scenario",
        evaluated_transitions=chosen.evaluated_transitions + trial_count,
        pv_headroom=(
            headroom_schedule(plant, quarters, pv_underprediction)
            if allow_pv_option
            else ()
        ),
        pv_headroom_enabled=allow_pv_option,
        load_risk_policy=legacy,
        robust_policy=proof,
    )
