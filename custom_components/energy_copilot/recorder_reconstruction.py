"""Reconstruct Recorder state intervals without treating changes as heartbeats."""

from bisect import bisect_left, bisect_right
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from .const import HISTORY_ROLES
from .models import HistoryGap, HistorySlot, Issue
from .validation import number, utc


@dataclass(frozen=True)
class RecordingRun:
    """A recorded process lifetime; clean termination does not prove no pauses."""

    start: datetime
    end: datetime
    reliable: bool = True
    recorded_end: datetime | None = None


def recorded_power(role, state):
    if state is None or state.state in {"unknown", "unavailable"}:
        raise ValueError("invalid_input")
    try:
        value = number(state.state)
    except ValueError, TypeError, OverflowError:
        raise ValueError("invalid_input") from None
    if state.attributes.get("unit_of_measurement") != "W":
        raise ValueError("invalid_unit")
    if role == "home" and value < 0:
        raise ValueError("negative_home_power")
    if role == "pv" and value < 0:
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
    # A numeric float(0) template from an outage remains suspect until home
    # itself reports again after the source recovers. Do not infer freshness
    # from normal last_updated differences between otherwise valid sources.
    recovery_times = {}
    for role in ("pv", "grid", "battery"):
        latest, was_invalid, recovery_times[role] = None, False, []
        for state in series[role]:
            try:
                recorded_power(role, state)
            except ValueError:
                was_invalid = True
            else:
                if was_invalid:
                    latest = utc(state.last_updated)
                was_invalid = False
            recovery_times[role].append(latest)
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
        energy, observed_seconds, unobserved_seconds = 0.0, 0.0, 0.0
        issues, gaps, reason_seconds = set(), [], Counter()
        truncated = False
        for left, right in zip(cuts, cuts[1:]):
            duration = (right - left).total_seconds()
            segment_issues = set()
            run = next(
                (
                    candidate
                    for candidate in reversed(runs)
                    if candidate.start <= left and candidate.end >= right
                ),
                None,
            )
            values = {}
            if run is None:
                segment_issues.add(Issue("recorder_recording_gap", "recorder"))
                segment_issues.add(Issue("historical_quality_unverifiable", "recorder"))
            elif not run.reliable:
                segment_issues.add(Issue("recorder_run_uncertain", "recorder"))
                segment_issues.add(Issue("historical_quality_unverifiable", "recorder"))
            else:
                for role in HISTORY_ROLES:
                    if role in excluded:
                        segment_issues.add(Issue("recorder_entity_excluded", role))
                        continue
                    index = bisect_right(times[role], left) - 1
                    if index < 0 or times[role][index] < run.start:
                        segment_issues.add(
                            Issue("historical_quality_unverifiable", role)
                        )
                        continue
                    try:
                        values[role] = recorded_power(role, series[role][index])
                    except ValueError as err:
                        segment_issues.add(Issue(str(err), role))
                # Numeric home cannot repair missing PV/grid/battery sources.
                if not all(role in values for role in HISTORY_ROLES):
                    segment_issues.add(Issue("invalid_input", "home"))
                else:
                    home_at = times["home"][bisect_right(times["home"], left) - 1]
                    for role in ("pv", "grid", "battery"):
                        index = bisect_right(times[role], left) - 1
                        recovered_at = recovery_times[role][index]
                        if (
                            recovered_at is not None
                            and run.start <= recovered_at
                            and home_at < recovered_at
                        ):
                            segment_issues.add(
                                Issue("home_predates_source_recovery", "home")
                            )
            if segment_issues:
                issues.update(segment_issues)
                unobserved_seconds += duration
                for code in {i.code for i in segment_issues}:
                    reason_seconds[code] += duration
                reasons = tuple(
                    sorted(segment_issues, key=lambda i: (i.source, i.code))
                )
                if gaps and gaps[-1].end == left and gaps[-1].issues == reasons:
                    gaps[-1] = HistoryGap(gaps[-1].start, right, reasons)
                elif len(gaps) < 32:
                    gaps.append(HistoryGap(left, right, reasons))
                else:
                    truncated = True
            else:
                observed_seconds += duration
                energy += values["home"] / 1000 * duration / 3600
        result.append(
            HistorySlot(
                cursor,
                stop,
                None if issues else energy,
                tuple(sorted(issues, key=lambda issue: (issue.source, issue.code))),
                observed_home_kwh=energy if observed_seconds else None,
                observed_seconds=observed_seconds,
                unobserved_seconds=unobserved_seconds,
                unobserved_reason_seconds=tuple(sorted(reason_seconds.items())),
                unobserved_intervals=tuple(gaps),
                unobserved_intervals_truncated=truncated,
            )
        )
        cursor = stop
    return tuple(result)
