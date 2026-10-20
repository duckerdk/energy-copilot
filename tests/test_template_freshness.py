"""PR #10: stable native templates need live evidence from their base sources."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import SupportsResponse
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_copilot.const import DOMAIN
from custom_components.energy_copilot.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.energy_copilot.live_measurements import derived_templates
from custom_components.energy_copilot.models import Issue
from custom_components.energy_copilot.validation import measurements

from .conftest import NOW, make_state
from .test_validation import forecast_response


@pytest.fixture
async def native_templates(hass, settings, source_states, freezer):
    """Real YAML-style template entities without registry unique IDs."""
    freezer.move_to(NOW)
    for role, state in source_states.items():
        if role not in {"pv", "home"}:
            hass.states.async_set(
                state.entity_id,
                "0" if role in {"pv1", "pv2"} else state.state,
                dict(state.attributes),
            )
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
                            "state": "{{ states('sensor.sun12k_pv1_power') | float(0) + states('sensor.sun12k_pv2_power') | float(0) }}",
                        },
                        {
                            "name": "Home energy consumption",
                            "unit_of_measurement": "W",
                            "state": "{{ states('sensor.pv_sum') | float(0) + states('sensor.sun12k_total_grid_power') | float(0) + states('sensor.sun12k_battery_output_power') | float(0) }}",
                        },
                    ]
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


def report_leaves(hass, settings, *, omit=()):
    for role in ("pv1", "pv2", "grid", "battery", "soc"):
        if role not in omit:
            state = hass.states.get(settings[role])
            hass.states.async_set(state.entity_id, state.state, dict(state.attributes))


async def stable_for_ten_minutes(hass, entry, freezer):
    for _ in range(10):
        freezer.tick(timedelta(seconds=60))
        report_leaves(hass, entry.data)
        await hass.async_block_till_done()
        await entry.runtime_data.coordinator.async_refresh()


async def test_real_stable_night_pv_and_constant_home_use_live_leaf_evidence(
    hass, native_templates, freezer
):
    entry = native_templates
    coordinator = entry.runtime_data.coordinator
    originals = {
        r: hass.states.get(entry.data[r]).last_reported for r in ("pv", "home")
    }
    assert set(derived_templates(hass, coordinator.entities)) == {"pv", "home"}
    await stable_for_ten_minutes(hass, entry, freezer)
    for role in ("pv", "home"):
        sample = coordinator.data.measurements[role]
        assert (
            sample.at == originals[role] < coordinator.data.at - timedelta(seconds=300)
        )
        assert hass.states.get(entry.data[role]).last_reported == originals[role]
        assert sample.context_at == coordinator.data.at
        assert (
            Issue("derived_value_from_fresh_sources", role) in coordinator.data.issues
        )
        assert Issue("stale_input", role) not in coordinator.data.issues
    assert coordinator.data.measurements["pv"].value == 0
    assert coordinator.data.measurements["home"].value == 2200
    # Fresh Modbus leaves were observed; neither HA template was force-refreshed.
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    pv = diagnostic["observed"]["measurement_source_timing"]["pv"]
    assert pv["report_age_seconds"] >= 600
    assert pv["last_reported_utc"] == originals["pv"].isoformat()
    assert pv["freshness_time_basis"] == "validated_configured_sources"
    assert pv["context_oldest_report_utc"] == coordinator.data.at.isoformat()
    assert not pv["template_dependency_graph_verified"]
    window = diagnostic["observed"]["live_measurement_window"]
    assert window["home_rejected"] == 0
    assert window["home_retained_with_uncertainty"] == 5
    assert window["timing_seconds"]["source_report_skew_seconds"]["max"] >= 600
    assert window["timing_seconds"]["source_context_skew_seconds"]["max"] == 0
    assert Issue("forecast_entry_missing", "forecast_solar") in coordinator.data.issues
    assert coordinator.quality["input_state"] == "degraded"  # Independent forecast.


@pytest.mark.parametrize("dead", ["pv1", "pv2", "grid", "battery"])
async def test_dead_leaf_is_not_rescued_by_stable_native_templates(
    hass, native_templates, freezer, dead
):
    entry = native_templates
    await stable_for_ten_minutes(hass, entry, freezer)
    for _ in range(6):
        freezer.tick(timedelta(seconds=60))
        report_leaves(hass, entry.data, omit={dead})
        await hass.async_block_till_done()
        await entry.runtime_data.coordinator.async_refresh()
    coordinator = entry.runtime_data.coordinator
    assert "home" not in coordinator.data.measurements
    assert Issue("stale_input", dead) in coordinator.data.issues
    assert coordinator.quality["input_state"] == "degraded"


@pytest.mark.parametrize(
    "value,unit",
    [("unknown", "W"), ("unavailable", "W"), ("nan", "W"), ("0", "kWh"), (None, "W")],
)
async def test_float_zero_cannot_hide_bad_pv_leaf(
    hass, native_templates, freezer, value, unit
):
    entry = native_templates
    freezer.tick(timedelta(seconds=1))
    if value is None:
        hass.states.async_remove(entry.data["pv1"])
    else:
        hass.states.async_set(entry.data["pv1"], value, {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    assert hass.states.get(entry.data["pv"]).state == "0.0"
    await entry.runtime_data.coordinator.async_refresh()
    data = entry.runtime_data.coordinator.data
    assert "pv" not in data.measurements and "home" not in data.measurements
    assert Issue("derived_source_invalid", "pv") in data.issues
    assert not any(i.code == "negative_home_normalized" for i in data.issues)


async def test_leaf_outage_between_polls_keeps_unchanged_templates_untrusted(
    hass, native_templates, freezer
):
    entry = native_templates
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(
        entry.data["pv1"], "unavailable", {"unit_of_measurement": "W"}
    )
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(entry.data["pv1"], "0", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    await entry.runtime_data.coordinator.async_refresh()
    coordinator = entry.runtime_data.coordinator
    assert "home" not in coordinator.data.measurements
    assert Issue("derived_predates_source_recovery", "pv") in coordinator.data.issues
    # A real subsequent template evaluation/report re-establishes its context.
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(entry.data["pv1"], "10", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    await coordinator.async_refresh()
    assert coordinator.data.measurements["home"].value == 2210
    assert not coordinator.live_context.recovery_at


@pytest.mark.parametrize("removed", [("pv1",), ("pv1", "pv2")])
async def test_missing_optional_mappings_report_unverifiable_stable_pv(
    hass, native_templates, freezer, removed
):
    entry = native_templates
    hass.config_entries.async_update_entry(entry, options={r: None for r in removed})
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    # The template itself has live leaves, but Co-Pilot has no mapped evidence.
    await stable_for_ten_minutes(hass, entry, freezer)
    assert "home" not in coordinator.data.measurements
    assert Issue("stale_input", "pv") in coordinator.data.issues
    assert Issue("derived_freshness_unverifiable", "pv") in coordinator.data.issues
    assert all(coordinator.entities[r] is None for r in removed)
    assert all(
        Issue("optional_entity_unconfigured", r) in coordinator.data.issues
        for r in removed
    )


async def test_reload_accepts_old_native_values_only_with_current_valid_leaves(
    hass, native_templates, freezer
):
    entry = native_templates
    await stable_for_ten_minutes(hass, entry, freezer)
    old = entry.runtime_data.coordinator
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    new = entry.runtime_data.coordinator
    assert new is not old
    assert new.data.measurements["home"].value == 2200
    assert new.data.measurements["home"].context_at == new.data.at
    assert new.live_window.summary(new.data.at)["observations"] == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.states.async_set(entry.data["pv1"], "unknown", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert not new.live_context.recovery_at and not old.live_context.recovery_at


async def test_supported_old_templates_are_uncertain_with_healthy_forecast(
    hass, native_templates, freezer
):
    entry = native_templates
    await stable_for_ten_minutes(hass, entry, freezer)
    source = MockConfigEntry(domain="forecast_solar")
    source.add_to_hass(hass)
    hass.services.async_register(
        "forecast_solar",
        "get_forecast",
        AsyncMock(return_value=forecast_response()),
        supports_response=SupportsResponse.ONLY,
    )
    hass.config_entries.async_update_entry(
        entry, options={"forecast_entry": source.entry_id}
    )
    await hass.async_block_till_done()
    sensor = hass.states.get("sensor.energy_co_pilot_input_quality")
    assert sensor.state == "uncertain"
    assert sensor.attributes["home_available"]
    assert sensor.attributes["issue_categories"]["blocking"] == 0
    assert sensor.attributes["issue_categories"]["uncertainty"] == 2


@pytest.mark.parametrize("fault", ["unknown", "nan", "unit", "future", "inconsistent"])
def test_old_derived_payload_is_not_excused_by_healthy_components(fault):
    states = {r: make_state(r) for r in ("pv", "grid", "battery")}
    states["home"] = make_state(
        "home",
        value=fault if fault in {"unknown", "nan"} else 999,
        at=NOW + timedelta(seconds=11)
        if fault == "future"
        else NOW - timedelta(hours=2),
        unit="kWh" if fault == "unit" else "W",
    )
    values, _, issues = measurements(
        states, NOW, derived_templates={"home": ("pv", "grid", "battery")}
    )
    assert "home" not in values
    assert Issue("derived_value_from_fresh_sources", "home") not in issues
    if fault == "inconsistent":
        assert Issue("derived_value_inconsistent", "home") in issues


def test_old_signed_home_keeps_raw_value_context_and_approved_normalization():
    states = {
        "pv": make_state("pv", 0),
        "grid": make_state("grid", -300),
        "battery": make_state("battery", 100),
        "home": make_state("home", -200, at=NOW - timedelta(hours=2)),
    }
    values, _, issues = measurements(
        states, NOW, derived_templates={"home": ("pv", "grid", "battery")}
    )
    home = values["home"]
    assert home.value == 0 and home.raw_value == -200
    assert home.at == NOW - timedelta(hours=2) and home.context_at == NOW
    assert Issue("negative_home_normalized", "home") in issues
    assert Issue("derived_value_from_fresh_sources", "home") in issues
