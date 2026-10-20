"""Energy Co-Pilot M1/M2: native Home Assistant inputs, strictly read-only."""

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .build_info import async_installed_build
from .const import DOMAIN
from .coordinator import EnergyCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
PLATFORMS = [Platform.SENSOR]


@dataclass
class EnergyRuntimeData:
    coordinator: EnergyCoordinator
    installed_build: dict


type EnergyConfigEntry = ConfigEntry[EnergyRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: EnergyConfigEntry) -> bool:
    coordinator = EnergyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = EnergyRuntimeData(
        coordinator, await async_installed_build(hass)
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: EnergyConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EnergyConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.coordinator.history_reader.async_close()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: EnergyConfigEntry) -> None:
    from homeassistant.helpers.storage import Store

    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.forecasts").async_remove()
