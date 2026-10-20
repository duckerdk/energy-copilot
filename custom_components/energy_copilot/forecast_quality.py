"""Explicit forecast coverage; absent solar hours never become invented zeros."""

from .models import ForecastSnapshot, PriceSlot


def forecast_coverage(snapshot: ForecastSnapshot, prices: tuple[PriceSlot, ...], now):
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
    return {
        "expected_seconds": expected_seconds,
        "covered_seconds": covered_seconds,
        "coverage_fraction": covered_seconds / expected_seconds
        if expected_seconds
        else None,
        "source_first_boundary_utc": first.isoformat(),
        "source_last_boundary_utc": last.isoformat(),
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
        "missing_energy_timestamps_utc": [
            t.isoformat() for t in snapshot.missing_energy_at
        ],
    }
