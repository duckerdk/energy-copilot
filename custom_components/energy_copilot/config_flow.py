"""UI source mapping. Only monitor/dry_run are supported; neither can write."""

from typing import Any

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import callback, valid_entity_id
from homeassistant.helpers import selector

from .const import (
    DEFAULT_ENTITIES,
    DEFAULT_FORECAST_MAX_VERSIONS,
    DEFAULT_FORECAST_RETENTION_DAYS,
    DOMAIN,
    MAX_FORECAST_RETENTION_DAYS,
    MAX_FORECAST_VERSIONS,
    OPTIONAL_ENTITY_ROLES,
    REQUIRED_ENTITY_ROLES,
)

RETENTION_SETTINGS = {
    "forecast_retention_days": (
        DEFAULT_FORECAST_RETENTION_DAYS,
        MAX_FORECAST_RETENTION_DAYS,
    ),
    "forecast_max_versions": (DEFAULT_FORECAST_MAX_VERSIONS, MAX_FORECAST_VERSIONS),
}
OPTIONAL_SETTINGS = (*sorted(OPTIONAL_ENTITY_ROLES), "solar_sell", "forecast_entry", "load_statistic")


def _optional_key(name, current, suggestion=None):
    """Suggest existing values without reinserting deliberately cleared fields."""
    value = current.get(name, suggestion)
    description = {"suggested_value": value} if value else {}
    return vol.Optional(name, description=description)


def schema(current):
    fields = {
        vol.Required(
            "mode", default=current.get("mode", "monitor")
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=["monitor", "dry_run"])
        ),
    }
    for role, entity_id in DEFAULT_ENTITIES.items():
        key = (
            vol.Required(role, default=current.get(role, entity_id))
            if role in REQUIRED_ENTITY_ROLES
            else _optional_key(role, current, entity_id)
        )
        fields[key] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        )
    fields[_optional_key("load_statistic", current)] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor")
    )
    fields[_optional_key("forecast_entry", current)] = selector.ConfigEntrySelector(
        selector.ConfigEntrySelectorConfig(integration="forecast_solar")
    )
    fields[_optional_key("solar_sell", current, "switch.sun12k_solar_sell")] = (
        selector.EntitySelector(selector.EntitySelectorConfig(domain="switch"))
    )
    for name, (default, maximum) in RETENTION_SETTINGS.items():
        fields[vol.Required(name, default=current.get(name, default))] = (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
                )
            )
        )
    return vol.Schema(fields)


def validate(hass, data):
    errors = {}
    # Required sensors may be unavailable, but must be mapped to existing entities.
    # Missing optional diagnostics can be mapped in advance; runtime reports their quality.
    for role in (*DEFAULT_ENTITIES, "solar_sell", "load_statistic"):
        entity_id = data.get(role)
        if not entity_id and role not in REQUIRED_ENTITY_ROLES:
            continue
        domain = "switch" if role == "solar_sell" else "sensor"
        if (
            not isinstance(entity_id, str)
            or not valid_entity_id(entity_id)
            or not entity_id.startswith(domain + ".")
            or (role in REQUIRED_ENTITY_ROLES and hass.states.get(entity_id) is None)
        ):
            errors[role] = "entity_missing"
    selected = [data[r] for r in DEFAULT_ENTITIES if data.get(r)]
    if len(set(selected)) != len(selected):
        errors["base"] = "duplicate_entity"
    if data.get("mode") not in {"monitor", "dry_run"}:
        errors["mode"] = "read_only"
    if entry_id := data.get("forecast_entry"):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != "forecast_solar":
            errors["forecast_entry"] = "forecast_entry_missing"
    for name, (default, maximum) in RETENTION_SETTINGS.items():
        value = data.get(name, default)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 1 <= value <= maximum
            or value != int(value)
        ):
            errors[name] = "invalid_retention"
    return errors


def normalize(data):
    """Persist explicit removals so old entry.data cannot restore optional mappings."""
    result = {key: value for key, value in data.items() if key not in {"pv1", "pv2"}}
    for name in OPTIONAL_SETTINGS:
        result[name] = data.get(name) or None
    for name, (default, _) in RETENTION_SETTINGS.items():
        result[name] = int(data.get(name, default))
    return result


class EnergyCopilotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            errors = validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title="Energy Co-Pilot", data=normalize(user_input)
                )
        return self.async_show_form(
            step_id="user", data_schema=schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return EnergyCopilotOptionsFlow()


class EnergyCopilotOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            errors = validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="", data=normalize(user_input))
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=schema(user_input or current), errors=errors
        )
