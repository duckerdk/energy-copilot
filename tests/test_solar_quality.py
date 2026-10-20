"""Night evidence, missing daylight and decision-time provenance remain distinct."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.energy_copilot.forecast_history import ForecastHistory
from custom_components.energy_copilot.forecast_quality import (
    forecast_coverage,
    periods_for_decision,
)
from custom_components.energy_copilot.models import Issue, PriceSlot
from custom_components.energy_copilot.quality import quality_report
from custom_components.energy_copilot.solar import solar_evidence
from custom_components.energy_copilot.validation import forecast, utc

from .conftest import NOW
from .test_validation import forecast_response

# Public, approximate Danish coordinates; not the user's private PV location.
LOCATION = {"latitude": 56, "longitude": 9}


def evening_snapshot():
    first, last = utc("2026-10-21T18:00:00+02:00"), utc("2026-10-21T18:06:30+02:00")
    return forecast(
        {
            "watts": {first.isoformat(): 162, last.isoformat(): 0},
            "wh_period": {first.isoformat(): 100, last.isoformat(): 9},
        },
        first,
    )


def test_reported_evening_gap_is_partitioned_into_twilight_and_civil_night():
    snapshot = evening_snapshot()
    end = utc("2026-10-22T00:00:00+02:00")
    solar = solar_evidence(LOCATION, snapshot.captured_at, end, snapshot.captured_at)
    periods = snapshot.periods
    result = forecast_coverage(
        snapshot,
        (PriceSlot(snapshot.captured_at, end, 1, 1),),
        snapshot.captured_at,
        solar=solar,
    )
    assert solar["available"]
    assert snapshot.periods == periods and periods[-1].kwh == 0.009
    assert solar["zero_energy_inserted"] is False
    assert len(result["missing_intervals"]) == 1
    assert result["missing_intervals"][0]["zero_production_verified"] is False
    assert result["unpublished_night_seconds"] > 5 * 3600
    assert (
        result["unresolved_forecast_seconds"] > 0
    )  # No zero-energy twilight assumption.
    assert (
        result["unpublished_night_seconds"] + result["unresolved_forecast_seconds"]
        == 5 * 3600 + 53 * 60 + 30
    )
    assert result["covered_seconds"] == 390
    categories = quality_report(
        [Issue("forecast_horizon_incomplete", "forecast_solar")], result
    )
    assert categories["categories"]["blocking"] == 1
    assert "latitude" not in str(solar) and "longitude" not in str(solar)


def test_night_only_missing_forecast_is_information_without_energy_substitution():
    snapshot = evening_snapshot()
    start, end = utc("2026-10-21T20:00:00+02:00"), utc("2026-10-22T00:00:00+02:00")
    solar = solar_evidence(LOCATION, start, end, start)
    result = forecast_coverage(
        snapshot, (PriceSlot(start, end, 1, 1),), start, solar=solar
    )
    assert result["covered_seconds"] == 0
    assert result["unpublished_night_seconds"] == 4 * 3600
    assert result["unresolved_forecast_seconds"] == 0
    assert len(result["missing_intervals"]) == 1  # Retain source absence for audit.
    report = quality_report(
        [Issue("forecast_horizon_incomplete", "forecast_solar")], result
    )
    assert report["categories"]["informational"] == 1
    assert report["issues"][0]["effect"] == "night_energy_policy_required"
    assert report["planning_readiness"] == "not_evaluated_m2"


@pytest.mark.parametrize(
    "location",
    [
        {},
        {"latitude": True, "longitude": 9},
        {"latitude": 91, "longitude": 9},
        {"latitude": "nan", "longitude": 9},
        {"latitude": 90, "longitude": 0},
    ],
)
def test_missing_invalid_or_polar_location_cannot_establish_night(location):
    snapshot = evening_snapshot()
    start, end = utc("2026-10-21T20:00:00+02:00"), utc("2026-10-22T00:00:00+02:00")
    solar = solar_evidence(location, start, end, start)
    assert not solar["available"] and not solar["intervals"]
    result = forecast_coverage(
        snapshot, (PriceSlot(start, end, 1, 1),), start, solar=solar
    )
    assert result["unpublished_night_seconds"] == 0
    assert result["unresolved_forecast_seconds"] == 4 * 3600
    assert {
        g["solar_state"] for g in result["unpublished_intervals_by_solar_state"]
    } == {"unknown"}
    assert (
        quality_report(
            [Issue("forecast_horizon_incomplete", "forecast_solar")], result
        )["categories"]["blocking"]
        == 1
    )


def test_missing_daytime_wh_is_not_night_even_with_zero_watts():
    start = utc("2026-10-21T09:00:00+02:00")
    points = [start + timedelta(hours=h) for h in range(3)]
    snapshot = forecast(
        {
            "watts": {p.isoformat(): 0 for p in points},
            "wh_period": {points[0].isoformat(): 0, points[2].isoformat(): 0},
        },
        start,
    )
    result = forecast_coverage(
        snapshot,
        (PriceSlot(start, points[-1], 1, 1),),
        start,
        solar=solar_evidence(LOCATION, start, points[-1], start),
    )
    assert result["unpublished_night_seconds"] == 0
    assert result["unresolved_forecast_seconds"] == 3600
    assert (
        result["unpublished_intervals_by_solar_state"][0]["solar_state"] == "daylight"
    )
    assert result["missing_energy_timestamps_utc"] == [points[1].isoformat()]


@pytest.mark.parametrize("day,hours", [("2026-03-29", 23), ("2026-10-25", 25)])
def test_solar_windows_cover_dst_day_exactly_once_in_utc(day, hours):
    zone = ZoneInfo("Europe/Copenhagen")
    start = utc(datetime.fromisoformat(day).replace(tzinfo=zone))
    end = start + timedelta(hours=hours)
    result = solar_evidence(LOCATION, start, end, start)
    assert result["available"]
    intervals = result["intervals"]
    assert (
        utc(intervals[0]["start_utc"]) == start and utc(intervals[-1]["end_utc"]) == end
    )
    assert (
        sum(
            (utc(w["end_utc"]) - utc(w["start_utc"])).total_seconds() for w in intervals
        )
        == hours * 3600
    )
    assert all(a["end_utc"] == b["start_utc"] for a, b in zip(intervals, intervals[1:]))
    assert {w["solar_state"] for w in intervals} == {
        "daylight",
        "twilight",
        "civil_night",
    }


def test_pv_location_controls_night_not_machine_timezone_or_default_home():
    start, end = utc("2026-10-21T22:00:00+00:00"), utc("2026-10-21T23:00:00+00:00")
    denmark = solar_evidence(LOCATION, start, end, start)
    australia = solar_evidence(
        {"latitude": -33.8, "longitude": 151.2}, start, end, start
    )
    assert {w["solar_state"] for w in denmark["intervals"]} == {"civil_night"}
    assert {w["solar_state"] for w in australia["intervals"]} == {"daylight"}


async def test_decision_input_rejects_future_observations_and_started_period_energy(
    hass,
):
    archive = ForecastHistory(hass, "decision-time")
    captured = NOW + timedelta(minutes=31)
    snapshot = await archive.async_record(forecast_response(), captured, "solar")
    assert snapshot.periods[0].start == NOW and snapshot.periods[0].kwh == 1
    assert periods_for_decision(snapshot, NOW) == ()
    assert archive.decision_periods_as_of(captured - timedelta(microseconds=1)) == ()
    assert archive.as_of(captured).periods[0].kwh == 1  # Audit remains unchanged.
    decision_periods = archive.decision_periods_as_of(captured)
    assert decision_periods == snapshot.periods[1:]
    assert decision_periods[0].kwh == 0.5
    assert all(p.start >= captured for p in decision_periods)
    assert archive.decision_periods_as_of(captured, source_entry="other") == ()


def test_quality_separates_required_inputs_history_and_information():
    issues = [
        Issue("invalid_input", "home"),
        Issue("historical_quality_unverifiable", "recorder"),
        Issue("home_profile_unverified", "home"),
        Issue("optional_entity_unconfigured", "voltage"),
        Issue("forecast_observed_after_period_start", "forecast_solar"),
        Issue("new_unknown_failure", "new_source"),
    ]
    report = quality_report(issues)
    assert report["categories"] == {
        "blocking": 2,
        "uncertainty": 0,
        "historical": 2,
        "informational": 2,
    }
    assert len(report["issues"]) == len(issues)
    assert report["night_classification_supplies_forecast_energy"] is False


async def test_native_lifecycle_exposes_night_quality_without_replacing_forecast(
    hass, populated_hass, entry
):
    import json
    from pathlib import Path
    from unittest.mock import AsyncMock

    from homeassistant.core import SupportsResponse
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.energy_copilot.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    source = json.loads(
        (
            Path(__file__).parent / "fixtures" / "forecast_solar_end_contract.json"
        ).read_text()
    )["response"]
    solar = MockConfigEntry(domain="forecast_solar", data=LOCATION)
    solar.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={"forecast_entry": solar.entry_id}
    )
    zone = ZoneInfo("Europe/Copenhagen")
    points = [NOW + timedelta(hours=h) for h in range(36)]
    for role in ("buy", "sell"):
        old = hass.states.get(entry.data[role])
        attrs = dict(old.attributes)
        attrs.update(
            raw_today=[
                {"hour": p.isoformat(), "price": 1}
                for p in points
                if p.astimezone(zone).date() == NOW.astimezone(zone).date()
            ],
            raw_tomorrow=[
                {"hour": p.isoformat(), "price": 1}
                for p in points
                if p.astimezone(zone).date() != NOW.astimezone(zone).date()
            ],
            tomorrow_valid=True,
        )
        hass.states.async_set(old.entity_id, old.state, attrs)
    callback = AsyncMock(return_value=source)
    hass.services.async_register(
        "forecast_solar",
        "get_forecast",
        callback,
        supports_response=SupportsResponse.ONLY,
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    first = entry.runtime_data.coordinator
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    coverage = diagnostic["observed"]["forecast_coverage"]
    assert coverage["unpublished_night_seconds"] > 5 * 3600
    assert coverage["unresolved_forecast_seconds"] > 0
    assert coverage["solar_evidence"]["available"]
    assert diagnostic["quality"]["categories"]["blocking"] >= 1
    assert diagnostic["quality"]["categories"]["historical"] >= 1
    assert diagnostic["quality"]["planning_readiness"] == "not_evaluated_m2"
    state = hass.states.get("sensor.energy_co_pilot_input_quality")
    assert (
        state.state == "valid"
        and state.attributes["issue_categories"] == diagnostic["quality"]["categories"]
    )
    assert diagnostic["read_only"] and first.data.forecast.periods[-1].kwh == 0.009
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator is not first
    assert (await async_get_config_entry_diagnostics(hass, entry))["observed"][
        "forecast_coverage"
    ]["solar_evidence"]["available"]
    reloaded = entry.runtime_data.coordinator
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert first.history_reader._closed and reloaded.history_reader._closed
