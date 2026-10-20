"""User-approved home clamp, missing-data safety, sensor scope and private audits."""

import json
from copy import deepcopy
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import SupportsResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_copilot.const import DEFAULT_ENTITIES, HISTORY_ROLES
from custom_components.energy_copilot.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.energy_copilot.history import (
    RecorderHistoryReader,
    home_normalization_summary,
)
from custom_components.energy_copilot.home_quality import negative_home_audit
from custom_components.energy_copilot.models import Issue
from custom_components.energy_copilot.quality import quality_report
from custom_components.energy_copilot.recorder_reconstruction import (
    RecordingRun,
    reconstruct_history,
)
from custom_components.energy_copilot.validation import measurements

from .conftest import NOW, make_state
from .test_validation import forecast_response


@pytest.mark.parametrize("raw", [-0.001, -1768, -1_000_000, 0, 250])
def test_live_home_is_clamped_only_after_context_validation(source_states, raw):
    source_states["home"] = make_state("home", raw)
    before = source_states["home"].state
    values, _, issues = measurements(source_states, NOW)
    assert values["home"].value == max(0, raw)
    assert values["home"].raw_value == (raw if raw < 0 else None)
    assert source_states["home"].state == before
    assert ("negative_home_normalized" in {i.code for i in issues}) == (raw < 0)
    assert quality_report(issues)["categories"]["blocking"] == 0


@pytest.mark.parametrize(
    "role,value,unit,age",
    [
        ("pv", "unavailable", "W", 0),
        ("grid", "unknown", "W", 0),
        ("battery", "nan", "W", 0),
        ("home", "-inf", "W", 0),
        ("home", "unknown", "W", 0),
        ("home", -20, "kWh", 0),
        ("grid", 10, "kWh", 0),
        ("pv", -1, "W", 0),
        ("battery", 10, "W", 20),
        ("home", -20, "W", 301),
    ],
)
def test_live_invalid_context_never_becomes_normalized_zero(
    source_states, role, value, unit, age
):
    source_states["home"] = make_state("home", -20)
    source_states[role] = make_state(
        role, value, at=NOW - timedelta(seconds=age), unit=unit
    )
    values, _, issues = measurements(source_states, NOW)
    assert "home" not in values
    assert "negative_home_normalized" not in {i.code for i in issues}
    assert quality_report(issues)["input_state"] == "degraded"


def rows_at(start, home=1000):
    return {
        DEFAULT_ENTITIES[r]: [make_state(r, home if r == "home" else 0, at=start)]
        for r in HISTORY_ROLES
    }


def test_short_negative_pulse_changes_its_integral_without_losing_the_quarter():
    start = NOW - timedelta(minutes=15)
    rows = rows_at(start)
    rows[DEFAULT_ENTITIES["home"]].extend(
        [
            make_state("home", -1768, at=start + timedelta(seconds=100)),
            make_state("home", 1000, at=start + timedelta(seconds=102)),
        ]
    )
    slot = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, (RecordingRun(start, NOW),)
    )[0]
    assert slot.home_kwh == pytest.approx(898 / 3600)
    assert slot.observed_raw_home_kwh == pytest.approx(
        (1000 * 898 - 1768 * 2) / 3_600_000
    )
    assert slot.home_correction_kwh == pytest.approx(1768 * 2 / 3_600_000)
    assert slot.home_correction_seconds == 2 and slot.home_correction_records == 1
    assert slot.home_correction_segments == 1
    assert (
        slot.observed_seconds == 900
        and slot.unobserved_seconds == 0
        and not slot.issues
    )
    assert slot.home_kwh - slot.observed_raw_home_kwh == pytest.approx(
        slot.home_correction_kwh
    )


def test_continuing_negative_state_across_quarters_is_not_counted_as_new_rows():
    start = NOW - timedelta(minutes=30)
    rows = rows_at(start, home=-100)
    slots = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, (RecordingRun(start, NOW),)
    )
    assert [s.home_kwh for s in slots] == [0, 0]
    summary = home_normalization_summary(slots)
    assert summary["corrected_records"] == 1
    assert (
        summary["corrected_seconds"] == 1800
        and summary["corrected_observed_fraction"] == 1
    )
    assert summary["observed_raw_kwh"] == pytest.approx(-0.05)
    assert summary["correction_kwh"] == pytest.approx(0.05)
    assert not summary["physical_consumption_verified"]
    carry = reconstruct_history(
        rows,
        DEFAULT_ENTITIES,
        start + timedelta(minutes=15),
        NOW,
        (RecordingRun(start, NOW),),
    )[0]
    assert carry.home_correction_records == 0 and carry.home_correction_seconds == 900


@pytest.mark.parametrize(
    "role,value,unit",
    [
        ("pv", "unknown", "W"),
        ("grid", "unavailable", "W"),
        ("battery", "nan", "W"),
        ("home", "nan", "W"),
        ("home", -100, "kWh"),
        ("pv", -10, "W"),
    ],
)
def test_historical_invalid_context_is_not_an_observed_zero(role, value, unit):
    start = NOW - timedelta(minutes=15)
    rows = rows_at(start, home=-100)
    rows[DEFAULT_ENTITIES[role]] = [make_state(role, value, at=start, unit=unit)]
    slot = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, (RecordingRun(start, NOW),)
    )[0]
    assert slot.home_kwh is None and slot.observed_home_kwh is None
    assert slot.observed_raw_home_kwh is None
    assert slot.home_correction_seconds == 0 and slot.home_correction_records == 0
    assert slot.observed_seconds == 0 and slot.unobserved_seconds == 900


def test_untrusted_negative_template_after_source_failure_is_not_clamped():
    start = NOW - timedelta(minutes=15)
    rows = rows_at(start, home=-100)
    rows[DEFAULT_ENTITIES["grid"]].extend(
        [
            make_state("grid", "unavailable", at=start + timedelta(seconds=100)),
            make_state("grid", 0, at=start + timedelta(seconds=110)),
        ]
    )
    rows[DEFAULT_ENTITIES["home"]].append(
        make_state("home", -90, at=start + timedelta(seconds=120))
    )
    slot = reconstruct_history(
        rows, DEFAULT_ENTITIES, start, NOW, (RecordingRun(start, NOW),)
    )[0]
    assert slot.home_kwh is None
    assert slot.unobserved_seconds == 20 and slot.home_correction_seconds == 880
    assert dict(slot.unobserved_reason_seconds)["home_predates_source_recovery"] == 10
    assert slot.observed_home_kwh == 0
    assert slot.home_correction_records == 2


async def test_sensor_current_scope_retains_history_warnings_and_private_raw_values(
    hass, populated_hass, entry
):
    solar = MockConfigEntry(domain="forecast_solar")
    solar.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={"forecast_entry": solar.entry_id}
    )
    callback = AsyncMock(return_value=forecast_response())
    hass.services.async_register(
        "forecast_solar",
        "get_forecast",
        callback,
        supports_response=SupportsResponse.ONLY,
    )
    hass.states.async_set(entry.data["home"], "-25", {"unit_of_measurement": "W"})

    async def read_window(reader, start, end):
        rows = rows_at(start, home=-100)
        slots = reconstruct_history(
            rows, reader.entities, start, end, (RecordingRun(start, end),)
        )
        local = negative_home_audit(
            rows,
            reader.entities,
            start,
            end,
            (RecordingRun(start, end),),
            include_events=True,
        )
        reader.last_read_summary = {
            "recording_pause_history_verified": False,
            "negative_home_audit": local,
            "home_normalization": home_normalization_summary(slots),
        }
        # Simulate a separately requested local detailed audit in the backfill.
        reader.last_backfill_summary = {
            "negative_home_audit_last_chunk": deepcopy(local)
        }
        return slots

    with patch.object(RecorderHistoryReader, "async_read_window", new=read_window):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        coordinator = entry.runtime_data.coordinator
        sensor = hass.states.get("sensor.energy_co_pilot_input_quality")
        assert sensor.state == "valid"
        assert sensor.attributes["quality_scope"] == "required_current_inputs"
        assert sensor.attributes["planning_readiness"] == "not_evaluated_m2"
        assert (
            sensor.attributes["load_profile_readiness"]
            == "physical_validation_required"
        )
        assert sensor.attributes["issue_categories"]["historical"] >= 2
        assert sensor.attributes["issue_categories"]["informational"] >= 1
        assert {
            "home_profile_unverified",
            "recorder_pause_history_unverifiable",
            "negative_home_normalized",
        } <= set(sensor.attributes["issue_codes"])
        assert coordinator.data.measurements["home"].value == 0
        assert hass.states.get(entry.data["home"]).state == "-25"
        local = coordinator.history_reader.last_read_summary["negative_home_audit"]
        assert local["events"][0]["home_w"] == -100
        diagnostic = await async_get_config_entry_diagnostics(hass, entry)
        encoded = json.dumps(diagnostic)
        assert "home_w" not in encoded and "source_w" not in encoded
        assert (
            "events"
            not in diagnostic["observed"]["recent_history"]["negative_home_audit"]
        )
        assert (
            "events"
            not in diagnostic["observed"]["requested_history"][
                "negative_home_audit_last_chunk"
            ]
        )
        assert (
            local["events"][0]["home_w"] == -100
        )  # Export does not mutate local audit.
        assert diagnostic["observed"]["home_sample_normalized"]
        assert (
            diagnostic["observed"]["recent_history"]["home_normalization"][
                "corrected_seconds"
            ]
            == 86400
        )
        assert diagnostic["quality"]["input_state"] == "valid"
        assert not diagnostic["observed"]["recent_history"]["home_normalization"][
            "physical_consumption_verified"
        ]
        hass.states.async_set(
            entry.data["pv"], "unavailable", {"unit_of_measurement": "W"}
        )
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert (
            hass.states.get("sensor.energy_co_pilot_input_quality").state == "degraded"
        )
        assert "home" not in coordinator.data.measurements
        hass.states.async_set(entry.data["pv"], "3034", {"unit_of_measurement": "W"})
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get("sensor.energy_co_pilot_input_quality").state == "valid"
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("sensor.energy_co_pilot_input_quality").state == "valid"
        assert await hass.config_entries.async_unload(entry.entry_id)


def test_history_only_or_informational_issues_do_not_permanently_degrade_inputs():
    report = quality_report(
        [
            Issue("home_profile_unverified", "home"),
            Issue("recorder_pause_history_unverifiable", "recorder"),
            Issue("negative_home_normalized", "recorder"),
        ]
    )
    assert report["input_state"] == "valid"
    assert report["categories"] == {"blocking": 0, "historical": 2, "informational": 1}
    assert len(report["issues"]) == 3
    assert report["planning_readiness"] == "not_evaluated_m2"
    assert (
        quality_report([Issue("unknown_failure", "home")])["input_state"] == "degraded"
    )
