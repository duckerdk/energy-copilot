"""Economic materiality and low-rate charging policy for whole-horizon plans.

Numerical precision remains untouched. The accepted thresholds are *decision*
thresholds, not rounding of electricity prices or energy conservation inputs.
Only validated full-horizon alternatives can replace the original dispatch.
"""

from dataclasses import replace

from .planner import Dispatch, InfeasibleCandidate, Plant, simulate_candidate

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
        without_first_grid_charge.candidate.objective_dkk
        - base.candidate.objective_dkk
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
    Never move energy before its original acquisition: each new prefix must
    have no more charged energy than the original prefix. This ensures no extra
    battery SOC at intermediate points. Reject on validator failure or a
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
        if abs(q.buy_dkk_per_kwh - start_price) > CHEAP_WINDOW_PRICE_TOLERANCE_DKK_PER_KWH:
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
    min_ac_kwh_per_quarter = plant.battery_voltage_v / (4000 * plant.eta_grid_to_battery)
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

    # Only reallocate energy from earlier to later quarters. When original
    # charging is not front-loaded enough, skip rather than advance it.
    accumulated_old = 0.0
    accumulated_new = 0.0
    smoothed = []
    for old in original:
        accumulated_old += old
        new = min(equal_ac, max(0.0, accumulated_old - accumulated_new))
        accumulated_new += new
        smoothed.append(new)
    remaining = total - sum(smoothed)
    if remaining > 1e-7:
        # A narrow initial credit cannot be reconciled with equal rates within
        # the window; preserve the original plan, no heuristic compensation.
        return result
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
    if checked.objective_dkk > result.candidate.objective_dkk + CHANGE_STRATEGY_BENEFIT_DKK + 1e-8:
        return result
    return replace(
        result,
        candidate=checked,
        dispatches=tuple(dispatches),
        method=result.method + "_low_price_charge_spread",
    )
