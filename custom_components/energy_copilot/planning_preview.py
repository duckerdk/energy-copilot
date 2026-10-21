"""Read-only M3 HA preview: bounded, auditable arbitrage scenarios.

The forecast conversion and physical efficiency factors are TEST assumptions.
Output is never a Deye TOU plan, a confirmed saving or an actuator command.
"""

from dataclasses import dataclass, replace
from datetime import datetime

from .models import InputSnapshot
from .planner import (
    Dispatch,
    InfeasibleCandidate,
    Plant,
    lowest_cost_candidate,
    spread_grid_charge_evenly,
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
MAX_PRICE_CANDIDATES = 10


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


def _reference_dispatch(plant: Plant, q) -> Dispatch:
    pv_home = min(q.pv_dc_kwh, q.home_ac_kwh / plant.eta_pv_to_ac)
    remainder = max(0.0, q.pv_dc_kwh - pv_home)
    pv_export = remainder if q.pv_export_enabled and q.sell_dkk_per_kwh >= 0.40 else 0.0
    return Dispatch(pv_home, 0.0, pv_export, remainder - pv_export, 0.0, 0.0)


def evaluate_preview(
    snapshot: InputSnapshot,
    *,
    mode: str,
    pv_export_enabled: bool = False,
) -> Preview:
    """Model only counterfactual charge/discharge cycles with unchanged ending SOC.

    Candidate search deliberately explores a restricted set of ONE-cycle schedules
    and reports this, not a global optimum, six-TOU schedule or a live decision.
    """
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
        inputs = build_planning_input(
            snapshot,
            pv_forecast_to_dc_multiplier=PV_FORECAST_TO_DC_MULTIPLIER,
            pv_export_enabled=pv_export_enabled,
            allow_prefix=True,
            pv_temporal_model="uniform_power_unverified",
            load_projection=project_previous_utc_day_load(
                snapshot, short_gap_model="linear_bracketed_unverified"
            ),
        )
        quarters = inputs.quarters
        base = tuple(_reference_dispatch(plant, q) for q in quarters)
        # The preview searches a bounded sample of economically promising pairs,
        # without promoting this candidate set to "optimal Deye planning".
        headroom = plant.battery_capacity_dc_kwh * (100 - soc) / 100
        grid_current_limit = min(plant.charge_limit_a, plant.grid_charge_limit_a)
        candidates = [base]
        schedules = [(None, None)]
        if headroom > 1e-7 and len(quarters) >= 2:
            order = sorted(
                range(len(quarters)),
                key=lambda i: (quarters[i].buy_dkk_per_kwh, i),
            )[:MAX_PRICE_CANDIDATES]
            for charge_at in order:
                # Single-slot and two-slot charging with unchanged final SOC.
                for count in (1, 2):
                    end_charge = charge_at + count
                    if end_charge >= len(quarters):
                        continue
                    charge_energy_limit = (
                        battery_voltage * grid_current_limit * count / 4000
                    )
                    discharge_order = sorted(
                        range(end_charge, len(quarters)),
                        key=lambda i: (-quarters[i].buy_dkk_per_kwh, i),
                    )[:MAX_PRICE_CANDIDATES]
                    for discharge_at in discharge_order:
                        q = quarters[discharge_at]
                        base_load_ac = (
                            q.home_ac_kwh
                            - base[discharge_at].pv_to_home_dc_kwh * plant.eta_pv_to_ac
                        )
                        energy = min(
                            headroom,
                            charge_energy_limit,
                            battery_voltage * plant.discharge_limit_a / 4000,
                            max(0.0, base_load_ac) / plant.eta_battery_to_ac,
                        )
                        if energy <= 1e-7:
                            continue
                        flags = tuple(
                            charge_at <= i < end_charge for i in range(len(quarters))
                        )
                        try:
                            dispatch = list(
                                spread_grid_charge_evenly(
                                    plant, quarters, energy, flags
                                )
                            )
                            dispatch[discharge_at] = replace(
                                dispatch[discharge_at],
                                battery_to_home_dc_kwh=energy,
                            )
                            candidates.append(tuple(dispatch))
                            schedules.append((charge_at, discharge_at))
                        except InfeasibleCandidate:
                            continue
        selected, result = lowest_cost_candidate(plant, quarters, tuple(candidates))
        _, reference = lowest_cost_candidate(plant, quarters, (base,))
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
    charge_idx, discharge_idx = schedules[selected]
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
        scenario_cost_dkk=result.objective_dkk,
        modeled_saving_dkk=max(0.0, reference.objective_dkk - result.objective_dkk),
        max_charge_current_a=max(q.charge_current_a for q in result.quarters),
        charge_start=quarters[charge_idx].start if charge_idx is not None else None,
        discharge_start=(
            quarters[discharge_idx].start if discharge_idx is not None else None
        ),
        evaluated_scenarios=len(candidates),
        voltage_source=voltage_source,
    )
