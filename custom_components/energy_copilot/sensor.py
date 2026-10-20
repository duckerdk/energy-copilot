"""Diagnostic sensor; no actuator entities or services are registered."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([InputQualitySensor(entry)])


class InputQualitySensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "input_quality"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["valid", "degraded"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_input_quality"
        self._installed_build = entry.runtime_data.installed_build
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Energy Co-Pilot",
            manufacturer="Energy Co-Pilot",
            model="Read-only M1/M2",
            sw_version=entry.runtime_data.installed_build["installed_version"],
        )

    @property
    def native_value(self):
        return "degraded" if self.coordinator.data.issues else "valid"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        return {
            "mode": self.coordinator.settings.get("mode", "monitor"),
            "read_only": True,
            "installed_version": self._installed_build["installed_version"],
            "release_tag": self._installed_build["tag"],
            "release_commit": self._installed_build["commit"],
            "issue_codes": sorted({issue.code for issue in data.issues}),
            "price_slots": len(data.prices),
            "forecast_periods": len(data.forecast.periods) if data.forecast else 0,
            "history_valid_slots": sum(s.home_kwh is not None for s in data.history),
        }
