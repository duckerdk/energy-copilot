"""Pure scenario adapter shared by local and GitHub Pages Planner Lab.

Uses original production optimizer modules and the same validated input schema.
No Home Assistant, sockets or external Python packages required.
"""

import importlib
import math
import sys
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path

CORE_PATH = Path(__file__).resolve().parent / "core"
if not CORE_PATH.is_dir():
    CORE_PATH = (
        Path(__file__).resolve().parents[2]
        / "custom_components"
        / "energy_copilot"
    )

PACKAGE = "_energy_copilot_planner_lab_core"
MAX_HOURS = 72

# N1, October 2026 — actual Home Assistant source export 2026-10-20:
# sensor.energi_data_service - sensor.energi_data_spotpris.
# Additional tariffs: Energinet transmission 0.054, system 0.090,
# elafgift 0.010; N1 hour rates 0.110 / 0.329 / 0.988 DKK/kWh.
# All figures come from already-priced HA sensors. Do NOT add VAT twice.
FIXED_SURCHARGE_DKK_KWH = 0.054 + 0.090 + 0.010
N1_NIGHT = 0.110
N1_DAY = 0.329
N1_PEAK = 0.988


def _last_sunday(year: int, month: int) -> int:
    if month == 12:
        first_next = datetime(year + 1, 1, 1, tzinfo=UTC)
    else:
        first_next = datetime(year, month + 1, 1, tzinfo=UTC)
    last = first_next - timedelta(days=1)
    return last.day - (last.weekday() + 1) % 7


def _local_hour_copenhagen(when: datetime) -> int:
    """Copenhagen local hour using current EU DST (March/October last Sunday).

    Works in browsers with Python WASM, even when zoneinfo databases are absent.
    """
    value = when.astimezone(UTC)
    year = value.year
    dst_start = datetime(year, 3, _last_sunday(year, 3), 1, tzinfo=UTC)
    dst_end = datetime(year, 10, _last_sunday(year, 10), 1, tzinfo=UTC)
    return (value + timedelta(hours=2 if dst_start <= value < dst_end else 1)).hour


def _prices_from_spot(spot: float, at: datetime) -> tuple[float, float]:
    """Return buy/sell DKK/kWh from a raw spot value and N1 snapshot tariffs."""
    hour = _local_hour_copenhagen(at)
    network = N1_NIGHT if hour < 6 else N1_PEAK if 17 <= hour < 21 else N1_DAY
    return spot + FIXED_SURCHARGE_DKK_KWH + network, spot



def _core_modules():
    """Load original production modules without running HA integration setup."""
    if not CORE_PATH.is_dir():
        raise RuntimeError("Brak katalogu custom_components/energy_copilot.")
    if PACKAGE not in sys.modules:
        module = types.ModuleType(PACKAGE)
        module.__package__ = PACKAGE
        module.__path__ = [str(CORE_PATH)]
        sys.modules[PACKAGE] = module
    planner = importlib.import_module(f"{PACKAGE}.planner")
    horizon = importlib.import_module(f"{PACKAGE}.horizon_optimizer")
    return planner, horizon


def _number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}: wymagana liczba")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{label}: liczba musi być skończona")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label}: wartość mniejsza niż {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label}: wartość większa niż {maximum}")
    return value


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("start_utc: podaj godzinę w formacie ISO 8601 z UTC")
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("start_utc: błędna data lub godzina") from exc
    if date.tzinfo is None or date.utcoffset() != timedelta(0):
        raise ValueError("start_utc: wymagany czas UTC z +00:00 lub Z")
    if date.minute or date.second or date.microsecond:
        raise ValueError("start_utc: wymagany początek pełnej godziny")
    return date.astimezone(UTC)


def _round(value):
    return round(value, 5)


def simulate_scenario(payload):
    """Validate hand-entered hourly values; return real planner dispatch."""
    if not isinstance(payload, dict):
        raise ValueError("Przekaż obiekt JSON")
    planner, horizon = _core_modules()
    start = _timestamp(payload.get("start_utc"))
    hours = payload.get("hours")
    if not isinstance(hours, list) or not (1 <= len(hours) <= MAX_HOURS):
        raise ValueError(f"hours: wymagane od 1 do {MAX_HOURS} kolejnych godzin")
    soc = _number(payload.get("initial_soc_pct"), "SOC początkowy", 20, 100)
    capacity = _number(payload.get("battery_capacity_kwh", 10.24), "Pojemność", 0.1, 250)
    voltage = _number(payload.get("battery_voltage_v", 51.2), "Napięcie", 1, 1500)
    max_charge = _number(payload.get("charge_limit_a", 50), "Limit ładowania", 0, 50)
    max_discharge = _number(
        payload.get("discharge_limit_a", 100), "Limit rozładowania", 0, 100
    )
    max_grid = _number(
        payload.get("grid_charge_limit_a", 50), "Limit ładowania sieciowego", 0, 50
    )
    if max_grid > max_charge:
        raise ValueError("Limit ładowania z sieci nie może przekraczać ogólnego limitu")
    efficiency = _number(payload.get("efficiency", 0.95), "Sprawność", 0.01, 1)
    export = payload.get("pv_export_enabled", False)
    if not isinstance(export, bool):
        raise ValueError("pv_export_enabled: wymagana wartość true lub false")

    plant = planner.Plant(
        battery_capacity_dc_kwh=capacity,
        initial_soc_pct=soc,
        battery_voltage_v=voltage,
        charge_limit_a=max_charge,
        discharge_limit_a=max_discharge,
        grid_charge_limit_a=max_grid,
        eta_pv_to_ac=efficiency,
        eta_pv_to_battery=efficiency,
        eta_grid_to_battery=efficiency,
        eta_battery_to_ac=efficiency,
        terminal_value_dkk_per_kwh_dc=0.0,
    )
    quarters = []
    for i, hour in enumerate(hours):
        if not isinstance(hour, dict):
            raise ValueError(f"Godzina {i + 1}: wymagany obiekt")
        spot = _number(hour.get("spot"), f"Godzina {i + 1} / spot", -20, 100)
        pv_kw = _number(hour.get("pv_kw"), f"Godzina {i + 1} / PV", 0, 100)
        home_kw = _number(hour.get("home_kw"), f"Godzina {i + 1} / dom", 0, 100)
        for part in range(4):
            at = start + timedelta(hours=i, minutes=15 * part)
            buy, sell = _prices_from_spot(spot, at)
            quarters.append(
                planner.Quarter(
                    start=at,
                    end=at + planner.QUARTER,
                    buy_dkk_per_kwh=buy,
                    sell_dkk_per_kwh=sell,
                    pv_dc_kwh=pv_kw / 4,
                    home_ac_kwh=home_kw / 4,
                    pv_export_enabled=export,
                )
            )

    try:
        result = horizon.optimize_horizon(plant, tuple(quarters))
    except planner.InfeasibleCandidate as exc:
        raise ValueError(f"Planer: {exc}") from exc

    detailed = []
    for i, (q, d, observation) in enumerate(
        zip(quarters, result.dispatches, result.candidate.quarters, strict=True)
    ):
        if d.grid_to_battery_ac_kwh > 1e-7:
            mode = "charge_grid"
        elif d.pv_to_battery_dc_kwh > 1e-7:
            mode = "charge_pv"
        elif d.battery_to_home_dc_kwh > 1e-7:
            mode = "discharge"
        else:
            mode = "hold"
        detailed.append(
            {
                "start_utc": q.start.isoformat(),
                "hour": i // 4,
                "mode": mode,
                "soc_start_pct": _round(observation.soc_start_pct),
                "soc_end_pct": _round(observation.soc_end_pct),
                "grid_charge_ac_kwh": _round(d.grid_to_battery_ac_kwh),
                "pv_charge_dc_kwh": _round(d.pv_to_battery_dc_kwh),
                "discharge_dc_kwh": _round(d.battery_to_home_dc_kwh),
                "grid_import_ac_kwh": _round(observation.grid_import_kwh),
                "grid_export_ac_kwh": _round(observation.grid_export_kwh),
                "pv_curtailed_dc_kwh": _round(d.pv_curtailed_dc_kwh),
                "purchase_dkk": _round(observation.purchase_dkk),
                "sales_dkk": _round(observation.sales_dkk),
                "degradation_dkk": _round(observation.degradation_dkk),
            }
        )

    per_hour = []
    sum_keys = (
        "grid_charge_ac_kwh", "pv_charge_dc_kwh", "discharge_dc_kwh",
        "grid_import_ac_kwh", "grid_export_ac_kwh", "pv_curtailed_dc_kwh",
        "purchase_dkk", "sales_dkk", "degradation_dkk",
    )
    for i, values in enumerate(hours):
        parts = detailed[i * 4 : i * 4 + 4]
        grid = sum(d["grid_charge_ac_kwh"] for d in parts)
        pv_charge = sum(d["pv_charge_dc_kwh"] for d in parts)
        discharge = sum(d["discharge_dc_kwh"] for d in parts)
        mode = (
            "charge_grid" if grid > 1e-6 else
            "charge_pv" if pv_charge > 1e-6 else
            "discharge" if discharge > 1e-6 else "hold"
        )
        per_hour.append(
            {
                "start_utc": (start + timedelta(hours=i)).isoformat(),
                "spot": values["spot"],
                "buy": quarters[i * 4].buy_dkk_per_kwh,
                "sell": quarters[i * 4].sell_dkk_per_kwh,
                "pv_kw": values["pv_kw"],
                "home_kw": values["home_kw"],
                "mode": mode,
                "soc_end_pct": parts[-1]["soc_end_pct"],
                **{key: _round(sum(d[key] for d in parts)) for key in sum_keys},
            }
        )

    reference = result.reference
    candidate = result.candidate
    return {
        "summary": {
            "start_utc": start.isoformat(),
            "hours": len(hours),
            "initial_soc_pct": soc,
            "final_soc_pct": _round(candidate.final_soc_pct),
            "reference_objective_dkk": _round(reference.objective_dkk),
            "plan_objective_dkk": _round(candidate.objective_dkk),
            "modeled_saving_dkk": _round(reference.objective_dkk - candidate.objective_dkk),
            "energy_cost_dkk": _round(candidate.energy_cost_dkk),
            "degradation_cost_dkk": _round(candidate.degradation_cost_dkk),
            "terminal_value_dkk": _round(candidate.terminal_battery_value_dkk),
            "terminal_value_dkk_per_kwh_dc": _round(result.terminal_value_dkk_per_kwh_dc),
            "grid_charge_ac_kwh": _round(sum(d.grid_to_battery_ac_kwh for d in result.dispatches)),
            "pv_charge_dc_kwh": _round(sum(d.pv_to_battery_dc_kwh for d in result.dispatches)),
            "battery_discharge_dc_kwh": _round(sum(d.battery_to_home_dc_kwh for d in result.dispatches)),
            "grid_import_ac_kwh": _round(sum(q.grid_import_kwh for q in candidate.quarters)),
            "grid_export_ac_kwh": _round(sum(q.grid_export_kwh for q in candidate.quarters)),
            "pv_curtailed_dc_kwh": _round(sum(d.pv_curtailed_dc_kwh for d in result.dispatches)),
            "evaluated_transitions": result.evaluated_transitions,
            "soc_step_dc_kwh": result.soc_resolution_dc_kwh,
            "solver": result.method,
            "tariff_source": "N1_2026-10-20_HA_export_snapshot",
            "physical_dispatch_verified": True,
            "deye_tou_verified": False,
            "device_commands_executed": False,
        },
        "hourly": per_hour,
        "quarters": detailed,
    }


