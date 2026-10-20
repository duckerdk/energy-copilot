"""Conservative source validation shared by live and historical observations."""

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from .const import HISTORY_ROLES, MAX_FUTURE_OFFSET, POWER_ROLES
from .models import (
    ForecastPeriod,
    ForecastSnapshot,
    Issue,
    PriceSlot,
    Sample,
)

COPENHAGEN = ZoneInfo("Europe/Copenhagen")
DERIVED_SOURCES = {"home": ("pv", "grid", "battery")}
DERIVED_SUM_TOLERANCE_W = 1


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
    """Validate the HA state without confusing an unchanged value with failure."""
    if state is None or state.state in ("unknown", "unavailable"):
        raise ValueError("invalid_input")
    try:
        value = number(state.state)
        at = utc(state.last_updated if historical else state.last_reported)
    except AttributeError, ValueError, TypeError, OverflowError:
        raise ValueError("invalid_input") from None
    if at > now + MAX_FUTURE_OFFSET:
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
        }
        and value < 0
    ):
        raise ValueError("invalid_input")
    return Sample(value, at)


def live_timing(states, samples=None):
    """Compare reports separately from changes in the derived home's inputs.

    A fresh unchanged report is not a new value requiring template evaluation.
    These are HA timestamps, not proof of an atomic Modbus device frame.
    """
    reported, changed = {}, {}
    for role in HISTORY_ROLES:
        state = states.get(role)
        try:
            reported[role] = utc(state.last_reported)
            changed[role] = utc(state.last_updated)
        except AttributeError, TypeError, ValueError, OverflowError:
            continue
    sources = ("pv", "grid", "battery")

    def skew(roles, timestamps):
        times = [timestamps[r] for r in roles if r in timestamps]
        return (
            (max(times) - min(times)).total_seconds()
            if len(times) == len(roles)
            else None
        )

    return {
        "source_report_skew_seconds": skew(sources, reported),
        "source_context_skew_seconds": skew(
            sources,
            {r: s.context_at or s.at for r, s in samples.items()}
            if samples is not None
            else reported,
        ),
        "all_report_skew_seconds": skew(HISTORY_ROLES, reported),
        "home_context_lag_seconds": max(
            0, (max(changed[r] for r in sources) - reported["home"]).total_seconds()
        )
        if "home" in reported and all(r in changed for r in sources)
        else None,
    }


def _derived_measurements(values, issues, templates, recovery):
    """Check derived HA values against available sources and observed recoveries."""
    if (
        "pv" in values
        and "pv" in recovery
        and (recovery["pv"] is None or values["pv"].at < recovery["pv"])
    ):
        values.pop("pv")
        issues.append(Issue("derived_predates_source_recovery", "pv"))
    for role, required in DERIVED_SOURCES.items():
        if role not in templates:
            continue
        configured = templates[role]
        if any(source not in values for source in configured):
            values.pop(role, None)
            issues.append(Issue("derived_source_invalid", role))
            continue
        if role not in values:
            continue
        original = values[role]
        if any(
            source in recovery
            and (recovery[source] is None or original.at < recovery[source])
            for source in configured
        ):
            values.pop(role, None)
            issues.append(Issue("derived_predates_source_recovery", role))
            continue
        if not all(source in configured and source in values for source in required):
            issues.append(Issue("derived_source_confirmation_unavailable", role))
        elif (
            abs(original.value - sum(values[source].value for source in required))
            > DERIVED_SUM_TOLERANCE_W
        ):
            issues.append(Issue("derived_sum_time_uncertain", role))
        else:
            values[role] = Sample(
                original.value,
                original.at,
                context_at=min(
                    values[source].context_at or values[source].at
                    for source in required
                ),
            )

def measurements(
    states, now, *, historical=False, source_recovery_at=None, derived_templates=None
):
    values, issues = {}, []
    for role, state in states.items():
        if role in {"buy", "sell"}:
            continue
        try:
            values[role] = measurement(role, state, now, historical=historical)
        except ValueError as err:
            issues.append(Issue(str(err), role))
    if not historical:
        _derived_measurements(
            values,
            issues,
            derived_templates or {},
            source_recovery_at or {},
        )
    sources = [values[r] for r in HISTORY_ROLES if r in values]
    if len(sources) != len(HISTORY_ROLES):
        values.pop("home", None)
        issues.append(Issue("invalid_input", "home"))
    elif any(
        recovered is None or values["home"].at < recovered
        for recovered in (source_recovery_at or {}).values()
    ):
        values.pop("home", None)
        issues.append(Issue("home_predates_source_recovery", "home"))
    else:
        if (home := values["home"]).value < 0:
            # User policy applies after availability, units, freshness and recovery.
            # As-of timing uncertainty remains visible alongside normalization.
            values["home"] = Sample(
                0, home.at, raw_value=home.value, context_at=home.context_at
            )
            issues.append(Issue("negative_home_normalized", "home"))
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
    """Parse observed HA raw Wh for the interval ENDING at each timestamp.

    The native service's start-index docstring contradicts the exported data.
    The contract in HA_CONTRACT is backed by adjacent watts/time integrals.
    """
    if not isinstance(response, Mapping):
        raise ValueError("invalid_forecast_response")
    periods = response.get("wh_period")
    if not isinstance(periods, Mapping) or not periods:
        raise ValueError("invalid_forecast_response")
    # The first energy value has no known preceding boundary. Every later
    # value belongs to the interval bounded by the preceding/current watts keys.
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
        if end in values and end > captured_at:
            result.append(ForecastPeriod(start, end, values[end] / 1000))
    if not result:
        raise ValueError("empty_forecast")
    serial = [(p.start.isoformat(), p.end.isoformat(), p.kwh) for p in result]
    version = hashlib.sha256(
        json.dumps([captured_at.isoformat(), serial]).encode()
    ).hexdigest()[:16]
    # Keep an already-started interval intact: its original Wh cannot be prorated
    # without a finer energy forecast. captured_at still records when it became known.
    return ForecastSnapshot(
        captured_at,
        version,
        tuple(result),
        source_start=boundaries[0],
        source_end=boundaries[-1],
        # A nonzero final value is bounded by the previous timestamp. Only
        # initial energy lacks its PRECEDING boundary; never invent that period.
        unbounded_prior_energy_at=tuple(
            t for t, value in values.items() if t == boundaries[0] and value != 0
        ),
        missing_energy_at=tuple(t for t in boundaries[1:] if t not in values),
    )


def history_slots(history, entities, start, end, recording_runs=(), excluded_roles=()):
    """Reconstruct recorded states only with supplied Recorder process/run evidence."""
    from .recorder_reconstruction import reconstruct_history

    return reconstruct_history(
        history, entities, start, end, recording_runs, excluded_roles
    )
