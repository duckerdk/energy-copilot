"""Risk-aware value of battery headroom for PV forecast upside (dry-run).

This is an explicit bounded scenario, not a fixed SOC ceiling or a measured
probability distribution. It values possible extra PV against the economic alternative of exporting it.
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
    """Price a rolling 4-hour buffer from PV upside and export opportunity.

    Only expected PV inside the NEXT sixteen quarters activates the buffer.
    This also prices headroom before sunrise, influencing night charging. If 16 real observed quarters are available,
    their underprediction p75 supplements a forecast-relative 35% uncertainty
    band, rather than asserting that curtailed PV was physically observed.
    Opportunity costs are spread across sixteen 15-minute quarters so storing
    one DC kWh for an entire sunny window is priced only once per window.
    """
    capacity = plant.battery_capacity_dc_kwh
    verified = observed_pv_upside_kwh is not None
    empirical = max(0.0, float(observed_pv_upside_kwh)) if verified else 0.0
    periods = []
    for i, q in enumerate(quarters):
        expected_extra = 0.0
        opportunity_total = 0.0
        for ahead in quarters[i : i + 16]:
            if ahead.pv_dc_kwh <= 0.01:
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
            extra_dc = extra * plant.eta_pv_to_battery
            expected_extra += extra_dc
            future_buy = max(
                later.buy_dkk_per_kwh for later in quarters[i : i + 48]
            )
            export_value = (
                ahead.sell_dkk_per_kwh
                * plant.eta_pv_to_ac
                / plant.eta_pv_to_battery
                if ahead.pv_export_enabled
                and ahead.sell_dkk_per_kwh >= PV_EXPORT_MIN_DKK_PER_KWH
                else 0.0
            )
            # Credit only the net benefit after cycling and foregone export.
            opportunity_total += extra_dc * max(
                0.0,
                future_buy * plant.eta_battery_to_ac
                - DEGRADATION_DKK_PER_KWH_DC
                - export_value,
            )

        target = min(capacity * 0.30, max(0.0, expected_extra))
        if target <= 1e-8:
            periods.append(Headroom())
            continue
        # A zero premium allows selling instead of reserving capacity.
        uncertainty_weight = 0.55 if verified else 0.45
        price = (
            opportunity_total / expected_extra * uncertainty_weight / 16.0
            if expected_extra > 1e-8
            else 0.0
        )
        periods.append(Headroom(target, price, expected_extra))
    return tuple(periods)
