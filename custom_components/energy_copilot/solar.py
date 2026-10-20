"""Solar geometry from the selected HA Forecast.Solar location; no provider API."""

from datetime import timedelta

from astral import Observer
from astral.sun import dawn, dusk, elevation, sunrise, sunset

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
