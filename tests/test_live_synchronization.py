"""Issue #9: asynchronous reports are usable as-of, missing sources are not."""

import json
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import State, SupportsResponse
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_copilot.const import HISTORY_ROLES
from custom_components.energy_copilot.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.energy_copilot.live_measurements import (
    MAX_POLLS,
    LiveMeasurementWindow,
    LiveSourceContext,
)
from custom_components.energy_copilot.models import Issue
from custom_components.energy_copilot.quality import quality_report
from custom_components.energy_copilot.validation import live_timing, measurements

from .conftest import NOW, make_state
from .test_validation import forecast_response


def timed(role, *, age=0, change_age=None, value=None, now=NOW):
    state = make_state(role, value, at=now - timedelta(seconds=age))
    return State(
        state.entity_id,
        state.state,
        state.attributes,
        last_updated=now - timedelta(seconds=age if change_age is None else change_age),
        last_reported=state.last_reported,
    )


@pytest.mark.parametrize("spread", [10, 15, 20, 33.476170, 40, 299])
@pytest.mark.parametrize("home", [5234, -1768])
def test_modbus_as_of_spread_preserves_home_and_negative_policy(spread, home):
    states = {r: make_state(r) for r in HISTORY_ROLES}
    states["pv"] = timed("pv", age=spread)
    states["home"] = timed("home", value=home)
    values, _, issues = measurements(states, NOW)
    assert values["home"].value == max(0, home)
    assert values["home"].raw_value == (home if home < 0 else None)
    assert "measurement_time_skew" not in {i.code for i in issues}
    assert quality_report(issues)["input_state"] == (
        "uncertain" if spread > 10 else "valid"
    )
    assert not any(i.code == "snapshot_not_synchronous" for i in issues)


def test_public_issue9_single_age_snapshot_is_retained_with_explicit_uncertainty():
    # Only timing aggregates from the public issue; power values are synthetic.
    ages = {"pv": 35.739319, "grid": 2.264175, "battery": 4.875376, "home": 2.263149}
    states = {role: timed(role, age=age) for role, age in ages.items()}
    values, _, issues = measurements(states, NOW)
    assert "home" in values
    assert not issues
    assert live_timing(states)["all_report_skew_seconds"] == pytest.approx(33.476170)
    assert quality_report(issues)["input_state"] == "valid"
    report = quality_report(
        issues + [Issue("forecast_horizon_incomplete", "forecast_solar")]
    )
    assert report["input_state"] == "valid"
    assert report["categories"]["uncertainty"] == 0
    assert report["categories"]["blocking"] == 1


def test_unchanged_night_pv_report_is_not_confused_with_change_time():
    states = {r: make_state(r) for r in HISTORY_ROLES}
    states["pv"] = timed("pv", value=0, age=2, change_age=8 * 3600)
    values, _, issues = measurements(states, NOW)
    assert values["pv"].value == 0 and "home" in values
    assert not issues
    # A silent template is still silent, regardless of its numeric zero.
    states["pv"] = timed("pv", value=0, age=301, change_age=8 * 3600)
    values, _, issues = measurements(states, NOW)
    assert "home" not in values
    assert Issue("stale_input", "pv") in issues


def test_home_report_lag_tracks_changed_inputs_not_unchanged_heartbeats():
    states = {r: timed(r, change_age=200) for r in HISTORY_ROLES}
    states["home"] = timed("home", age=100)
    values, _, issues = measurements(states, NOW)
    assert "home" in values and not issues
    states["battery"] = timed("battery", change_age=1)
    values, _, issues = measurements(states, NOW)
    assert "home" in values
    assert {i.code for i in issues} == {"home_context_lag"}
    assert live_timing(states)["home_context_lag_seconds"] == 99


@pytest.mark.parametrize("role", HISTORY_ROLES)
@pytest.mark.parametrize(
    "fault", ["missing", "unknown", "unavailable", "nan", "unit", "stale", "future"]
)
def test_real_faults_still_reject_numeric_template(role, fault):
    states = {r: make_state(r) for r in HISTORY_ROLES}
    states["home"] = make_state("home", -20)
    states[role] = (
        None
        if fault == "missing"
        else make_state(role, fault)
        if fault in {"unknown", "unavailable", "nan"}
        else make_state(role, unit="kWh")
        if fault == "unit"
        else timed(\n            role,\n            value=100 if role == "pv" and fault == "stale" else None,\n            age=301 if fault == "stale" else -11,\n        )
    )
    values, _, issues = measurements(states, NOW)
    assert "home" not in values
    assert quality_report(issues)["input_state"] == "degraded"
    assert "negative_home_normalized" not in {i.code for i in issues}


def test_source_recovery_requires_new_home_report_even_for_masked_zero():
    context = LiveSourceContext()
    context.observe("grid", make_state("grid", "unavailable"), NOW)
    recovery = NOW + timedelta(seconds=5)
    context.observe("grid", make_state("grid", at=recovery), recovery)
    # Later source reports must not keep moving the already-known recovery boundary.
    context.observe(
        "grid",
        make_state("grid", at=recovery + timedelta(seconds=1)),
        recovery + timedelta(seconds=1),
    )
    assert context.recovery_at["grid"] == recovery
    states = {r: make_state(r) for r in HISTORY_ROLES}
    states["grid"] = make_state("grid", at=recovery)
    states["home"] = make_state("home", 0)
    values, _, issues = measurements(
        states, recovery, source_recovery_at=context.recovery_at
    )
    assert "home" not in values
    assert Issue("home_predates_source_recovery", "home") in issues
    states["home"] = make_state("home", -20, at=recovery)
    values, _, _ = measurements(
        states, recovery, source_recovery_at=context.recovery_at
    )
    assert values["home"].value == 0
    context.accept_home(values["home"])
    assert not context.recovery_at


def test_rapid_transitions_preserve_uncertainty_and_physical_checks(source_states):
    window = LiveMeasurementWindow()
    for seconds, pv, battery, home in (
        (0, 3034, 1000, 5234),
        (30, 0, -2000, -800),
        (60, 3034, 4000, 8234),
    ):
        now = NOW + timedelta(seconds=seconds)
        states = {
            r: timed(r, now=now) for r in source_states if r not in {"buy", "sell"}
        }
        states["pv"] = timed("pv", value=pv, age=35, now=now)
        states["battery"] = timed("battery", value=battery, now=now)
        states["home"] = timed("home", value=home, now=now)
        values, _, issues = measurements(states, now)
        window.record(states, now, values, issues)
        assert values["home"].value == max(0, home)
        assert Issue("measurement_time_skew", "home") not in issues
        if seconds:
            # Accepting temporal uncertainty must not suppress corroborating failures.
            assert Issue("battery_power_inconsistent", "battery") in issues
            assert quality_report(issues)["input_state"] == "degraded"
    summary = window.summary(now)
    assert summary["home_rejected"] == 0
    assert summary["source_change_with_uncertainty"] == 0


def test_window_percentiles_include_varied_ages_and_expire_by_utc():
    window = LiveMeasurementWindow()
    for age in (0, 10, 20, 30, 40, 50, 60):
        now = NOW + timedelta(seconds=age)
        states = {r: timed(r, now=now) for r in HISTORY_ROLES}
        states["pv"] = timed("pv", age=age, now=now)
        values, _, issues = measurements(states, now)
        window.record(states, now, values, issues)
    assert window.summary(now)["timing_seconds"][
        "pv_report_age_seconds"
    ] == pytest.approx(
        {
            "samples": 7,
            "p50": 30,
            "p95": 57,
            "max": 60,
        }
    )
    assert window.summary(NOW + timedelta(minutes=30, seconds=1))["observations"] == 6


def test_synthetic_half_hour_counts_and_percentiles_are_bounded_and_private():
    window = LiveMeasurementWindow()
    for index in range(60):
        now = NOW + timedelta(seconds=index * 30)
        states = {r: timed(r, now=now) for r in HISTORY_ROLES}
        states["pv"] = timed("pv", age=35, now=now)
        if index in {10, 20, 30}:
            states["grid"] = make_state("grid", "unavailable", at=now)
        values, _, issues = measurements(states, now)
        window.record(states, now, values, issues)
    summary = window.summary(now)
    assert summary["observations"] == 60
    assert summary["home_retained"] == 57 and summary["home_rejected"] == 3
    assert summary["home_retained_with_uncertainty"] == 0
    assert summary["source_change_with_uncertainty"] == 0
    assert summary["home_rejection_reasons"] == {
        "grid:invalid_input": 3,
        "home:invalid_input": 3,
    }
    assert summary["timing_seconds"]["source_report_skew_seconds"] == {
        "samples": 60,
        "p50": 35,
        "p95": 35,
        "max": 35,
    }
    encoded = json.dumps(summary)
    assert "5234" not in encoded and "3034" not in encoded
    assert "sensor." not in encoded and "home_w" not in encoded
    assert not summary["between_poll_transients_verified"]
    for _ in range(MAX_POLLS):
        window.record(states, now, values, issues)
    assert window.summary(now)["observations"] == MAX_POLLS
    assert window.summary(now)["capacity_evictions_this_runtime"] == 60
    assert window.summary(now + timedelta(minutes=31))["observations"] == 0
    window.record(states, now, values, issues)
    assert window.summary(NOW)["observations"] == 0
    assert window.clock_resets == 1


async def test_short_outage_between_polls_recovery_reload_and_listener_cleanup(
    hass, populated_hass, entry, freezer
):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(
        entry.data["grid"], "unavailable", {"unit_of_measurement": "W"}
    )
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(entry.data["grid"], "1200", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    await coordinator.async_refresh()
    assert "home" not in coordinator.data.measurements
    assert Issue("home_predates_source_recovery", "home") in coordinator.data.issues
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(entry.data["home"], "5234", {"unit_of_measurement": "W"})
    await coordinator.async_refresh()
    assert "home" in coordinator.data.measurements
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostic["observed"]["live_measurement_window"]["home_rejected"] == 1
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    replacement = entry.runtime_data.coordinator
    assert replacement is not coordinator
    assert (
        replacement.live_window.summary(NOW + timedelta(seconds=3))["observations"] == 1
    )
    hass.states.async_set(entry.data["grid"], "unknown", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert not coordinator.live_context.recovery_at  # Previous listener was removed.
    assert replacement.live_context.recovery_at == {"grid": None}
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.states.async_set(
        entry.data["battery"], "unknown", {"unit_of_measurement": "W"}
    )
    await hass.async_block_till_done()
    assert replacement.live_context.recovery_at == {"grid": None}


async def test_native_template_does_not_re_report_for_unchanged_dependency(
    hass, freezer
):
    freezer.move_to(NOW)
    hass.states.async_set("sensor.source_pv", "100")
    hass.states.async_set("sensor.source_grid", "200")
    assert await async_setup_component(
        hass,
        "template",
        {
            "template": [
                {
                    "sensor": [
                        {
                            "name": "Synthetic PV",
                            "unit_of_measurement": "W",
                            "state": "{{ states('sensor.source_pv') | float(0) }}",
                        },
                        {
                            "name": "Synthetic home",
                            "unit_of_measurement": "W",
                            "state": "{{ states('sensor.synthetic_pv') | float(0) + states('sensor.source_grid') | float(0) }}",
                        },
                    ]
                }
            ]
        },
    )
    await hass.async_start()
    await hass.async_block_till_done()
    home = hass.states.get("sensor.synthetic_home")
    assert home.state == "300.0"
    at = home.last_reported
    freezer.tick(timedelta(seconds=20))
    hass.states.async_set("sensor.source_pv", "100")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.source_pv").last_reported > at
    assert hass.states.get("sensor.synthetic_pv").last_reported <= at
    assert hass.states.get("sensor.synthetic_home").last_reported == at
    freezer.tick(timedelta(seconds=20))
    hass.states.async_set("sensor.source_grid", "300")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.synthetic_home").state == "400.0"
    assert hass.states.get("sensor.synthetic_home").last_reported > at
    assert (
        hass.states.get("sensor.synthetic_pv").last_reported
        < hass.states.get("sensor.synthetic_home").last_reported
    )


async def test_native_quality_sensor_uncertainty_and_blocking_are_distinct(
    hass, populated_hass, entry, freezer
):
    solar = MockConfigEntry(domain="forecast_solar")
    solar.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={"forecast_entry": solar.entry_id}
    )
    hass.services.async_register(
        "forecast_solar",
        "get_forecast",
        AsyncMock(return_value=forecast_response()),
        supports_response=SupportsResponse.ONLY,
    )
    freezer.tick(timedelta(seconds=40))
    for role in ("grid", "battery", "home"):
        old = hass.states.get(entry.data[role])
        hass.states.async_set(old.entity_id, old.state, dict(old.attributes))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sensor = hass.states.get("sensor.energy_co_pilot_input_quality")
    assert sensor.state == "valid"
    assert sensor.attributes["home_available"]
    assert sensor.attributes["issue_categories"]["blocking"] == 0
    assert sensor.attributes["issue_categories"]["uncertainty"] == 0
    assert "home" in entry.runtime_data.coordinator.data.measurements
    hass.states.async_set(entry.data["pv"], "unavailable", {"unit_of_measurement": "W"})
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    sensor = hass.states.get("sensor.energy_co_pilot_input_quality")
    assert sensor.state == "degraded"
    assert not sensor.attributes["home_available"]
