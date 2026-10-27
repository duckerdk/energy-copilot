"""Explicitly armed live control. OFF is STOP, not an inverter emergency stop."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DynamicControlSwitch(entry)])


class DynamicControlSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True
    _attr_name = "Automatic control ARM / STOP"
    _attr_icon = "mdi:shield-lock"

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_automatic_arm"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    @property
    def available(self):
        return self.coordinator.settings.get("mode") == "automatic"

    @property
    def is_on(self):
        return self.coordinator.dynamic_controller.armed

    @property
    def extra_state_attributes(self):
        control = self.coordinator.dynamic_controller
        return {
            "execution_state": control.status,
            "reason": control.reason,
            "last_plan_start": control.last_plan_start,
            "halted": control.halted,
            "active_tou_slot": control.active_tou_slot,
            "target_tou_soc": control.target_tou_soc,
            "target_tou_grid_charge": control.target_tou_grid_charge,
            "device_emergency_stop": False,
        }

    async def async_turn_on(self, **kwargs):
        self.coordinator.dynamic_controller.arm()
        await self.coordinator.async_request_refresh()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self.coordinator.dynamic_controller.stop()
        self.async_write_ha_state()
