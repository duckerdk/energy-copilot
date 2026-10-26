"""Risk-aware value of battery headroom for PV forecast upside (dry-run).

This is an explicit bounded scenario, not a fixed SOC ceiling or a measured
probability distribution. It values possible extra PV while Solar Sell is OFF.
It does not use an observation once at the same time as its forecast.
"""

from dataclasses import dataclass

from .planner import DEGRADATION_DKK_PER_KWH_DC, PV_EXPORT_MIN_DKK_PER_KWH


@dataclass(frozen=True)
class Headroom:
    target_dc_kwh: float = 0.0
    opportunity_dkk_per_kwh_dc_per_quarter: float = 0.0
    potential_extra_dc_kwh: float = 0.0


def headroom_schedule(plant, quarters, observed_pv_upside_kwh=None):
    """Price a rolling 2-hour buffer based on PV upside and future home value.

    PV positive forecast limits exposure to daylight and prevents hypothetical
    night charging penalties. If 16 real observed quarters are available,
    their underprediction p75 supplements a forecast-relative 35% uncertainty
    band, rather than asserting that curtailed PV was physically observed.
    Opportunity costs are spread across eight 15-minute quarters so storing
    one DC kWh for an entire sunny window is priced only once per window.
    """
    capacity = plant.battery_capacity_dc_kwh
    verified = observed_pv_upside_kwh is not None
    empirical = max(0.0, float(observed_pv_upside_kwh)) if verified else 0.0
    periods = []
    for i, q in enumerate(quarters):
        if q.pv_dc_kwh <= 0.01 or (
            q.pv_export_enabled and q.sell_dkk_per_kwh >= PV_EXPORT_MIN_DKK_PER_KWH
        ):
            periods.append(Headroom())
            continue
        expected_extra = 0.0
        for ahead in quarters[i : i + 8]:
            if ahead.pv_dc_kwh <= 0.01 or (
                ahead.pv_export_enabled
                and ahead.sell_dkk_per_kwh >= PV_EXPORT_MIN_DKK_PER_KWH
            ):
                continue
            forecast_upside = min(
                0.45,
                max(
                    0.35 * ahead.pv_dc_kwh,
                    empirical if verified else 0.0,
                ),
            )
            demand_dc = ahead.home_ac_kwh / plant.eta_pv_to_ac
            extra = max(0.0, ahead.pv_dc_kwh + forecast_upside - demand_dc) - max(
                0.0, ahead.pv_dc_kwh - demand_dc
            )
            expected_extra += extra * plant.eta_pv_to_battery

        target = min(capacity * 0.30, max(0.0, expected_extra))
        if target <= 1e-8:
            periods.append(Headroom())
            continue
        # Future avoided purchase or unpriced demand is the economic upside.
        # The time window extends to evening (up to 12 hours), without
        # inventing next-day spot prices.
        future_buy = max(later.buy_dkk_per_kwh for later in quarters[i : i + 48])
        marginal_value = max(
            0.0,
            future_buy * plant.eta_battery_to_ac - DEGRADATION_DKK_PER_KWH_DC,
        )
        # Unverified upside has lower weight; measured p75 must remain a
        # bounded heuristic because inverter PV may have been curtailed.
        uncertainty_weight = 0.55 if verified else 0.45
        price = marginal_value * uncertainty_weight / 8.0
        periods.append(Headroom(target, price, expected_extra))
    return tuple(periods)
