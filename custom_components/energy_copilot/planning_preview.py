"""Read-only M3 HA preview: bounded, auditable arbitrage scenarios.

The forecast conversion and physical efficiency factors are TEST assumptions.
Output is never a Deye TOU plan, a confirmed saving or an actuator command.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from .horizon_optimizer import optimize_horizon
from .models import InputSnapshot
from .planner import (
    DEGRADATION_DKK_PER_KWH_DC,
    PV_EXPORT_MIN_DKK_PER_KWH,
    InfeasibleCandidate,
    Plant,
)
from .planning_inputs import (
    PlanningInputError,
    build_planning_input,
    project_previous_utc_day_load,
)

NOMINAL_BATTERY_CAPACITY_KWH = 10.24
NOMINAL_BATTERY_VOLTAGE_V = 51.2
MODEL_EFFICIENCY = 0.95
PV_FORECAST_TO_DC_MULTIPLIER = 1.0
# Each scenario returns to initial SOC, so terminal valuation cancels out.
TERMINAL_VALUE_DKK_PER_KWH = 0.0


@dataclass(frozen=True)
class Preview:
    status: str
    reason: str | None = None
    first_uncovered_at: datetime | None = None
    start: datetime | None = None
    end: datetime | None = None
    published_price_horizon_end: datetime | None = None
    coverage: str = "unknown"
    quarters: int = 0
    pv_version: str | None = None
    source_load_method: str | None = None
    load_modeled_quarters: int = 0
    pv_temporal_model: str | None = None
    pv_temporal_modeled_quarters: int = 0
    reference_cost_dkk: float | None = None
    scenario_cost_dkk: float | None = None
    modeled_saving_dkk: float | None = None
    max_charge_current_a: float | None = None
    charge_start: datetime | None = None
    discharge_start: datetime | None = None
    evaluated_scenarios: int = 0
    voltage_source: str = "not_evaluated"
    executable: bool = False
    final_soc_pct: float | None = None
    terminal_value_dkk_per_kwh_dc: float | None = None
    grid_charge_kwh: float | None = None
    pv_charge_dc_kwh: float | None = None
    discharge_dc_kwh: float | None = None
    purchase_cost_dkk: float | None = None
    sales_revenue_dkk: float | None = None
    terminal_value_basis: str | None = None
    post_horizon_load_kwh: float | None = None
    evaluated_transitions: int = 0
    soc_resolution_dc_kwh: float | None = None
    hourly_plan: tuple[dict, ...] = ()


def _hourly_plan(quarters, dispatches, results) -> tuple[dict, ...]:
    """Expose a bounded display series; no private household history exported."""
    from datetime import UTC

    hours = {}
    for q, d, outcome in zip(quarters, dispatches, results, strict=True):
        at = q.start.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        row = hours.setdefault(
            at,
            {
                "start": at.isoformat(),
                "price_dkk_kwh": q.buy_dkk_per_kwh,
                "buy_price_dkk_kwh": q.buy_dkk_per_kwh,
                "sell_price_dkk_kwh": q.sell_dkk_per_kwh,
                "solar_sell_planned_on": (
                    q.pv_export_enabled
                    and q.sell_dkk_per_kwh >= PV_EXPORT_MIN_DKK_PER_KWH
                ),
                "home_kwh": 0.0,
                "pv_dc_kwh": 0.0,
                "grid_charge_kwh": 0.0,
                "pv_charge_dc_kwh": 0.0,
                "battery_discharge_dc_kwh": 0.0,
                "grid_import_kwh": 0.0,
                "grid_export_kwh": 0.0,
                "purchase_cost_dkk": 0.0,
                "sales_revenue_dkk": 0.0,
                "pv_curtailed_dc_kwh": 0.0,
                "charge_current_setpoint_a": 0.0,
                "soc_end_pct": 0.0,
            },
        )
        row["home_kwh"] += q.home_ac_kwh
        row["pv_dc_kwh"] += q.pv_dc_kwh
        row["grid_charge_kwh"] += d.grid_to_battery_ac_kwh
        row["pv_charge_dc_kwh"] += d.pv_to_battery_dc_kwh
        row["battery_discharge_dc_kwh"] += d.battery_to_home_dc_kwh
        row["grid_import_kwh"] += outcome.grid_import_kwh
        row["grid_export_kwh"] += outcome.grid_export_kwh
        row["purchase_cost_dkk"] += outcome.purchase_dkk
        row["sales_revenue_dkk"] += outcome.sales_dkk
        row["pv_curtailed_dc_kwh"] += d.pv_curtailed_dc_kwh
        row["charge_current_setpoint_a"] = max(
            row["charge_current_setpoint_a"], outcome.charge_current_a
        )
        row["soc_end_pct"] = outcome.soc_end_pct
    return tuple(
        {
            key: round(value, 4) if isinstance(value, float) else value
            for key, value in row.items()
        }
        for row in hours.values()
    )


def _terminal_proxy(plant, quarters, projection, pv_periods):
    """Value unpriced post-horizon household demand without inventing tariffs.

    No hypothetical next-day spot is appended to the optimization. If actual
    future household demand is forecast before the next predicted PV arrival,
    use a clearly labeled recent PUBLISHED purchase-price proxy for the energy
    that would otherwise need to be bought. The old minimum-price replacement
    value is the conservative floor; there is no fixed terminal SOC target.
    """
    end = quarters[-1].end
    first_future_pv = min(
        (
            period.start
            for period in pv_periods
            if period.start >= end and period.kwh > 1e-8
        ),
        default=end + timedelta(hours=8),
    )
    until = min(first_future_pv, end + timedelta(hours=12))
    demand = sum(
        period.kwh
        for period in projection.periods
        if end <= period.start and period.end <= until
    )
    published = [q.buy_dkk_per_kwh for q in quarters]
    base = max(0.0, min(published) / plant.eta_grid_to_battery)
    if demand <= 1e-6:
        return base, "min_published_buy_price_no_confirmed_future_load", demand
    recent = published[-min(32, len(published)) :]
    conservative_proxy = max(
        0.0,
        median(recent) * plant.eta_battery_to_ac - DEGRADATION_DKK_PER_KWH_DC,
    )
    return (
        max(base, conservative_proxy),
        "unpriced_overnight_demand_recent_published_price_proxy_unverified",
        demand,
    )


def evaluate_preview(
    snapshot: InputSnapshot,
    *,
    mode: str,
    pv_export_enabled: bool = False,
    load_projection=None,
) -> Preview:
    """Optimize the complete published input horizon, but never actuate Deye."""
    if mode != "dry_run":
        return Preview("monitor", "dry_run_not_enabled")
    if "soc" not in snapshot.measurements:
        return Preview("blocked", "soc:invalid_or_missing")
    soc = snapshot.measurements["soc"].value
    if soc < 20 or soc > 100:
        return Preview("blocked", "soc:outside_policy")
    voltage = snapshot.measurements.get("voltage")
    voltage_source = "measured" if voltage else "nominal_unverified"
    battery_voltage = voltage.value if voltage else NOMINAL_BATTERY_VOLTAGE_V
    if battery_voltage <= 0:
        return Preview("blocked", "battery:invalid_voltage")

    plant = Plant(
        battery_capacity_dc_kwh=NOMINAL_BATTERY_CAPACITY_KWH,
        initial_soc_pct=soc,
        battery_voltage_v=battery_voltage,
        charge_limit_a=50,
        discharge_limit_a=100,
        grid_charge_limit_a=50,
        eta_pv_to_ac=MODEL_EFFICIENCY,
        eta_pv_to_battery=MODEL_EFFICIENCY,
        eta_grid_to_battery=MODEL_EFFICIENCY,
        eta_battery_to_ac=MODEL_EFFICIENCY,
        terminal_value_dkk_per_kwh_dc=TERMINAL_VALUE_DKK_PER_KWH,
    )
    try:
        projection = load_projection or project_previous_utc_day_load(
            snapshot, short_gap_model="linear_bracketed_unverified"
        )
        inputs = build_planning_input(
            snapshot,
            pv_forecast_to_dc_multiplier=PV_FORECAST_TO_DC_MULTIPLIER,
            pv_export_enabled=pv_export_enabled,
            allow_prefix=True,
            pv_temporal_model="uniform_power_unverified",
            load_projection=projection,
        )
        quarters = inputs.quarters
        terminal_value, terminal_basis, unpriced_load = _terminal_proxy(
            plant, quarters, projection, snapshot.forecast.periods
        )
        result = optimize_horizon(
            plant, quarters, terminal_value_override=terminal_value
        )
        candidate = result.candidate
        reference = result.reference
        dispatches = result.dispatches
    except (PlanningInputError, InfeasibleCandidate) as error:
        code = getattr(error, "code", str(error))
        return Preview(
            "blocked",
            str(code),
            first_uncovered_at=getattr(error, "at", None),
            voltage_source=voltage_source,
        )

    first = quarters[0].start
    last = quarters[-1].end
    charge_idx = next(
        (
            i
            for i, d in enumerate(dispatches)
            if d.grid_to_battery_ac_kwh > 1e-7 or d.pv_to_battery_dc_kwh > 1e-7
        ),
        None,
    )
    discharge_idx = next(
        (i for i, d in enumerate(dispatches) if d.battery_to_home_dc_kwh > 1e-7),
        None,
    )
    return Preview(
        "preview",
        start=first,
        end=last,
        published_price_horizon_end=inputs.price_horizon_end,
        coverage=inputs.coverage_status,
        reason=inputs.first_missing_code,
        first_uncovered_at=inputs.first_missing_at,
        quarters=len(quarters),
        pv_version=inputs.pv_forecast_version,
        source_load_method=inputs.load_method,
        load_modeled_quarters=inputs.load_modeled_quarters,
        pv_temporal_model=inputs.pv_temporal_model,
        pv_temporal_modeled_quarters=inputs.pv_temporal_modeled_quarters,
        reference_cost_dkk=reference.objective_dkk,
        scenario_cost_dkk=candidate.objective_dkk,
        modeled_saving_dkk=max(0.0, reference.objective_dkk - candidate.objective_dkk),
        max_charge_current_a=max(q.charge_current_a for q in candidate.quarters),
        charge_start=quarters[charge_idx].start if charge_idx is not None else None,
        discharge_start=quarters[discharge_idx].start
        if discharge_idx is not None
        else None,
        evaluated_scenarios=0,
        evaluated_transitions=result.evaluated_transitions,
        voltage_source=voltage_source,
        final_soc_pct=candidate.final_soc_pct,
        terminal_value_dkk_per_kwh_dc=result.terminal_value_dkk_per_kwh_dc,
        grid_charge_kwh=sum(d.grid_to_battery_ac_kwh for d in dispatches),
        pv_charge_dc_kwh=sum(d.pv_to_battery_dc_kwh for d in dispatches),
        discharge_dc_kwh=sum(d.battery_to_home_dc_kwh for d in dispatches),
        purchase_cost_dkk=sum(q.purchase_dkk for q in candidate.quarters),
        sales_revenue_dkk=sum(q.sales_dkk for q in candidate.quarters),
        terminal_value_basis=terminal_basis,
        post_horizon_load_kwh=unpriced_load,
        soc_resolution_dc_kwh=result.soc_resolution_dc_kwh,
        hourly_plan=_hourly_plan(quarters, dispatches, candidate.quarters),
    )
