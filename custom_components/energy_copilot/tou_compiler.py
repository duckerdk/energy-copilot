"""Conservative Deye six-window TOU compiler.

A 15-minute economic trajectory is not automatically executable with Deye's
repeating daily schedule. This compiler supports only uniform whole-hour
24-hour plans with <=6 runs. It refuses incomplete days rather than inventing
a safe-looking six-window schedule.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite


class TOUCompilationError(ValueError):
    """The economic plan cannot be represented as a Deye daily program."""


@dataclass(frozen=True)
class TOUWindow:
    start_minute: int
    power_w: int
    minimum_soc_pct: int
    grid_charge: bool


@dataclass(frozen=True)
class TOUProgram:
    windows: tuple[TOUWindow, ...]
    represented_hours: int = 24


def compile_tou(
    quarter_plan: tuple[dict, ...],
    *,
    charge_limit_a: int = 50,
    discharge_limit_a: int = 100,
    voltage_v: float = 51.2,
) -> TOUProgram:
    """Compile a full Copenhagen-local day or block as not representable.

    Input keys: start (offset-aware ISO), soc_end_pct, grid_charge_kwh,
    battery_discharge_dc_kwh. The converter only accepts whole-hour uniform
    decisions. A valid output is a set of six distinct daily start points.
    No device writes are performed.
    """
    if len(quarter_plan) != 96:
        raise TOUCompilationError("tou:requires_complete_24h")
    if (
        not isfinite(voltage_v)
        or voltage_v <= 0
        or type(charge_limit_a) is not int
        or type(discharge_limit_a) is not int
        or not 0 <= charge_limit_a <= 50
        or not 0 <= discharge_limit_a <= 100
    ):
        raise TOUCompilationError("tou:invalid_limits")
    from zoneinfo import ZoneInfo

    local = ZoneInfo("Europe/Copenhagen")
    parsed = []
    for entry in quarter_plan:
        try:
            at = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
            if at.tzinfo is None:
                raise ValueError("naive")
            at = at.astimezone(local)
            soc = float(entry["soc_end_pct"])
            charge = float(entry["grid_charge_kwh"])
            discharge = float(entry["battery_discharge_dc_kwh"])
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise TOUCompilationError("tou:invalid_quarter") from exc
        if not all(map(isfinite, (soc, charge, discharge))):
            raise TOUCompilationError("tou:nonfinite")
        if not 20 <= soc <= 100 or charge < 0 or discharge < 0:
            raise TOUCompilationError("tou:outside_policy")
        if charge > 1e-8 and discharge > 1e-8:
            raise TOUCompilationError("tou:simultaneous_charge_discharge")
        parsed.append((at, soc, charge, discharge))
    if parsed[0][0].hour != 0 or parsed[0][0].minute != 0:
        raise TOUCompilationError("tou:must_start_midnight")
    for i, (at, _, _, _) in enumerate(parsed):
        if at.date() != parsed[0][0].date():
            raise TOUCompilationError("tou:not_single_local_day")
        if i and at.astimezone(ZoneInfo("UTC")) - parsed[i - 1][0].astimezone(
            ZoneInfo("UTC")
        ) != timedelta(minutes=15):
            raise TOUCompilationError("tou:noncontiguous")
        if at.hour != i // 4 or at.minute != (i % 4) * 15:
            raise TOUCompilationError("tou:dst_or_misaligned")
    hourly = []
    for hour in range(24):
        block = parsed[4 * hour : 4 * hour + 4]
        # Deye can hold a single SOC target per period. Do not round a
        # changing 15-minute SOC trajectory into an unverified TOU behavior.
        socs = [round(b[1]) for b in block]
        if any(abs(b[1] - socs[0]) > 0.5 for b in block):
            raise TOUCompilationError("tou:intra_hour_soc_trajectory")
        charge = sum(b[2] for b in block)
        discharge = sum(b[3] for b in block)
        if charge > 1e-8 and discharge > 1e-8:
            raise TOUCompilationError("tou:mixed_hour")
        # A zero target cannot be assumed to disable Deye TOU power limits;
        # encode only configured safe upper limit (not a forced charge).
        power = round(
            voltage_v * (charge_limit_a if charge > 1e-8 else discharge_limit_a)
        )
        hourly.append((power, socs[0], charge > 1e-8))
    runs = []
    for hour, (power, soc, grid_charge) in enumerate(hourly):
        if hour == 0 or hourly[hour] != hourly[hour - 1]:
            runs.append(TOUWindow(hour * 60, power, soc, grid_charge))
    if len(runs) != 6:
        raise TOUCompilationError("tou:requires_exactly_six_distinct_windows")
    return TOUProgram(tuple(runs))
