"""Configuration accepts core sources without requiring diagnostic entities."""

from unittest.mock import patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.energy_copilot.config_flow import normalize, schema, validate
from custom_components.energy_copilot.const import (
    DEFAULT_ENTITIES,
    DOMAIN,
    OPTIONAL_ENTITY_ROLES,
    REQUIRED_ENTITY_ROLES,
)


def minimal_settings(settings):
    return {
        key: value
        for key, value in settings.items()
        if key in REQUIRED_ENTITY_ROLES or key == "mode"
    }


async def test_minimal_config_ignores_missing_optional_entities(
    hass, populated_hass, settings
):
    for role in OPTIONAL_ENTITY_ROLES:
        hass.states.async_remove(DEFAULT_ENTITIES[role])
    hass.states.async_remove("switch.sun12k_solar_sell")
    with patch("custom_components.energy_copilot.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], minimal_settings(settings)
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert all(result["data"][role] is None for role in OPTIONAL_ENTITY_ROLES)
        assert result["data"]["solar_sell"] is None
        assert result["data"]["forecast_entry"] is None
        assert result["data"]["forecast_retention_days"] == 90
        assert result["data"]["forecast_max_versions"] == 10_000
        await hass.async_block_till_done()


async def test_partial_optional_mapping_keeps_manual_entity_ids(
    hass, populated_hass, settings
):
    data = {
        **minimal_settings(settings),
        "pv1": "sensor.custom_pv1",
        "voltage": "sensor.voltage_not_loaded",
        "solar_sell": "switch.optional_not_loaded",
    }
    hass.states.async_set("sensor.custom_pv1", "unavailable")
    with patch("custom_components.energy_copilot.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"]["pv1"] == "sensor.custom_pv1"
        assert result["data"]["voltage"] == "sensor.voltage_not_loaded"
        assert result["data"]["solar_sell"] == "switch.optional_not_loaded"
        assert result["data"]["pv2"] is None
        await hass.async_block_till_done()


async def test_required_missing_entity_still_blocks_configuration(
    hass, populated_hass, settings
):
    data = {**minimal_settings(settings), "grid": "sensor.grid_missing"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"grid": "entity_missing"}


def test_optional_suggestions_do_not_restore_cleared_values(settings):
    data = minimal_settings(settings)
    result = schema(settings)(data)
    assert all(role not in result for role in OPTIONAL_ENTITY_ROLES)
    assert "solar_sell" not in result and "forecast_entry" not in result
    normalized = normalize(result)
    merged = {**settings, **normalized}
    assert all(merged[role] is None for role in OPTIONAL_ENTITY_ROLES)
    assert merged["solar_sell"] is None
    assert "pv1" not in schema(merged)(data)


def test_duplicate_validation_ignores_unconfigured_optional_sources(
    hass, populated_hass, settings
):
    data = normalize(minimal_settings(settings))
    assert validate(hass, data) == {}
    data["pv1"] = data["pv"]
    assert validate(hass, data) == {"base": "duplicate_entity"}


@pytest.mark.parametrize(
    "role,entity",
    [
        ("pv1", "switch.pv1"),
        ("voltage", "not_an_entity"),
        ("solar_sell", "sensor.solar_sell"),
    ],
)
def test_invalid_optional_mapping_is_rejected(
    hass, populated_hass, settings, role, entity
):
    errors = validate(hass, {**minimal_settings(settings), role: entity})
    assert errors == {role: "entity_missing"}


@pytest.mark.parametrize(
    "name,bad",
    [
        ("forecast_retention_days", 0),
        ("forecast_retention_days", 367),
        ("forecast_retention_days", 1.5),
        ("forecast_retention_days", True),
        ("forecast_max_versions", 0),
        ("forecast_max_versions", 50_001),
        ("forecast_max_versions", 100.5),
        ("forecast_max_versions", float("nan")),
    ],
)
def test_retention_requires_bounded_whole_numbers(
    hass, populated_hass, settings, name, bad
):
    assert validate(hass, {**minimal_settings(settings), name: bad}) == {
        name: "invalid_retention"
    }


@pytest.mark.parametrize("days,versions", [(1, 1), (366, 50_000)])
async def test_retention_boundaries_are_accepted(
    hass, populated_hass, settings, days, versions
):
    data = {
        **minimal_settings(settings),
        "forecast_retention_days": days,
        "forecast_max_versions": versions,
    }
    with patch("custom_components.energy_copilot.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"]["forecast_retention_days"] == days
        assert result["data"]["forecast_max_versions"] == versions
        assert isinstance(result["data"]["forecast_retention_days"], int)
        await hass.async_block_till_done()


async def test_options_remove_old_optional_mappings(
    hass, populated_hass, entry, settings
):
    """Legacy entry.data must not restore optional fields cleared in options."""
    with patch("custom_components.energy_copilot.async_reload_entry") as reload_entry:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], minimal_settings(settings)
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        assert all(entry.options[role] is None for role in OPTIONAL_ENTITY_ROLES)
        assert entry.options["solar_sell"] is None
        assert entry.options["forecast_entry"] is None
        reload_entry.assert_awaited_once()
