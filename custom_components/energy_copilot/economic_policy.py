"""Economic materiality and low-rate charging policy for whole-horizon plans.

Numerical precision remains untouched. The accepted thresholds are *decision*
thresholds, not rounding of electricity prices or energy conservation inputs.
Only validated full-horizon alternatives can replace the original dispatch.
"""

from dataclasses import replace
from math import isfinite, sqrt

from .planner import InfeasibleCandidate, Plant, simulate_candidate

ECONOMIC_TIE_DKK = 0.01
START_GRID_CHARGE_BENEFIT_DKK = 0.10
CHANGE_STRATEGY_BENEFIT_DKK = 0.05
SOC_TARGET_TOLERANCE_PCT = 1.0
CHEAP_WINDOW_PRICE_TOLERANCE_DKK_PER_KWH = 0.01
MAX_SPREAD_QUARTERS = 20


def material_grid_charge(
    base, without_first_grid_charge, *, soc_pct, already_charging=False
):
    """Retain first-quarter grid charging only if it has a material benefit.

    Comparing *whole* re-optimized plans avoids rejecting a series of small
    individually valuable quarters whose combined benefit is significant.
    A nearly full battery already meets a 100% requested charge target.
    """
    if soc_pct >= 100.0 - SOC_TARGET_TOLERANCE_PCT:
        return False
    saved_dkk = (
        without_first_grid_charge.candidate.objective_dkk - base.candidate.objective_dkk
    )
    threshold = (
        CHANGE_STRATEGY_BENEFIT_DKK
        if already_charging
        else START_GRID_CHARGE_BENEFIT_DKK
    )
    return saved_dkk >= threshold - 1e-8


def spread_grid_charge_over_cheap_window(plant, quarters, result):
    """Delay front-loaded grid charging across an equally cheap contiguous window.

    Keep the total scheduled AC energy and all PV/discharge flows unchanged.
    Movement within the same published low-price window is allowed in both
    directions, but must pass the independent full-horizon physical validator. Reject on validator failure or a
    material cost penalty. Do not invent a window beyond published prices.
    """
    if not quarters or not result.dispatches:
        return result
    dispatches = list(result.dispatches)
    if dispatches[0].grid_to_battery_ac_kwh <= 1e-7:
        return result
    start_price = quarters[0].buy_dkk_per_kwh
    end = 0
    for q, dispatch in zip(quarters[:MAX_SPREAD_QUARTERS], dispatches, strict=False):
        if (
            abs(q.buy_dkk_per_kwh - start_price)
            > CHEAP_WINDOW_PRICE_TOLERANCE_DKK_PER_KWH
        ):
            break
        # Avoid changing battery priorities in a PV-producing or discharge slot.
        if (
            q.pv_dc_kwh > 0.01
            or dispatch.pv_to_battery_dc_kwh > 1e-7
            or dispatch.battery_to_home_dc_kwh > 1e-7
            or dispatch.pv_to_export_dc_kwh > 1e-7
        ):
            break
        end += 1
    if end < 4:
        return result
    original = [d.grid_to_battery_ac_kwh for d in dispatches[:end]]
    total = sum(original)
    if total <= 1e-7:
        return result
    # There is no benefit to altering negligible low-current dispatches.
    min_ac_kwh_per_quarter = plant.battery_voltage_v / (
        4000 * plant.eta_grid_to_battery
    )
    equal_ac = total / end
    if equal_ac < min_ac_kwh_per_quarter:
        return result
    max_ac = (
        min(plant.charge_limit_a, plant.grid_charge_limit_a)
        * plant.battery_voltage_v
        / (4000 * plant.eta_grid_to_battery)
    )
    if equal_ac > max_ac + 1e-7:
        return result

    # Equal prices justify charging earlier or later inside this same window.
    # The independent whole-horizon validator rejects SOC, current or AC/DC
    # violations. No shift is allowed outside the published cheap window.
    smoothed = [equal_ac] * end
    smoothed[-1] += total - sum(smoothed)
    if max(abs(a - b) for a, b in zip(original, smoothed, strict=True)) < 1e-6:
        return result
    for i, new in enumerate(smoothed):
        previous = dispatches[i]
        dispatches[i] = replace(previous, grid_to_battery_ac_kwh=max(0.0, new))
    verified_plant = Plant(
        **{
            **vars(plant),
            "terminal_value_dkk_per_kwh_dc": result.terminal_value_dkk_per_kwh_dc,
        }
    )
    try:
        checked = simulate_candidate(verified_plant, quarters, tuple(dispatches))
    except InfeasibleCandidate:
        return result
    if (
        checked.objective_dkk
        > result.candidate.objective_dkk + CHANGE_STRATEGY_BENEFIT_DKK + 1e-8
    ):
        return result
    return replace(
        result,
        candidate=checked,
        dispatches=tuple(dispatches),
        method=result.method + "_low_price_charge_spread",
    )


def hedge_load_forecast_risk(plant, quarters, plan, accuracy):
    """Price a bounded SOC reserve against observed household underforecast.

    The original forecast and its dispatch stay visible. Only real, independently
    validated additional grid charging is appended in a multi-quarter cheap
    window; nominal discharge is not invented, shifted or throttled.
    The risk factor is a documented policy assumption, not a calibrated
    probability. If evidence or a charge window is missing, keep the plan.
    """
    if not isinstance(accuracy, dict):
        return plan

    def evidence(status, **details):
        return replace(
            plan,
            load_risk_policy={
                "status": status,
                "method": "seven_day_holdout_peak_load_hedge_v1",
                "max_extra_soc_points": 15.0,
                **details,
            },
        )

    try:
        hours = int(accuracy.get("hours_evaluated") or 0)
        peak_hours = int(accuracy.get("peak_hours_evaluated") or 0)
        bias = float(accuracy["peak_bias_kwh_per_hour"])
        p75 = float(accuracy["peak_positive_underprediction_p75_kwh_per_hour"])
    except ValueError, TypeError, KeyError:
        return evidence("insufficient_history")
    if hours < 96 or peak_hours < 16 or not all(isfinite(v) for v in (bias, p75)):
        return evidence("insufficient_history")
    if len(quarters) < 8:
        return evidence("horizon_too_short")

    prices = [q.buy_dkk_per_kwh for q in quarters]
    max_price_index = max(range(len(prices)), key=prices.__getitem__)
    if max_price_index < 4:
        return evidence("no_future_peak")
    earlier_min = min(prices[:max_price_index])
    price_threshold = max(3.0, earlier_min + 0.9, earlier_min * 1.35)
    if prices[max_price_index] < price_threshold:
        return evidence("no_material_price_peak")
    start = next(
        (i for i in range(max_price_index + 1) if prices[i] >= price_threshold),
        None,
    )
    if start is None or start < 2:
        return evidence("no_charge_window")
    end = start
    while end < len(quarters) and end - start < 32 and prices[end] >= price_threshold:
        end += 1
    duration = (end - start) / 4.0
    if duration < 1.0:
        return evidence("peak_too_short")

    peak_prices = sorted(prices[start:end])
    representative_peak = peak_prices[
        min(len(peak_prices) - 1, int(0.75 * len(peak_prices)))
    ]
    # Negative bias = consumption was higher than forecast. The P75 error
    # captures non-systematic deviations without multiplying every hour's
    # worst-case error linearly across the entire evening.
    risk_ac = max(0.0, -bias) * duration + 0.5 * max(0.0, p75) * sqrt(duration)
    capacity = plant.battery_capacity_dc_kwh
    risk_dc = risk_ac / plant.eta_battery_to_ac
    nominal_min = min(q.soc_end_pct for q in plan.candidate.quarters[start:end])
    existing_buffer_dc = max(0.0, (nominal_min - 20.0) * capacity / 100.0)
    peak_soc = plan.candidate.quarters[start - 1].soc_end_pct
    planned_extra_dc = min(
        capacity * 0.15,
        max(0.0, risk_dc - existing_buffer_dc),
        max(0.0, capacity * (100.0 - peak_soc) / 100.0),
    )
    details = {
        "holdout_hours": hours,
        "peak_holdout_hours": peak_hours,
        "peak_bias_kwh_per_hour": round(bias, 4),
        "peak_positive_p75_kwh_per_hour": round(p75, 4),
        "risk_demand_ac_kwh": round(risk_ac, 4),
        "nominal_min_peak_soc_pct": round(nominal_min, 2),
        "desired_extra_soc_points": round(100 * planned_extra_dc / capacity, 2),
        "peak_start_utc": quarters[start].start.isoformat(),
        "peak_end_utc": quarters[end - 1].end.isoformat(),
        "peak_price_p75_dkk_per_kwh": round(representative_peak, 4),
        "extra_grid_charge_ac_kwh": 0.0,
        "applied_extra_soc_points": 0.0,
        "nominal_forecast_unchanged": True,
        "risk_weight_assumed": 0.65,
    }
    if planned_extra_dc < capacity * 0.005:
        return evidence("reserve_already_sufficient", **details)

    # Only a deliberate charging campaign qualifies for adjusting current:
    # no simultaneous PV export, PV-to-battery, battery discharge or existing
    # grid-charge action in the chosen quarters.
    eligible = [
        i
        for i in range(max(0, start - 24), start)
        if plan.dispatches[i].pv_to_battery_dc_kwh < 1e-7
        and plan.dispatches[i].pv_to_export_dc_kwh < 1e-7
        and plan.dispatches[i].battery_to_home_dc_kwh < 1e-7
        and plan.dispatches[i].grid_to_battery_ac_kwh < 1e-7
    ]
    if len(eligible) < 2:
        return evidence("no_idle_prepeak_window", **details)
    cheapest = min(prices[i] for i in eligible)
    cheap = [i for i in eligible if prices[i] <= cheapest + 0.01 + 1e-8]
    blocks = []
    for i in cheap:
        if blocks and blocks[-1][-1] + 1 == i:
            blocks[-1].append(i)
        else:
            blocks.append([i])
    blocks = [block for block in blocks if len(block) >= 2]
    if not blocks:
        return evidence("no_contiguous_spread_window", **details)
    chosen = min(
        blocks,
        key=lambda block: (
            sum(prices[i] for i in block) / len(block),
            -len(block),
            -block[-1],
        ),
    )
    dc_per_quarter_max = (
        plant.battery_voltage_v
        * min(plant.charge_limit_a, plant.grid_charge_limit_a)
        / 4000.0
    )
    extra_dc = min(planned_extra_dc, len(chosen) * dc_per_quarter_max)
    if extra_dc < capacity * 0.005:
        return evidence("insufficient_charge_capacity", **details)

    # One energy unit charged now can avoid buying at the 75th-percentile
    # evening price, with a non-calibrated 0.65 risk weight. Existing
    # terminal-energy credit is already in the nominal objective.
    risk_value_dc = 0.65 * (representative_peak * plant.eta_battery_to_ac - 0.40)
    if risk_value_dc <= cheapest / plant.eta_grid_to_battery + 0.01:
        return evidence("reserve_not_economic", **details)

    calibrated = replace(
        plant,
        terminal_value_dkk_per_kwh_dc=plan.terminal_value_dkk_per_kwh_dc,
    )

    def validate(fraction):
        per_quarter_dc = extra_dc * fraction / len(chosen)
        dispatches = list(plan.dispatches)
        for i in chosen:
            dispatches[i] = replace(
                dispatches[i],
                grid_to_battery_ac_kwh=(per_quarter_dc / plant.eta_grid_to_battery),
            )
        accepted = simulate_candidate(calibrated, quarters, tuple(dispatches))
        return accepted, tuple(dispatches)

    # Battery headroom may be tighter at intermediate times than at the
    # peak start; shrink only to a physically verified feasible energy.
    low, high = 0.0, 1.0
    feasible = None
    for _ in range(24):
        mid = (low + high) / 2.0
        try:
            verified = validate(mid)
        except InfeasibleCandidate:
            high = mid
        else:
            low = mid
            feasible = verified
    if feasible is None or extra_dc * low < capacity * 0.005:
        return evidence("no_physical_headroom", **details)
    candidate, dispatches = feasible
    stored_dc = extra_dc * low
    extra_nominal_cost = candidate.objective_dkk - plan.candidate.objective_dkk
    risk_premium_dkk = (risk_value_dc - plan.terminal_value_dkk_per_kwh_dc) * stored_dc
    if extra_nominal_cost > risk_premium_dkk + 0.01:
        return evidence("reserve_not_economic", **details)

    return replace(
        plan,
        candidate=candidate,
        dispatches=dispatches,
        method=plan.method + "_load_risk_hedge",
        load_risk_policy={
            **details,
            "status": "applied",
            "applied_extra_soc_points": round(stored_dc * 100 / capacity, 2),
            "extra_grid_charge_ac_kwh": round(stored_dc / plant.eta_grid_to_battery, 4),
            "extra_nominal_objective_dkk": round(extra_nominal_cost, 4),
            "estimated_avoided_risk_dkk": round(risk_premium_dkk, 4),
            "charge_start_utc": quarters[chosen[0]].start.isoformat(),
            "charge_end_utc": quarters[chosen[-1]].end.isoformat(),
            "spread_quarters": len(chosen),
        },
    )
