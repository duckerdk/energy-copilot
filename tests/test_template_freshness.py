"""The configured PV input is exclusively sensor.pv_sum."""

from datetime import timedelta

import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_copilot.const import DEFAULT_ENTITIES, DOMAIN
from custom_components.energy_copilot.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.energy_copilot.live_measurements import derived_templates
from custom_components.energy_copilot.models import Issue
from custom_components.energy_copilot.quality import quality_report
from custom_components.energy_copilot.validation import measurements

from .conftest import NOW, make_state


@pytest.fixture
async def native_templates(hass, settings, source_states, freezer):
    freezer.move_to(NOW)
    for role, state in source_states.items():
        if role not in {"pv", "home"}:
            hass.states.async_set(state.entity_id, state.state, dict(state.attributes))
    hass.states.async_set("sensor.raw_pv_total", "0", {"unit_of_measurement": "W"})
    hass.states.async_set("switch.sun12k_solar_sell", "off")
    assert await async_setup_component(
        hass,
        "template",
        {
            "template": [
                {
                    "sensor": [
                        {
                            "name": "PV sum",
                            "unit_of_measurement": "W",
                            "state": "{{ states('sensor.raw_pv_total') | float(0) }}",
                        },
                        {
                            "name": "Home energy consumption",
                            "unit_of_measurement": "W",
                            "state": "{{ states('sensor.pv_sum') | float(0) + states('sensor.sun12k_total_grid_power') | float(0) + states('sensor.sun12k_battery_output_power') | float(0) }}",
                        },
                    ],
                }
            ]
        },
    )
    await hass.async_start()
    await hass.async_block_till_done()
    entry = MockConfigEntry(domain=DOMAIN, data=settings, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(settings["pv"]).state == "0.0"
    assert hass.states.get(settings["home"]).state == "2200.0"
    return entry


async def test_stable_native_pv_and_home_need_no_string_sensor_inputs(
    hass, native_templates, freezer
):
    entry = native_templates
    coordinator = entry.runtime_data.coordinator
    assert set(derived_templates(hass, coordinator.entities)) == {"pv", "home"}
    initial_pv_report = hass.states.get(entry.data["pv"]).last_reported
    for _ in range(10):
        freezer.tick(timedelta(seconds=60))
        for role in ("grid", "battery", "soc"):
            state = hass.states.get(entry.data[role])
            hass.states.async_set(state.entity_id, state.state, dict(state.attributes))
        hass.states.async_set("sensor.raw_pv_total", "0", {"unit_of_measurement": "W"})
        await hass.async_block_till_done()
        await coordinator.async_refresh()
    assert hass.states.get(entry.data["pv"]).last_reported == initial_pv_report
    assert coordinator.data.measurements["pv"].value == 0
    assert coordinator.data.measurements["home"].value == 2200
    assert Issue("pv_template_time_unverified", "pv") not in coordinator.data.issues
    assert coordinator.live_window.summary(coordinator.data.at)["pv_rejected"] == 0
    assert not any(role in coordinator.entities for role in ("pv1", "pv2"))
    d = await async_get_config_entry_diagnostics(hass, entry)
    assert not any(
        role in d["observed"]["measurement_source_timing"] for role in ("pv1", "pv2")
    )


@pytest.mark.parametrize("bad", ["unknown", "unavailable", "nan"])
async def test_invalid_pv_sum_blocks_home(hass, native_templates, bad):
    entry = native_templates
    hass.states.async_set(entry.data["pv"], bad, {"unit_of_measurement": "W"})
    await entry.runtime_data.coordinator.async_refresh()
    assert "home" not in entry.runtime_data.coordinator.data.measurements


@pytest.mark.parametrize("bad", ["unknown", "unavailable", "nan"])
def test_bad_pv_sum_never_accepted_as_zero(bad):
    states = {r: make_state(r) for r in ("pv", "grid", "battery", "home")}
    states["pv"] = make_state("pv", bad)
    values, _, _ = measurements(
        states, NOW, derived_templates={"pv": (), "home": ("pv", "grid", "battery")}
    )
    assert "home" not in values


def test_unchanged_native_pv_and_home_keep_real_timestamp_and_uncertainty():
    states = {
        "pv": make_state("pv", 0, at=NOW - timedelta(hours=8)),
        "grid": make_state("grid"),
        "battery": make_state("battery"),
        "home": make_state("home", 2200, at=NOW - timedelta(hours=8)),
    }
    values, _, issues = measurements(
        states, NOW, derived_templates={"pv": (), "home": ("pv", "grid", "battery")}
    )
    assert values["pv"].at == NOW - timedelta(hours=8)
    assert values["home"].at == NOW - timedelta(hours=8)
    assert Issue("pv_template_time_unverified", "pv") not in issues
    assert quality_report(issues)["input_state"] == "uncertain"


def test_stable_zero_non_native_pv_is_accepted():
    states = {r: make_state(r) for r in ("pv", "grid", "battery", "home")}
    states["pv"] = make_state("pv", 0, at=NOW - timedelta(hours=8))
    values, _, issues = measurements(states, NOW)
    assert "home" not in values
    assert Issue("stale_input", "pv") in issues


def test_old_home_must_match_pv_sum_grid_battery():
    states = {r: make_state(r) for r in ("pv", "grid", "battery", "home")}
    states["home"] = make_state("home", 12345, at=NOW - timedelta(hours=2))
    values, _, issues = measurements(
        states, NOW, derived_templates={"home": ("pv", "grid", "battery")}
    )
    assert "home" not in values
    assert Issue("derived_value_inconsistent", "home") in issues


def test_pv_recovery_needs_new_template_report():
    states = {r: make_state(r) for r in ("pv", "grid", "battery", "home")}
    states["pv"] = make_state("pv", 0, at=NOW - timedelta(hours=2))
    values, _, issues = measurements(
        states,
        NOW,
        derived_templates={"pv": (), "home": ("pv", "grid", "battery")},
        source_recovery_at={"pv": NOW - timedelta(seconds=20)},
    )
    assert "pv" not in values and "home" not in values
    assert Issue("stale_input", "pv") in issues


def test_input_mapping_is_only_pv_sum():
    assert DEFAULT_ENTITIES["pv"] == "sensor.pv_sum"
    assert "pv1" not in DEFAULT_ENTITIES and "pv2" not in DEFAULT_ENTITIES
