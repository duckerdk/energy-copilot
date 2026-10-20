"""Bounded negative-home evidence, never a causal or physical load model."""

from bisect import bisect_right
from collections import Counter

from .const import HISTORY_ROLES
from .recorder_reconstruction import recorded_power
from .validation import number, utc

MAX_NEGATIVE_EVENTS = 16


def negative_home_audit(rows, entities, start, end, runs=(), excluded_roles=()):
    """Compare actual as-of Recorder rows, without confusing changes with reports.

    Unequal last_updated timestamps are evidence of unequal state-change times,
    not proof of asynchronous device sampling. Algebraic agreement is not proof
    of correct AC/DC semantics, losses, or an independent household measurement.
    """
    series = {
        role: sorted(rows.get(entities[role], ()), key=lambda s: s.last_updated)
        for role in HISTORY_ROLES
    }
    times = {
        role: [utc(s.last_updated) for s in states] for role, states in series.items()
    }
    events, counts = [], Counter()
    total = 0
    for state in series["home"]:
        at = utc(state.last_updated)
        if not start <= at < end or state.attributes.get("unit_of_measurement") != "W":
            continue
        try:
            home = number(state.state)
        except TypeError, ValueError, OverflowError:
            continue
        if home >= 0:
            continue
        total += 1
        run = next(
            (r for r in reversed(runs) if r.start <= at < r.end and r.reliable), None
        )
        values, changed, invalid = {}, {}, {}
        for role in ("pv", "grid", "battery"):
            index = bisect_right(times[role], at) - 1
            if role in excluded_roles:
                invalid[role] = "recorder_entity_excluded"
            elif index < 0 or run is None or times[role][index] < run.start:
                invalid[role] = "recording_context_unknown"
            else:
                changed[role] = times[role][index].isoformat()
                try:
                    values[role] = recorded_power(role, series[role][index])
                except ValueError as err:
                    invalid[role] = str(err)
        component_sum = sum(values.values()) if len(values) == 3 else None
        residual = home - component_sum if component_sum is not None else None
        matches = abs(residual) <= 1 if residual is not None else None
        counts[
            "incomplete_source_context" if invalid else "complete_recorded_sources"
        ] += 1
        if matches is not None:
            counts["template_sum_matches" if matches else "template_sum_differs"] += 1
        distinct = len(set(changed.values())) > 1 if len(changed) == 3 else None
        if distinct:
            counts["different_source_change_times"] += 1
        if len(events) < MAX_NEGATIVE_EVENTS:
            events.append(
                {
                    "at_utc": at.isoformat(),
                    "home_w": home,
                    "source_w": values,
                    "source_changed_at_utc": changed,
                    "invalid_sources": invalid,
                    "template_residual_w": residual,
                    "template_sum_matches_within_1w": matches,
                    "different_source_change_times": distinct,
                    "recording_context_known": run is not None,
                }
            )
    return {
        "records": total,
        "events": events,
        "events_truncated": total > len(events),
        "context_counts": dict(sorted(counts.items())),
        "timestamp_basis": "recorder_state_change_not_device_report",
        "causal_conclusion": "not_identifiable_from_state_changes_alone",
        "physical_consumption_verified": False,
        "template_residual_tolerance_w": 1,
    }
