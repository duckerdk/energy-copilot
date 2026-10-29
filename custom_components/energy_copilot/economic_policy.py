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


def hedge_load_forecast_risk(plant, quarters, result, load_accuracy):
    """Buy a bounded insurance reserve before a costly period when load is biased low.

    Preserve the *nominal* home forecast and full physical energy balances:
    this adds only explicitly costed, feasible grid-charge energy. Neither a
    speculative high load nor a fictional battery discharge is injected into
    the displayed dispatch. The risk weight is an assumption, not an inferred
    outage probability.
    """
    if not isinstance(load_accuracy, dict):
        return result
    try:
        count = int(load_accuracy.get("hours_evaluated") or 0)
        mae = float(load_accuracy["mae_kwh_per_hour"])
        bias = float(load_accuracy["bias_kwh_per_hour"])
    except (TypeError, ValueError, KeyError):
        return result
    if count < 96 or not all(isfinite(v) for v in (mae, bias)) or mae <= 0:
        return replace(result, load_risk_policy={"status": "insufficient_evidence"})
    if len(quarters) < 8:
        return replace(result, load_risk_policy={"status": "short_horizon"})

    # Find the first economically significant, contiguous higher-price period.
    # The reference is the cheapest previously published quarter, never an
    # invented future or a price from outside the optimization horizon.
    start = None
    floor = quarters[0].buy_dkk_per_kwh
    for i in range(1, len(quarters) - 3):
        price = quarters[i].buy_dkk_per_kwh
        threshold = max(3.0, floor * 1.35, floor + 0.70)
        if price >= threshold:
            start = i
            break
        floor = min(floor, price)
    if start is None:
        return replace(result, load_risk_policy={"status": "no_expensive_window"})

    end = start
    while (
        end < len(quarters)
        and end - start < 32
        and quarters[end].buy_dkk_per_kwh >= max(2.9, floor * 1.25)
    ):
        end += 1
    duration_hours = (end - start) / 4.0
    if duration_hours < 1.0:
        return replace(result, load_risk_policy={"status": "brief_price_peak"})

    # Bias is forecast-minus-observed: negative bias means underforecast.
    # Include a bounded MAE-dependent allowance for unpredictable deviation.
    stress_ac = max(0.0, -bias) * duration_hours + 0.5 * mae * sqrt(
        duration_hours
    )
    stress_dc = stress_ac / plant.eta_battery_to_ac
    capacity = plant.battery_capacity_dc_kwh
    energy_at_peak = (
        result.candidate.quarters[start - 1].soc_end_pct / 100 * capacity
    )
    available_at_peak = max(0.0, capacity - energy_at_peak)
    # Only cover stress above the nominal minimum-SOC headroom expected to
    # remain after the expensive window. Do not store an arbitrary SOC target.
    leftover = (
        min(q.soc_end_pct for q in result.candidate.quarters[start:end])
        - 20.0
    ) * capacity / 100.0
    desired_dc = min(
        max(0.0, stress_dc - max(0.0, leftover)),
        max(0.0, available_at_peak),
        capacity * 0.25,
    )
    evidence = {
        "status": "no_reserve_needed",
        "source": "seven_day_out_of_sample_load_holdout_unverified",
        "hours_evaluated": count,
        "forecast_mae_kwh_per_hour": round(mae, 4),
        "forecast_bias_kwh_per_hour": round(bias, 4),
        "peak_start_utc": quarters[start].start.isoformat(),
        "peak_end_utc": quarters[end - 1].end.isoformat(),
        "peak_buy_dkk_per_kwh": max(
            q.buy_dkk_per_kwh for q in quarters[start:end]
        ),
        "risk_stress_ac_kwh": round(stress_ac, 4),
        "candidate_extra_dc_kwh": round(desired_dc, 4),
        "actual_extra_dc_kwh": 0.0,
        "estimated_extra_cost_dkk": 0.0,
        "risk_weight_assumed": 0.65,
        "probability_calibrated": False,
    }
    if desired_dc < 0.05:
        return replace(result, load_risk_policy=evidence)

    # Do not grid-charge while PV is being stored or sold, nor during
    # battery discharge. Prefer a coherent multi-quarter low-price window:
    # charging current may only be deliberately spread, never set to match
    # instantaneous forecast power.
    eligible = [
        i
        for i in range(max(0, start - 24), start)
        if result.dispatches[i].pv_to_battery_dc_kwh < 1e-7
        and result.dispatches[i].pv_to_export_dc_kwh < 1e-7
        and result.dispatches[i].battery_to_home_dc_kwh < 1e-7
        and result.dispatches[i].grid_to_battery_ac_kwh < 1e-7
    ]
    if not eligible:
        return replace(result, load_risk_policy={**evidence, "status": "no_safe_charge_window"})
    lowest = min(quarters[i].buy_dkk_per_kwh for i in eligible)
    chosen = [
        i for i in eligible
        if quarters[i].buy_dkk_per_kwh <= lowest + 0.01 + 1e-10
    ]
    # An isolated current target is not a time-spreading campaign.
    if len(chosen) < 2:
        return replace(result, load_risk_policy={**evidence, "status": "no_spread_window"})
    peak_price = evidence["peak_buy_dkk_per_kwh"]
    # This is a bounded risk aversion coefficient, NOT a measured probability.
    value_dc = 0.65 * peak_price * plant.eta_battery_to_ac - 0.40
    if value_dc <= lowest / plant.eta_grid_to_battery + 0.01:
        return replace(result, load_risk_policy={**evidence, "status": "insurance_not_economic"})

    # Equal-price eligible periods share the extra energy evenly rather than
    # charging in BOOST at the start. Never exceed available charging limits.
    quarter_dc_cap = (
        plant.battery_voltage_v
        * min(plant.charge_limit_a, plant.grid_charge_limit_a)
        / 4000.0
    )
    target_dc = min(desired_dc, len(chosen) * quarter_dc_cap)
    if target_dc < 0.05:
        return replace(result, load_risk_policy={**evidence, "status": "rate_capacity_insufficient"})
    calibrated = plant.__class__(
        **{
            **vars(plant),
            "terminal_value_dkk_per_kwh_dc": result.terminal_value_dkk_per_kwh_dc,
        }
    )

    def with_extra(fraction):
        extra_dc = target_dc * fraction / len(chosen)
        modified = list(result.dispatches)
        for i in chosen:
            modified[i] = replace(
                modified[i],
                grid_to_battery_ac_kwh=extra_dc / plant.eta_grid_to_battery,
            )
        checked = simulate_candidate(calibrated, quarters, tuple(modified))
        return checked, tuple(modified)

    # Independent simulator is authoritative for SOC and AC/DC feasibility.
    low, high = 0.0, 1.0
    accepted = None
    for _ in range(24):
        mid = (low + high) / 2
        try:
            accepted = with_extra(mid)
        except InfeasibleCandidate:
            high = mid
        else:
            low = mid
    if low < 1e-4 or accepted is None:
        return replace(result, load_risk_policy={**evidence, "status": "not_physically_feasible"})
    checked, dispatches = accepted
    extra_dc = target_dc * low
    extra_cost = checked.objective_dkk - result.candidate.objective_dkk
    # The existing terminal value has already been credited in the candidate;
    # insurance must pay for its *additional* expected avoided high-price loss.
    incremental_risk_value = max(
        0.0, value_dc - result.terminal_value_dkk_per_kwh_dc
    ) * extra_dc
    if extra_cost > incremental_risk_value + 0.01:
        return replace(result, load_risk_policy={**evidence, "status": "insurance_not_economic"})

    return replace(
        result,
        candidate=checked,
        dispatches=dispatches,
        method=result.method + "_holdout_load_risk_guard",
        load_risk_policy={
            **evidence,
            "status": "applied",
            "actual_extra_dc_kwh": round(extra_dc, 4),
            "estimated_extra_cost_dkk": round(extra_cost, 4),
            "risk_value_above_terminal_dkk": round(incremental_risk_value, 4),
            "charge_start_utc": quarters[chosen[0]].start.isoformat(),
            "charge_end_utc": quarters[chosen[-1]].end.isoformat(),
            "spread_quarters": len(chosen),
        },
    )
