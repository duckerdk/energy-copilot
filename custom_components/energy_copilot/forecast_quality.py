"""Explicit forecast coverage; absent solar hours never become invented zeros."""

from .models import ForecastSnapshot, PriceSlot
from .validation import utc


def periods_for_decision(snapshot: ForecastSnapshot, decision_at):
    """Only complete future periods from an observation already available then.

    Started intervals remain in the raw snapshot for audit. Without an explicit
    intra-period model their full Wh cannot describe the remaining future part.
    """
    at = utc(decision_at)
    if snapshot.captured_at > at:
        return ()
    return tuple(p for p in snapshot.periods if p.start >= at)


def forecast_coverage(
    snapshot: ForecastSnapshot, prices: tuple[PriceSlot, ...], now, *, solar=None
):
    """Describe remaining price horizon gaps using the actual published boundaries."""
    periods = sorted(snapshot.periods, key=lambda period: period.start)
    first = snapshot.source_start or min(p.start for p in periods)
    last = snapshot.source_end or max(p.end for p in periods)
    gaps = []
    expected_seconds = covered_seconds = 0.0
    for slot in prices:
        start, end = max(slot.start, now), slot.end
        if start >= end:
            continue
        expected_seconds += (end - start).total_seconds()
        cursor = start
        for period in periods:
            left, right = max(start, period.start), min(end, period.end)
            if right <= left:
                continue
            if left > cursor:
                gaps.append((cursor, left))
            if right > cursor:
                covered_seconds += (right - max(cursor, left)).total_seconds()
                cursor = right
        if cursor < end:
            gaps.append((cursor, end))
    # Preserve provenance when a gap crosses a source horizon boundary.
    classified = []
    for start, end in gaps:
        cuts = sorted({start, end} | {t for t in (first, last) if start < t < end})
        for left, right in zip(cuts, cuts[1:]):
            reason = (
                "before_published_forecast"
                if right <= first
                else "after_published_forecast"
                if left >= last
                else "missing_energy_period"
            )
            if classified and classified[-1][1] == left and classified[-1][2] == reason:
                classified[-1] = (classified[-1][0], right, reason)
            else:
                classified.append((left, right, reason))
    solar_gaps = []
    windows = solar["intervals"] if solar and solar.get("available") else []
    for start, end, reason in classified:
        cursor = start
        for window in windows:
            left, right = (
                max(start, utc(window["start_utc"])),
                min(end, utc(window["end_utc"])),
            )
            if right <= left:
                continue
            if cursor < left:
                solar_gaps.append((cursor, left, reason, "unknown"))
            solar_gaps.append((left, right, reason, window["solar_state"]))
            cursor = right
        if cursor < end:
            solar_gaps.append((cursor, end, reason, "unknown"))
    night_seconds = sum(
        (b - a).total_seconds() for a, b, _, kind in solar_gaps if kind == "civil_night"
    )
    unresolved_seconds = sum(
        (b - a).total_seconds() for a, b, _, kind in solar_gaps if kind != "civil_night"
    )
    return {
        "expected_seconds": expected_seconds,
        "covered_seconds": covered_seconds,
        "coverage_fraction": covered_seconds / expected_seconds
        if expected_seconds
        else None,
        "source_first_boundary_utc": first.isoformat(),
        "source_last_boundary_utc": last.isoformat(),
        "solar_evidence": solar,
        "unpublished_night_seconds": night_seconds,
        "unresolved_forecast_seconds": unresolved_seconds,
        "unpublished_intervals_by_solar_state": [
            {
                "start_utc": a.isoformat(),
                "end_utc": b.isoformat(),
                "reason": reason,
                "solar_state": kind,
                "zero_production_verified": False,
            }
            for a, b, reason, kind in solar_gaps
        ],
        "missing_intervals": [
            {
                "start_utc": start.isoformat(),
                "end_utc": end.isoformat(),
                "reason": reason,
                "zero_production_verified": False,
            }
            for start, end, reason in classified
        ],
        "partially_elapsed_periods": sum(
            p.start < snapshot.captured_at < p.end for p in periods
        ),
        "unbounded_energy_timestamps_utc": [
            t.isoformat() for t in snapshot.unbounded_energy_at
        ],
        "unbounded_prior_energy_timestamps_utc": [
            t.isoformat() for t in snapshot.unbounded_prior_energy_at
        ],
        "energy_timestamp_semantics": "interval_end",
        "available_at_utc": snapshot.captured_at.isoformat(),
        "complete_periods_known_at_evaluation": len(
            periods_for_decision(snapshot, now)
        ),
        "started_period_energy_used_as_remaining": False,
        "missing_energy_timestamps_utc": [
            t.isoformat() for t in snapshot.missing_energy_at
        ],
    }
