"""M3 deterministic candidate evaluator. Calculations only; no HA service calls.

A candidate is an explicit 15-minute DC/AC dispatch. This module verifies its
physical and policy constraints, then costs it; it does not claim Deye TOU
executability or select an optimal candidate. Uncalibrated inputs must be passed
explicitly rather than concealed as defaults.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isclose, isfinite

QUARTER = timedelta(minutes=15)
EPS = 1e-7
DEGRADATION_DKK_PER_KWH_DC = 0.40
MIN_SOC = 20.0
PV_EXPORT_MIN_DKK_PER_KWH = 0.40
COST_TIE_ABS_TOL_DKK = 1e-7  # Floating-point equality only; no economic sacrifice.


class InfeasibleCandidate(ValueError):
    """Candidate violates input, energy conservation, equipment or policy."""


@dataclass(frozen=True)
class Plant:
    battery_capacity_dc_kwh: float
    initial_soc_pct: float
    battery_voltage_v: float
    charge_limit_a: float
    grid_charge_limit_a: float
    eta_pv_to_ac: float
    eta_pv_to_battery: float
    eta_grid_to_battery: float
    eta_battery_to_ac: float
    terminal_value_dkk_per_kwh_dc: float


@dataclass(frozen=True)
class Quarter:
    start: datetime
    end: datetime
    buy_dkk_per_kwh: float
    sell_dkk_per_kwh: float
    pv_dc_kwh: float
    home_ac_kwh: float
    pv_export_enabled: bool


@dataclass(frozen=True)
class Dispatch:
    pv_to_home_dc_kwh: float
    pv_to_battery_dc_kwh: float
    pv_to_export_dc_kwh: float
    pv_curtailed_dc_kwh: float
    grid_to_battery_ac_kwh: float
    battery_to_home_dc_kwh: float


@dataclass(frozen=True)
class QuarterResult:
    start: datetime
    end: datetime
    soc_start_pct: float
    soc_end_pct: float
    grid_import_kwh: float
    grid_export_kwh: float
    battery_discharge_dc_kwh: float
    purchase_dkk: float
    sales_dkk: float
    degradation_dkk: float
    charge_current_a: float
    grid_charge_current_a: float


@dataclass(frozen=True)
class CandidateResult:
    quarters: tuple[QuarterResult, ...]
    energy_cost_dkk: float
    degradation_cost_dkk: float
    terminal_battery_value_dkk: float
    objective_dkk: float
    final_soc_pct: float
    # Dispatch on 15-min intervals is not proof of 6-window Deye TOU feasibility.
    status: str = "physical_candidate_only_tou_unverified"


def _finite(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InfeasibleCandidate(f"{label}:not_numeric")
    value = float(value)
    if not isfinite(value):
        raise InfeasibleCandidate(f"{label}:nonfinite")
    return value


def _nonnegative(value: float, label: str) -> float:
    value = _finite(value, label)
    if value < 0:
        raise InfeasibleCandidate(f"{label}:negative")
    return value


def _plant(plant: Plant) -> None:
    if _nonnegative(plant.battery_capacity_dc_kwh, "capacity") <= 0:
        raise InfeasibleCandidate("capacity:zero")
    if _nonnegative(plant.battery_voltage_v, "voltage") <= 0:
        raise InfeasibleCandidate("voltage:zero")
    if not MIN_SOC <= _finite(plant.initial_soc_pct, "initial_soc") <= 100:
        raise InfeasibleCandidate("initial_soc:policy_limit")
    for field, maximum in (
        ("charge_limit_a", 50),
        ("grid_charge_limit_a", 50),
    ):
        if _nonnegative(getattr(plant, field), field) > maximum:
            raise InfeasibleCandidate(f"{field}:policy_limit")
    if plant.grid_charge_limit_a > plant.charge_limit_a:
        raise InfeasibleCandidate("grid_charge_limit_a:exceeds_charge_limit")
    for field in (
        "eta_pv_to_ac",
        "eta_pv_to_battery",
        "eta_grid_to_battery",
        "eta_battery_to_ac",
    ):
        if not 0 < _finite(getattr(plant, field), field) <= 1:
            raise InfeasibleCandidate(f"{field}:outside_0_to_1")
    _nonnegative(plant.terminal_value_dkk_per_kwh_dc, "terminal_value")


def simulate_candidate(
    plant: Plant, quarters: tuple[Quarter, ...], dispatches: tuple[Dispatch, ...]
) -> CandidateResult:
    """Verify and value explicit dispatch, without executing any inverter action.

    Battery charging DC energy includes conversion efficiencies exactly once;
    discharging degradation is charged once on DC energy. PV/battery export is
    not enabled by this API. All quarters are consecutive and UTC-aligned.
    """
    _plant(plant)
    if not quarters or len(quarters) != len(dispatches):
        raise InfeasibleCandidate("quarters:missing_or_mismatched")
    capacity = plant.battery_capacity_dc_kwh
    energy = capacity * plant.initial_soc_pct / 100
    minimum = capacity * MIN_SOC / 100
    outcomes = []
    for index, (q, d) in enumerate(zip(quarters, dispatches, strict=True)):
        if q.start.tzinfo is None or q.end.tzinfo is None:
            raise InfeasibleCandidate("time:timezone_required")
        if q.start.utcoffset() != timedelta(0) or q.end.utcoffset() != timedelta(0):
            raise InfeasibleCandidate("time:utc_required")
        duration = q.end - q.start
        # Only the FIRST interval may be a remaining fraction of the active
        # quarter. A live replan starts at the latest observation, not the
        # next 15-minute boundary, but future intervals remain complete.
        if (
            duration <= timedelta(0)
            or duration > QUARTER
            or (index and duration != QUARTER)
            or (index and (q.start.second or q.start.microsecond or q.start.minute % 15))
            or q.end.second
            or q.end.microsecond
            or q.end.minute % 15
        ):
            raise InfeasibleCandidate("time:quarter_alignment")
        if index and q.start != quarters[index - 1].end:
            raise InfeasibleCandidate("time:nonconsecutive")
        if not isinstance(q.pv_export_enabled, bool):
            raise InfeasibleCandidate("pv_export_enabled:not_boolean")
        buy = _finite(q.buy_dkk_per_kwh, "buy_price")
        sell = _finite(q.sell_dkk_per_kwh, "sell_price")
        pv = _nonnegative(q.pv_dc_kwh, "pv")
        home = _nonnegative(q.home_ac_kwh, "home")
        for field in (
            "pv_to_home_dc_kwh",
            "pv_to_battery_dc_kwh",
            "pv_to_export_dc_kwh",
            "pv_curtailed_dc_kwh",
            "grid_to_battery_ac_kwh",
            "battery_to_home_dc_kwh",
        ):
            _nonnegative(getattr(d, field), field)
        if (
            abs(
                d.pv_to_home_dc_kwh
                + d.pv_to_battery_dc_kwh
                + d.pv_to_export_dc_kwh
                + d.pv_curtailed_dc_kwh
                - pv
            )
            > EPS
        ):
            raise InfeasibleCandidate("pv:balance")
        if d.pv_to_export_dc_kwh > EPS and (
            not q.pv_export_enabled or sell < PV_EXPORT_MIN_DKK_PER_KWH
        ):
            raise InfeasibleCandidate("pv_export:policy")
        pv_home = d.pv_to_home_dc_kwh * plant.eta_pv_to_ac
        battery_home = d.battery_to_home_dc_kwh * plant.eta_battery_to_ac
        if pv_home + battery_home > home + EPS:
            raise InfeasibleCandidate("home:oversupply")
        grid_home = max(0.0, home - pv_home - battery_home)
        grid_import = grid_home + d.grid_to_battery_ac_kwh
        grid_export = d.pv_to_export_dc_kwh * plant.eta_pv_to_ac
        if grid_import > EPS and grid_export > EPS:
            raise InfeasibleCandidate("grid:simultaneous_import_export")
        charge_dc = (
            d.pv_to_battery_dc_kwh * plant.eta_pv_to_battery
            + d.grid_to_battery_ac_kwh * plant.eta_grid_to_battery
        )
        discharge_dc = d.battery_to_home_dc_kwh
        if charge_dc > EPS and discharge_dc > EPS:
            raise InfeasibleCandidate("battery:simultaneous_charge_discharge")
        quarter_hours = duration.total_seconds() / 3600
        max_charge = (
            plant.battery_voltage_v * plant.charge_limit_a / 1000 * quarter_hours
        )
        max_grid_charge = (
            plant.battery_voltage_v * plant.grid_charge_limit_a / 1000 * quarter_hours
        )
        if charge_dc > max_charge + EPS:
            raise InfeasibleCandidate("battery:charge_current_limit")
        if d.grid_to_battery_ac_kwh * plant.eta_grid_to_battery > max_grid_charge + EPS:
            raise InfeasibleCandidate("battery:grid_charge_current_limit")
        soc_start = energy / capacity * 100
        energy += charge_dc - discharge_dc
        if not minimum - EPS <= energy <= capacity + EPS:
            raise InfeasibleCandidate("battery:soc_policy_limit")
        purchase = grid_import * buy
        sales = grid_export * sell
        degradation = discharge_dc * DEGRADATION_DKK_PER_KWH_DC
        charge_current = charge_dc * 1000 / (plant.battery_voltage_v * quarter_hours)
        grid_current = (
            d.grid_to_battery_ac_kwh
            * plant.eta_grid_to_battery
            * 1000
            / (plant.battery_voltage_v * quarter_hours)
        )
        outcomes.append(
            QuarterResult(
                q.start,
                q.end,
                soc_start,
                energy / capacity * 100,
                grid_import,
                grid_export,
                discharge_dc,
                purchase,
                sales,
                degradation,
                charge_current,
                grid_current,
            )
        )
    energy_cost = sum(r.purchase_dkk - r.sales_dkk for r in outcomes)
    degradation_cost = sum(r.degradation_dkk for r in outcomes)
    terminal_value = energy * plant.terminal_value_dkk_per_kwh_dc
    return CandidateResult(
        tuple(outcomes),
        energy_cost,
        degradation_cost,
        terminal_value,
        energy_cost + degradation_cost - terminal_value,
        energy / capacity * 100,
    )


def reference_no_battery(
    plant: Plant, quarters: tuple[Quarter, ...]
) -> CandidateResult:
    """Zero battery cycling benchmark, NOT the existing Deye TOU baseline."""
    _plant(plant)
    dispatches = []
    for q in quarters:
        pv = _nonnegative(q.pv_dc_kwh, "pv")
        home = _nonnegative(q.home_ac_kwh, "home")
        sell = _finite(q.sell_dkk_per_kwh, "sell_price")
        pv_to_home = min(pv, home / plant.eta_pv_to_ac)
        excess = max(0.0, pv - pv_to_home)
        can_export = q.pv_export_enabled and sell >= PV_EXPORT_MIN_DKK_PER_KWH
        pv_to_export = excess if can_export else 0.0
        dispatches.append(
            Dispatch(
                pv_to_home,
                0.0,
                pv_to_export,
                excess - pv_to_export,
                0.0,
                0.0,
            )
        )
    return simulate_candidate(plant, quarters, tuple(dispatches))


def lowest_cost_candidate(
    plant: Plant,
    quarters: tuple[Quarter, ...],
    candidate_dispatches: tuple[tuple[Dispatch, ...], ...],
) -> tuple[int, CandidateResult]:
    """Rank validated candidates by full-horizon cost, including terminal SOC.

    This selects only among supplied dispatches. It does NOT claim global
    optimality, existing Deye policy emulation, or six-TOU executability.
    """
    if not candidate_dispatches:
        raise InfeasibleCandidate("candidates:missing")
    scored = tuple(
        (index, simulate_candidate(plant, quarters, candidate))
        for index, candidate in enumerate(candidate_dispatches)
    )
    minimum_cost = min(result.objective_dkk for _, result in scored)
    equally_cheap = (
        (index, result)
        for index, result in scored
        if isclose(
            result.objective_dkk, minimum_cost, rel_tol=0, abs_tol=COST_TIE_ABS_TOL_DKK
        )
    )
    return min(
        equally_cheap,
        key=lambda item: (
            sum(q.charge_current_a**2 for q in item[1].quarters),
            max(q.charge_current_a for q in item[1].quarters),
            item[0],
        ),
    )


def spread_grid_charge_evenly(
    plant: Plant,
    quarters: tuple[Quarter, ...],
    target_battery_dc_kwh: float,
    eligible_quarters: tuple[bool, ...],
) -> tuple[Dispatch, ...]:
    """Build a lower-current candidate for a chosen charging window.

    Evenly distribute a required DC energy amount across explicitly eligible
    15-minute slots. The calling optimizer must choose slots based on published
    prices and a real deadline; this helper does not determine that window.
    Never infer a target SOC or pretend a dispatch is a Deye TOU command.
    """
    _plant(plant)
    target = _nonnegative(target_battery_dc_kwh, "target_battery_charge")
    if not quarters or len(eligible_quarters) != len(quarters):
        raise InfeasibleCandidate("charge_window:missing_or_mismatched")
    if any(not isinstance(flag, bool) for flag in eligible_quarters):
        raise InfeasibleCandidate("charge_window:invalid_flag")
    count = sum(eligible_quarters)
    if target > EPS and not count:
        raise InfeasibleCandidate("charge_window:no_eligible_quarters")
    dc_per_slot = target / count if count else 0.0
    max_dc_per_slot = (
        plant.battery_voltage_v
        * min(plant.charge_limit_a, plant.grid_charge_limit_a)
        / 1000
        * (QUARTER.total_seconds() / 3600)
    )
    if dc_per_slot > max_dc_per_slot + EPS:
        raise InfeasibleCandidate("charge_window:insufficient_time")
    dispatches = []
    for q, eligible in zip(quarters, eligible_quarters, strict=True):
        pv = _nonnegative(q.pv_dc_kwh, "pv")
        home = _nonnegative(q.home_ac_kwh, "home")
        sell = _finite(q.sell_dkk_per_kwh, "sell_price")
        pv_to_home = min(pv, home / plant.eta_pv_to_ac)
        excess = max(0.0, pv - pv_to_home)
        export = (
            excess if q.pv_export_enabled and sell >= PV_EXPORT_MIN_DKK_PER_KWH else 0.0
        )
        dispatches.append(
            Dispatch(
                pv_to_home_dc_kwh=pv_to_home,
                pv_to_battery_dc_kwh=0.0,
                pv_to_export_dc_kwh=export,
                pv_curtailed_dc_kwh=excess - export,
                grid_to_battery_ac_kwh=(
                    dc_per_slot / plant.eta_grid_to_battery if eligible else 0.0
                ),
                battery_to_home_dc_kwh=0.0,
            )
        )
    result = tuple(dispatches)
    simulate_candidate(plant, quarters, result)
    return result
