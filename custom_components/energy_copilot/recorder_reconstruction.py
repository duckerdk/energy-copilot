"""Reconstruct Recorder state intervals without treating changes as heartbeats."""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta

from .const import HISTORY_ROLES
from .models import HistorySlot, Issue
from .validation import number, utc


@dataclass(frozen=True)
class RecordingRun:
    """A recorded process lifetime; clean termination does not prove no pauses."""

    start: datetime
    end: datetime
    reliable: bool = True


def _value(role, state):
    if state is None or state.state in {"unknown", "unavailable"}:
        raise ValueError("invalid_input")
    try:
        value = number(state.state)
    except ValueError, TypeError, OverflowError:
        raise ValueError("invalid_input") from None
    if state.attributes.get("unit_of_measurement") != "W":
        raise ValueError("invalid_unit")
    if role in {"pv", "home"} and value < 0:
        raise ValueError("invalid_input")
    return value


def reconstruct_history(
    rows, entities, start, end, recording_runs=(), excluded_roles=()
):
    """Integrate recorded state changes within known Recorder process runs.

    Recorder's last_updated identifies a state change, not a reporting heartbeat.
    Therefore neither live freshness nor live timestamp-skew tests apply here.
    A process run bounds reconstruction; it does not prove that recording was
    never paused or that filters stayed unchanged. A held zero is a reconstructed
    recorded state, never proof that the physical device kept reporting.
    """
    series = {
        role: sorted(rows.get(entities[role], ()), key=lambda row: row.last_updated)
        for role in HISTORY_ROLES
    }
    times = {
        role: [utc(row.last_updated) for row in records]
        for role, records in series.items()
    }
    runs = sorted(recording_runs, key=lambda run: run.start)
    boundaries = sorted(
        {t for ts in times.values() for t in ts}
        | {t for run in runs for t in (run.start, run.end)}
    )
    excluded = set(excluded_roles)
    result = []
    cursor = start
    while cursor + timedelta(minutes=15) <= end:
        stop = cursor + timedelta(minutes=15)
        cuts = [
            cursor,
            *boundaries[
                bisect_right(boundaries, cursor) : bisect_left(boundaries, stop)
            ],
            stop,
        ]
        energy, issues = 0.0, set()
        for left, right in zip(cuts, cuts[1:]):
            run = next(
                (
                    candidate
                    for candidate in reversed(runs)
                    if candidate.start <= left and candidate.end >= right
                ),
                None,
            )
            if run is None:
                issues.add(Issue("recorder_recording_gap", "recorder"))
                issues.add(Issue("historical_quality_unverifiable", "recorder"))
                continue
            if not run.reliable:
                issues.add(Issue("recorder_run_uncertain", "recorder"))
                issues.add(Issue("historical_quality_unverifiable", "recorder"))
                continue
            values = {}
            for role in HISTORY_ROLES:
                if role in excluded:
                    issues.add(Issue("recorder_entity_excluded", role))
                    continue
                index = bisect_right(times[role], left) - 1
                if index < 0 or times[role][index] < run.start:
                    issues.add(Issue("historical_quality_unverifiable", role))
                    continue
                try:
                    values[role] = _value(role, series[role][index])
                except ValueError as err:
                    issues.add(Issue(str(err), role))
            # A numeric template can mask a missing PV/grid/battery source.
            if not all(role in values for role in HISTORY_ROLES):
                issues.add(Issue("invalid_input", "home"))
                continue
            energy += values["home"] / 1000 * (right - left).total_seconds() / 3600
        result.append(
            HistorySlot(
                cursor,
                stop,
                None if issues else energy,
                tuple(sorted(issues, key=lambda issue: (issue.source, issue.code))),
            )
        )
        cursor = stop
    return tuple(result)
