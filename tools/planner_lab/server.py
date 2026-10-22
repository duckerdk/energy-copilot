"""Offline Energy Co-Pilot Planner Lab.

Runs the exact production planner and independent dispatch validator, without
importing Home Assistant or talking to HA / an inverter. 127.0.0.1 only.
"""

import argparse
import importlib
import json
import math
import sys
import types
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_PATH = ROOT / "custom_components" / "energy_copilot"
PACKAGE = "_energy_copilot_planner_lab_core"
MAX_BODY_BYTES = 160_000
MAX_HOURS = 72


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
        buy = _number(hour.get("buy"), f"Godzina {i + 1} / zakup", -20, 100)
        sell = _number(hour.get("sell"), f"Godzina {i + 1} / sprzedaż", -20, 100)
        pv_kw = _number(hour.get("pv_kw"), f"Godzina {i + 1} / PV", 0, 100)
        home_kw = _number(hour.get("home_kw"), f"Godzina {i + 1} / dom", 0, 100)
        for part in range(4):
            at = start + timedelta(hours=i, minutes=15 * part)
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
                "purchase_dkk": _round(observation.purchase_dkk),
                "sales_dkk": _round(observation.sales_dkk),
                "degradation_dkk": _round(observation.degradation_dkk),
            }
        )

    per_hour = []
    sum_keys = (
        "grid_charge_ac_kwh", "pv_charge_dc_kwh", "discharge_dc_kwh",
        "grid_import_ac_kwh", "grid_export_ac_kwh",
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
                "buy": values["buy"],
                "sell": values["sell"],
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
            "evaluated_transitions": result.evaluated_transitions,
            "soc_step_dc_kwh": result.soc_resolution_dc_kwh,
            "solver": result.method,
            "physical_dispatch_verified": True,
            "deye_tou_verified": False,
            "device_commands_executed": False,
        },
        "hourly": per_hour,
        "quarters": detailed,
    }


class Handler(BaseHTTPRequestHandler):
    def _reply(self, code, content, media_type):
        self.send_response(code)
        self.send_header("Content-Type", media_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            return self._reply(404, b"Not found", "text/plain; charset=utf-8")
        page = (Path(__file__).parent / "index.html").read_bytes()
        return self._reply(200, page, "text/html; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/simulate":
            return self._reply(404, b"Not found", "text/plain; charset=utf-8")
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY_BYTES:
                raise ValueError("Wielkość danych przekracza limit")
            request = json.loads(self.rfile.read(length))
            response = simulate_scenario(request)
            status = 200
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            response, status = {"error": str(exc)}, 400
        except Exception:
            # Do not expose server tracebacks to the browser.
            self.log_error("Unexpected simulation exception: %r", sys.exc_info()[1])
            response, status = {"error": "Wewnętrzny błąd symulacji. Sprawdź konsolę."}, 500
        data = json.dumps(response, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._reply(status, data, "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


def main():
    parser = argparse.ArgumentParser(description="Offline Planner Lab - bez HA i falownika")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    _core_modules()
    address = f"http://127.0.0.1:{args.port}"
    with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
        print(f"Planner Lab: {address}\nZamknięcie: Ctrl+C", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
