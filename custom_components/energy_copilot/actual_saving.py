"""Estimated yesterday battery savings from recorded signed grid and battery power.

Counterfactual removes battery flows while keeping observed PV and household load.
This is an estimate with assumed conversion efficiency, not billed savings.
"""

from bisect import bisect_right
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo


EFFICIENCY = 0.95
LOCAL = ZoneInfo("Europe/Copenhagen")
ROLES = ("grid", "battery", "buy", "sell")


@dataclass(frozen=True)
class YesterdaySaving:
    date: str
    value: float | None
    actual_cost: float | None
    baseline_cost: float | None
    coverage: float
    reason: str | None


def yesterday_bounds(now):
    local_end = now.astimezone(LOCAL).date()
    end = datetime(local_end.year, local_end.month, local_end.day, tzinfo=LOCAL)
    start = end - timedelta(days=1)
    return start.astimezone(UTC), end.astimezone(UTC), start.date().isoformat()


def _states_at(rows, entity_id, start, end):
    series = sorted(rows.get(entity_id, ()), key=lambda r: r.last_updated)
    return [r for r in series if r.last_updated <= end]


def compute_yesterday(rows, entities, start, end, date):
    """Integrate known recorded state spans; reject incomplete historical evidence."""
    streams = [_states_at(rows, entities[role], start, end) for role in ROLES]
    if any(not stream for stream in streams):
        return YesterdaySaving(date, None, None, None, 0.0, "history:missing_source")
    timestamps = [[s.last_updated for s in stream] for stream in streams]
    if any(t[0] > start for t in timestamps):
        return YesterdaySaving(date, None, None, None, 0.0, "history:missing_start")
    cuts = sorted(
        {start, end}
        | {t for times in timestamps for t in times if start < t < end}
    )
    actual, baseline = 0.0, 0.0
    duration = 0.0
    for left, right in zip(cuts, cuts[1:]):
        values = []
        for stream, times, role in zip(streams, timestamps, ROLES, strict=True):
            index = bisect_right(times, left) - 1
            if index < 0:
                return YesterdaySaving(date, None, None, None, 0.0, "history:missing_interval")
            state = stream[index]
            try:
                value = float(state.state)
                if not isfinite(value):
                    raise ValueError("nonfinite")
                if role in {"grid", "battery"}:
                    if state.attributes.get("unit_of_measurement") != "W":
                        raise ValueError("power_unit")
                elif state.attributes.get("unit_of_measurement") not in {
                    "DKK/kWh", "DKK/kwh"
                }:
                    raise ValueError("price_unit")
            except (ValueError, TypeError, AttributeError):
                return YesterdaySaving(
                    date, None, None, None, duration / (end - start).total_seconds(),
                    f"history:invalid_{role}",
                )
            values.append(value)
        grid_w, battery_w, buy, sell = values
        # Positive grid = import; positive battery = discharging to the home.
        # Remove battery from the measured grid balance at modeled AC efficiency.
        battery_ac_w = battery_w * EFFICIENCY if battery_w >= 0 else battery_w / EFFICIENCY
        baseline_grid_w = grid_w + battery_ac_w
        hours = (right - left).total_seconds() / 3600
        actual += (max(grid_w, 0) * buy - max(-grid_w, 0) * sell) / 1000 * hours
        baseline += (
            max(baseline_grid_w, 0) * buy - max(-baseline_grid_w, 0) * sell
        ) / 1000 * hours
        duration += (right - left).total_seconds()
    coverage = duration / (end - start).total_seconds()
    if coverage < 1 - 1e-8:
        return YesterdaySaving(date, None, None, None, coverage, "history:incomplete")
    return YesterdaySaving(date, round(baseline - actual, 3), round(actual, 3),
                           round(baseline, 3), coverage, None)


def read_yesterday(hass, entities, now):
    """One bounded synchronous Recorder query, called via executor once per local day."""
    start, end, date = yesterday_bounds(now)
    keys = {role: entities[role] for role in ROLES}
    from homeassistant.components.recorder.history import get_significant_states

    rows = get_significant_states(
        hass, start, end, entity_ids=list(keys.values()),
        include_start_time_state=True,
        significant_changes_only=False, minimal_response=False, no_attributes=False,
    )
    return compute_yesterday(rows, keys, start, end, date)
