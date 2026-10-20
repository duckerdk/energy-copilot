"""UI source mapping. Only monitor/dry_run are supported; neither can write."""

from typing import Any

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULT_ENTITIES, DOMAIN


def schema(current):
    fields = {
        vol.Required(
            "mode", default=current.get("mode", "monitor")
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(options=["monitor", "dry_run"])
        ),
    }
    for role, entity_id in DEFAULT_ENTITIES.items():
        fields[vol.Required(role, default=current.get(role, entity_id))] = (
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
        )
    optional = (
        {"default": current["forecast_entry"]} if current.get("forecast_entry") else {}
    )
    fields[vol.Optional("forecast_entry", **optional)] = selector.ConfigEntrySelector(
        selector.ConfigEntrySelectorConfig(integration="forecast_solar")
    )
    fields[
        vol.Required(
            "solar_sell", default=current.get("solar_sell", "switch.sun12k_solar_sell")
        )
    ] = selector.EntitySelector(selector.EntitySelectorConfig(domain="switch"))
    return vol.Schema(fields)


def validate(hass, data):
    errors = {}
    # Unavailable sensors may be selected; runtime quality remains explicit.
    for role in (*DEFAULT_ENTITIES, "solar_sell"):
        entity_id = data.get(role, "")
        domain = "switch" if role == "solar_sell" else "sensor"
        if not entity_id.startswith(domain + ".") or hass.states.get(entity_id) is None:
            errors[role] = "entity_missing"
    if len({data.get(r) for r in DEFAULT_ENTITIES}) != len(DEFAULT_ENTITIES):
        errors["base"] = "duplicate_entity"
    if data.get("mode") not in {"monitor", "dry_run"}:
        errors["mode"] = "read_only"
    if entry_id := data.get("forecast_entry"):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != "forecast_solar":
            errors["forecast_entry"] = "forecast_entry_missing"
    return errors


class EnergyCopilotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            errors = validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(title="Energy Co-Pilot", data=user_input)
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
                return self.async_create_entry(title="", data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=schema(user_input or current), errors=errors
        )
