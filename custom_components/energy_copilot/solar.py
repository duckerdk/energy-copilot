"""Solar geometry from the selected HA Forecast.Solar location; no provider API."""

from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import dawn, dusk, elevation, sunrise, sunset

from .models import ForecastPeriod
from .validation import number, utc


def solar_evidence(location, start, end, evaluated_at):
    """Partition a bounded horizon at civil/solar events, in UTC.

    Civil night (sun below -6 degrees) is conservative astronomical evidence,
    not measured zero production or a replacement Forecast.Solar energy series.
    Missing locations and polar event failures remain unverified, never night.
    No HA-home-location fallback: the selected PV installation may be elsewhere.
    """
    result = {
        "source": "forecast_solar_config_location_astral",
        "evaluated_at_utc": utc(evaluated_at).isoformat(),
        "available": False,
        "civil_night_solar_elevation_degrees": -6,
        "zero_energy_inserted": False,
        "location_coordinates_redacted": True,
        "intervals": [],
    }
    try:
        lat, lon = number(location["latitude"]), number(location["longitude"])
        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError("invalid_location")
        start, end = utc(start), utc(end)
        if end <= start or end - start > timedelta(days=4):
            raise ValueError("solar_horizon_out_of_bounds")
        observer = Observer(lat, lon, 0)
        cuts = {start, end}
        day = start.date() - timedelta(days=1)
        while day <= end.date() + timedelta(days=1):
            # Fail closed at polar latitudes; do not turn missing events into zeros.
            for event in (dawn, sunrise, sunset, dusk):
                at = event(observer, date=day)
                if start < at < end:
                    cuts.add(at)
            day += timedelta(days=1)
        points = sorted(cuts)
        for left, right in zip(points, points[1:]):
            angle = elevation(observer, left + (right - left) / 2)
            kind = (
                "civil_night"
                if angle < -6
                else "daylight"
                if angle >= 0
                else "twilight"
            )
            previous = result["intervals"][-1] if result["intervals"] else None
            if previous and previous["solar_state"] == kind:
                previous["end_utc"] = right.isoformat()
            else:
                result["intervals"].append(
                    {
                        "start_utc": left.isoformat(),
                        "end_utc": right.isoformat(),
                        "solar_state": kind,
                    }
                )
    except KeyError, TypeError, ValueError, OverflowError:
        result["reason"] = "location_or_solar_events_unverifiable"
        result["intervals"] = []
        return result
    result["available"] = True
    return result


def complete_night_forecast_edges(snapshot, solar, horizon_start, horizon_end):
    """Extend explicit 0 W sunrise/sunset boundaries through their local night.

    Forecast.Solar publishes no hourly Wh before the first sunrise 0 W marker
    or after the final sunset 0 W marker. Infer zero ONLY when the exact source
    edge reports 0 W AND the selected PV location confirms a sunrise/sunset
    within 30 minutes. Missing daytime intervals and missing energy records
    inside published periods are never replaced. The original archive is not
    changed: this returns a derived read-only planning snapshot.
    """
    if not solar or not solar.get("available") or not snapshot.periods:
        return snapshot
    start, end = utc(horizon_start), utc(horizon_end)
    if end <= start:
        return snapshot
    source_first = snapshot.source_start
    source_last = snapshot.source_end
    if source_first is None or source_last is None:
        return snapshot

    windows = solar["intervals"]
    sunrises = [
        utc(item["start_utc"]) for item in windows if item["solar_state"] == "daylight"
    ]
    sunsets = [
        utc(item["end_utc"]) for item in windows if item["solar_state"] == "daylight"
    ]
    tolerance = timedelta(minutes=30)
    zone = ZoneInfo("Europe/Copenhagen")
    modeled = []
    if (
        snapshot.first_watts_zero
        and start < source_first
        and any(abs(source_first - event) <= tolerance for event in sunrises)
    ):
        # Don't extend yesterday's unobserved night through the next daytime.
        local_day = source_first.astimezone(zone).date()
        midnight = datetime.combine(local_day, time.min, tzinfo=zone).astimezone(UTC)
        left = max(start, midnight)
        if left < source_first:
            modeled.append(ForecastPeriod(left, source_first, 0.0))

    if (
        snapshot.last_watts_zero
        and source_last < end
        and any(abs(source_last - event) <= tolerance for event in sunsets)
    ):
        next_day = source_last.astimezone(zone).date() + timedelta(days=1)
        midnight = datetime.combine(next_day, time.min, tzinfo=zone).astimezone(UTC)
        right = min(end, midnight)
        if source_last < right:
            modeled.append(ForecastPeriod(source_last, right, 0.0))

    if not modeled:
        return snapshot
    periods = tuple(sorted((*snapshot.periods, *modeled), key=lambda p: p.start))
    if any(a.end > b.start for a, b in zip(periods, periods[1:])):
        # An internal/overlapping provider period is not a valid night extension.
        return snapshot
    return replace(
        snapshot,
        periods=periods,
        night_zero_filled_seconds=sum(
            (p.end - p.start).total_seconds() for p in modeled
        ),
    )
