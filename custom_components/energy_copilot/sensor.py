"""Diagnostic sensor; no actuator entities or services are registered."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            InputQualitySensor(entry),
            PlanningStatusSensor(entry),
            ModeledSavingSensor(entry),
        ]
    )


class InputQualitySensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "input_quality"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["valid", "uncertain", "degraded"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_input_quality"
        self._installed_build = entry.runtime_data.installed_build
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Energy Co-Pilot",
            manufacturer="Energy Co-Pilot",
            model="Read-only M1/M2/M3 preview",
            sw_version=entry.runtime_data.installed_build["installed_version"],
        )

    @property
    def native_value(self):
        return self.coordinator.quality["input_state"]

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
            "issue_categories": self.coordinator.quality["categories"],
            "quality_scope": self.coordinator.quality["quality_scope"],
            "forecast_state": self.coordinator.quality["forecast_state"],
            "load_profile_readiness": self.coordinator.quality[
                "load_profile_readiness"
            ],
            "planning_readiness": self.coordinator.quality["planning_readiness"],
            "live_measurement_acceptance": self.coordinator.quality[
                "live_measurement_acceptance"
            ],
            "home_available": "home" in data.measurements,
            "pv_available": "pv" in data.measurements,
            "price_slots": len(data.prices),
            "forecast_periods": len(data.forecast.periods) if data.forecast else 0,
            "history_valid_slots": sum(s.home_kwh is not None for s in data.history),
        }


class PlanningStatusSensor(CoordinatorEntity, SensorEntity):
    """Expose the dry-run outcome without presenting it as an executable plan."""

    _attr_has_entity_name = True
    _attr_translation_key = "planning_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["monitor", "blocked", "preview"]
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_planning_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    @property
    def native_value(self):
        return self.coordinator.planning_preview.status

    @property
    def extra_state_attributes(self):
        preview = self.coordinator.planning_preview
        return {
            "reason": preview.reason,
            "read_only": True,
            "executable": False,
            "scenario_type": "exploratory_single_grid_charge_discharge_cycle",
            "start_utc": preview.start.isoformat() if preview.start else None,
            "end_utc": preview.end.isoformat() if preview.end else None,
            "published_price_horizon_end_utc": (
                preview.published_price_horizon_end.isoformat()
                if preview.published_price_horizon_end
                else None
            ),
            "coverage": preview.coverage,
            "first_uncovered_at_utc": (
                preview.first_uncovered_at.isoformat()
                if preview.first_uncovered_at
                else None
            ),
            "quarters": preview.quarters,
            "pv_forecast_version": preview.pv_version,
            "load_model": preview.source_load_method,
            "load_modeled_quarters": preview.load_modeled_quarters,
            "pv_temporal_model": preview.pv_temporal_model,
            "pv_temporal_modeled_quarters": preview.pv_temporal_modeled_quarters,
            "reference_cost_dkk": preview.reference_cost_dkk,
            "scenario_cost_dkk": preview.scenario_cost_dkk,
            "modeled_saving_dkk": preview.modeled_saving_dkk,
            "max_charge_current_a": preview.max_charge_current_a,
            "charge_start_utc": (
                preview.charge_start.isoformat() if preview.charge_start else None
            ),
            "discharge_start_utc": (
                preview.discharge_start.isoformat() if preview.discharge_start else None
            ),
            "evaluated_scenarios": preview.evaluated_scenarios,
            "voltage_source": preview.voltage_source,
            "nominal_capacity_kwh": 10.24,
            "pv_forecast_dc_multiplier_assumed": 1.0,
            "model_efficiencies_assumed": 0.95,
            "physical_calibration_verified": False,
            "tou_six_window_feasibility_verified": False,
            "actual_deye_baseline_used": False,
        }


class ModeledSavingSensor(CoordinatorEntity, SensorEntity):
    """Counterfactual model comparison; not realized savings."""

    _attr_has_entity_name = True
    _attr_translation_key = "modeled_saving"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "DKK"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_modeled_saving"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )

    @property
    def native_value(self):
        preview = self.coordinator.planning_preview
        return preview.modeled_saving_dkk if preview.status == "preview" else None

    @property
    def extra_state_attributes(self):
        return {
            "simulation_only": True,
            "baseline": "no_battery_cycling_not_actual_deye",
            "not_actual_savings": True,
            "tou_verified": False,
        }
