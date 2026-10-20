"""Conservative source validation shared by live and historical observations."""

import hashlib
import json
import math
from bisect import bisect_left, bisect_right
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .const import HISTORY_ROLES, MAX_AGE, MAX_SKEW, POWER_ROLES
from .models import (
    ForecastPeriod,
    ForecastSnapshot,
    HistorySlot,
    Issue,
    PriceSlot,
    Sample,
)

COPENHAGEN = ZoneInfo("Europe/Copenhagen")


def number(value):
    """Reject booleans, NaN and infinity rather than inventing zero."""
    if isinstance(value, bool):
        raise ValueError("boolean")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("nonfinite")
    return result


def utc(value):
    """Require an offset: ambiguous/imaginary local wall times are not guessed."""
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timezone_required")
    return result.astimezone(UTC)


def measurement(role, state, now, *, historical=False):
    if state is None or state.state in ("unknown", "unavailable"):
        raise ValueError("invalid_input")
    try:
        value = number(state.state)
        at = utc(state.last_updated if historical else state.last_reported)
    except ValueError, TypeError, OverflowError:
        raise ValueError("invalid_input") from None
    if at > now + MAX_SKEW or now - at > MAX_AGE:
        raise ValueError("stale_input")
    unit = state.attributes.get("unit_of_measurement")
    expected = (
        "W"
        if role in POWER_ROLES
        else {
            "voltage": "V",
            "current": "A",
            "soc": "%",
            "daily_pv": "kWh",
            "daily_charge": "kWh",
            "daily_discharge": "kWh",
        }[role]
    )
    if unit != expected:
        raise ValueError("invalid_unit")
    if role == "soc" and not 0 <= value <= 100:
        raise ValueError("invalid_input")
    if (
        role
        in {
            "pv",
            "pv1",
            "pv2",
            "voltage",
            "daily_pv",
            "daily_charge",
            "daily_discharge",
            "home",
        }
        and value < 0
    ):
        raise ValueError("invalid_input")
    return Sample(value, at)


def measurements(states, now, *, historical=False):
    values, issues = {}, []
    for role, state in states.items():
        if role in {"buy", "sell"}:
            continue
        try:
            values[role] = measurement(role, state, now, historical=historical)
        except ValueError as err:
            issues.append(Issue(str(err), role))
    sources = [values[r] for r in HISTORY_ROLES if r in values]
    if len(sources) != len(HISTORY_ROLES):
        values.pop("home", None)
        issues.append(Issue("invalid_input", "home"))
    elif max(s.at for s in sources) - min(s.at for s in sources) > MAX_SKEW:
        values.pop("home", None)
        issues.append(Issue("snapshot_not_synchronous", "home"))
    flows = {}
    for role, positive, negative in (
        ("grid", "grid_import", "grid_export"),
        ("battery", "battery_discharge", "battery_charge"),
    ):
        if role in values:
            power = values[role].value / 1000
            flows.update({positive: max(0, power), negative: max(0, -power)})
    if "pv" in values:
        flows["pv_dc"] = values["pv"].value / 1000
    if all(r in values for r in ("voltage", "current", "battery")):
        expected = values["voltage"].value * values["current"].value
        if abs(expected - values["battery"].value) > max(100, abs(expected) * 0.1):
            issues.append(Issue("battery_power_inconsistent", "battery"))
    if all(r in values for r in ("pv", "pv1", "pv2")):
        if abs(values["pv"].value - values["pv1"].value - values["pv2"].value) > 100:
            issues.append(Issue("pv_sum_inconsistent", "pv"))
    if "soc" in values and values["soc"].value < 20:
        issues.append(Issue("below_policy_minimum", "soc"))
    # No physical efficiency is inferred from the template's algebraic residual.
    return values, flows, issues


def _prices(state, now, source):
    issues, result = [], {}
    if state is None or state.state in ("unknown", "unavailable"):
        return result, [Issue("invalid_input", source)]
    attrs = state.attributes
    if attrs.get("unit_of_measurement") != "DKK/kWh":
        return result, [Issue("invalid_unit", source)]
    today = now.astimezone(COPENHAGEN).date()
    poisoned = set()
    for name, day in (
        ("raw_today", today),
        ("raw_tomorrow", today + timedelta(days=1)),
    ):
        if name == "raw_tomorrow" and attrs.get("tomorrow_valid") is not True:
            continue
        records = attrs.get(name)
        if not isinstance(records, (list, tuple)) or not records:
            issues.append(Issue("empty_prices", source))
            continue
        for record in records:
            try:
                start = utc(record["hour"])
                price = number(record["price"])
                if start.astimezone(COPENHAGEN).date() != day:
                    raise ValueError("stale_prices")
                if start.minute or start.second or start.microsecond:
                    raise ValueError("invalid_price_interval")
                if start in result or start in poisoned:
                    result.pop(start, None)
                    poisoned.add(start)
                    issues.append(Issue("duplicate_price", source))
                    continue
                if start + timedelta(hours=1) <= now:
                    continue
                result[start] = price
            except KeyError, ValueError, TypeError, OverflowError:
                issues.append(Issue("invalid_price_slot", source))
    return result, issues


def prices(buy_state, sell_state, now):
    buy, issues = _prices(buy_state, now, "buy")
    sell, errors = _prices(sell_state, now, "sell")
    issues.extend(errors)
    if buy.keys() != sell.keys():
        issues.append(Issue("price_horizon_mismatch", "prices"))
    common = sorted(buy.keys() & sell.keys())
    if not common:
        issues.append(Issue("empty_prices", "prices"))
    if any(b - a != timedelta(hours=1) for a, b in zip(common, common[1:])):
        issues.append(Issue("price_gap", "prices"))
    slots = tuple(PriceSlot(t, t + timedelta(hours=1), buy[t], sell[t]) for t in common)
    current = next((s for s in slots if s.start <= now < s.end), None)
    if slots and current is None:
        issues.append(Issue("missing_current_price_slot", "prices"))
    if current:
        try:
            precise = number(sell_state.attributes["current_price"])
            if (precise >= 0.4) != (current.sell >= 0.4):
                issues.append(Issue("PRICE_THRESHOLD_AMBIGUOUS", "sell"))
        except KeyError, TypeError, ValueError, OverflowError:
            issues.append(Issue("missing_current_price", "sell"))
    return slots, issues


def forecast(response, captured_at):
    """Parse HA 2026.10 raw response: Wh for the interval starting at timestamp."""
    if not isinstance(response, Mapping):
        raise ValueError("invalid_forecast_response")
    periods = response.get("wh_period")
    if not isinstance(periods, Mapping) or not periods:
        raise ValueError("invalid_forecast_response")
    # wh_period alone cannot establish the final interval's end.
    # Require the corresponding watts timeline to prove interval boundaries.
    watts = response.get("watts")
    if not isinstance(watts, Mapping):
        raise ValueError("forecast_boundaries_unverifiable")
    boundaries = sorted({utc(t) for t in watts})
    if len(boundaries) != len(watts) or any(number(v) < 0 for v in watts.values()):
        raise ValueError("invalid_forecast_response")
    values = {utc(t): number(v) for t, v in periods.items()}
    if (
        len(values) != len(periods)
        or any(v < 0 for v in values.values())
        or not values.keys() <= set(boundaries)
    ):
        raise ValueError("invalid_forecast_response")
    result = []
    for start, end in zip(boundaries, boundaries[1:]):
        if start in values and start >= captured_at:
            result.append(ForecastPeriod(start, end, values[start] / 1000))
    if not result:
        raise ValueError("empty_forecast")
    serial = [(p.start.isoformat(), p.end.isoformat(), p.kwh) for p in result]
    version = hashlib.sha256(
        json.dumps([captured_at.isoformat(), serial]).encode()
    ).hexdigest()[:16]
    return ForecastSnapshot(captured_at, version, tuple(result))


def history_slots(history, entities, start, end):
    """Integrate 15 minute slots only when every source has corroborating history.

    State-change Recorder rows cannot prove unchanged sensors kept reporting.
    Carry-forwards exceeding MAX_AGE are explicitly unverifiable, never zeros.
    """
    series = {}
    times = {}
    for role in HISTORY_ROLES:
        rows = history.get(entities[role], [])
        series[role] = sorted(rows, key=lambda s: s.last_updated)
        times[role] = [utc(s.last_updated) for s in series[role]]
    timeline = sorted({t for ts in times.values() for t in ts})
    result = []
    cursor = start
    while cursor + timedelta(minutes=15) <= end:
        stop = cursor + timedelta(minutes=15)
        cuts = [
            cursor,
            *timeline[bisect_right(timeline, cursor) : bisect_left(timeline, stop)],
            stop,
        ]
        energy, issues = 0.0, []
        for left, right in zip(cuts, cuts[1:]):
            selected = {}
            for role, rows in series.items():
                index = bisect_right(times[role], left) - 1
                state = rows[index] if index >= 0 else None
                if state is None:
                    issues.append(Issue("historical_quality_unverifiable", role))
                    continue
                try:
                    # Recorder last_reported is not persisted: use last_updated.
                    at = utc(state.last_updated)
                    if right - at > MAX_AGE:
                        issues.append(Issue("historical_quality_unverifiable", role))
                    selected[role] = state
                except ValueError, TypeError:
                    issues.append(Issue("historical_quality_unverifiable", role))
            values, _, errors = measurements(selected, left, historical=True)
            issues.extend(errors)
            if "home" in values:
                energy += (
                    values["home"].value / 1000 * (right - left).total_seconds() / 3600
                )
        result.append(
            HistorySlot(cursor, stop, None if issues else energy, tuple(set(issues)))
        )
        cursor = stop
    return tuple(result)
