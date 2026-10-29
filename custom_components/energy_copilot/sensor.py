"""Quality and planning telemetry for the monitor, preview and control modes."""

from datetime import datetime
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

LOCAL_TIMEZONE = ZoneInfo("Europe/Copenhagen")


def local_timestamp(value):
    if value is None:
        return None
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    return moment.astimezone(LOCAL_TIMEZONE).isoformat()


def local_hourly_plan(hourly):
    return [{**row, "start": local_timestamp(row["start"])} for row in hourly]


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            InputQualitySensor(entry),
            PlanningStatusSensor(entry),
            ModeledSavingSensor(entry),
            ActualSavingYesterdaySensor(entry),
            SevenDayLoadSensor(entry),
            DecisionJournalSensor(entry),
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
            model="Energy Co-Pilot planner and guarded controller",
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
            "read_only": not self.coordinator.dynamic_controller.armed,
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
            "executable": self.coordinator.dynamic_controller.armed,
            "scenario_type": "whole_published_horizon_continuous_dispatch_unverified_tou",
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
            "purchase_cost_dkk": preview.purchase_cost_dkk,
            "sales_revenue_dkk": preview.sales_revenue_dkk,
            "terminal_value_basis": preview.terminal_value_basis,
            "pv_headroom_max_dc_kwh": preview.pv_headroom_max_dc_kwh,
            "pv_headroom_max_pct": preview.pv_headroom_max_pct,
            "pv_headroom_source": preview.pv_headroom_source,
            "load_risk_policy": preview.load_risk_policy,
            "pv_headroom_cost_premium_dkk": preview.pv_headroom_cost_premium_dkk,
            "post_horizon_load_kwh": preview.post_horizon_load_kwh,
            "max_charge_current_a": preview.max_charge_current_a,
            "charge_start_utc": (
                preview.charge_start.isoformat() if preview.charge_start else None
            ),
            "discharge_start_utc": (
                preview.discharge_start.isoformat() if preview.discharge_start else None
            ),
            "evaluated_scenarios": preview.evaluated_scenarios,
            "evaluated_transitions": preview.evaluated_transitions,
            "soc_resolution_dc_kwh": preview.soc_resolution_dc_kwh,
            "final_soc_pct": preview.final_soc_pct,
            "terminal_value_dkk_per_kwh_dc": preview.terminal_value_dkk_per_kwh_dc,
            "grid_charge_kwh": preview.grid_charge_kwh,
            "pv_charge_dc_kwh": preview.pv_charge_dc_kwh,
            "discharge_dc_kwh": preview.discharge_dc_kwh,
            "hourly_plan": local_hourly_plan(preview.hourly_plan),
            "hourly_plan_utc": list(preview.hourly_plan),
            "display_timezone": "Europe/Copenhagen",
            "charge_start_local": local_timestamp(preview.charge_start),
            "discharge_start_local": local_timestamp(preview.discharge_start),
            "start_local": local_timestamp(preview.start),
            "end_local": local_timestamp(preview.end),
            "execution_state": self.coordinator.dynamic_controller.status,
            "execution_reason": self.coordinator.dynamic_controller.reason,
            "last_plan_applied": self.coordinator.dynamic_controller.last_plan_start,
            "planner_scope": "all_contiguous_known_prices_pv_and_load",
            "grid_import_baseline": "no_battery_cycling_not_actual_deye",
            "tou_feasibility": "dynamic_control_bypasses_compilation",
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


class ActualSavingYesterdaySensor(CoordinatorEntity, SensorEntity):
    """Estimated previous Danish calendar day savings versus no battery."""

    _attr_has_entity_name = True
    _attr_name = "Actual Saving Yesterday"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_native_unit_of_measurement = "DKK"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_actual_saving_yesterday"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def native_value(self):
        result = self.coordinator.actual_yesterday
        return result.value if result is not None else None

    @property
    def extra_state_attributes(self):
        result = self.coordinator.actual_yesterday
        if result is None:
            return {"status": "pending"}
        return {
            "date": result.date,
            "status": "estimated" if result.value is not None else "unavailable",
            "reason": result.reason,
            "actual_cost_dkk": result.actual_cost,
            "no_battery_baseline_cost_dkk": result.baseline_cost,
            "coverage_fraction": result.coverage,
            "baseline": "same_observed_grid_without_battery_flow",
            "estimated_only": True,
            "battery_to_ac_efficiency_assumed": 0.95,
            "physical_meter_accuracy_verified": False,
            "comparison_is_not_attributable_solely_to_energy_copilot": True,
        }


class SevenDayLoadSensor(CoordinatorEntity, SensorEntity):
    """Seven-day forecast total; hourly series is usable by a future-time chart."""

    _attr_has_entity_name = True
    _attr_translation_key = "load_forecast_7d"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = "kWh"

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_load_forecast_7d"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def native_value(self):
        forecast = self.coordinator.load_forecast
        return round(forecast.total_kwh, 2) if forecast is not None else None

    @property
    def extra_state_attributes(self):
        forecast = self.coordinator.load_forecast
        if forecast is None:
            return {
                "status": "unavailable",
                "reason": self.coordinator.load_forecast_error,
                "read_only": True,
            }
        daily = {}
        from zoneinfo import ZoneInfo

        local = ZoneInfo("Europe/Copenhagen")
        for quarter in forecast.projection.periods:
            day = quarter.start.astimezone(local).date().isoformat()
            daily[day] = daily.get(day, 0.0) + quarter.kwh
        return {
            "status": "ready",
            "method": forecast.projection.method,
            "source": forecast.source,
            "generated_at": forecast.projection.captured_at.isoformat(),
            "start": forecast.projection.periods[0].start.isoformat(),
            "end": forecast.projection.periods[-1].end.isoformat(),
            "training_hours": forecast.training_hours,
            "training_days": forecast.training_days,
            "accuracy_verified": False,
            "read_only": True,
            "hourly": [
                {"start": item.start.isoformat(), "kwh": round(item.kwh, 4)}
                for item in forecast.hourly
            ],
            "daily": [
                {"date": day, "kwh": round(value, 3)}
                for day, value in sorted(daily.items())
            ],
        }


class DecisionJournalSensor(CoordinatorEntity, SensorEntity):
    """Last operational decision; complete history is in HA diagnostics."""

    _attr_has_entity_name = True
    _attr_name = "Decision journal"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:text-box-search-outline"

    def __init__(self, entry):
        super().__init__(entry.runtime_data.coordinator)
        self._attr_unique_id = f"{entry.entry_id}_decision_journal"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def native_value(self):
        # This is a diagnostic archive access point, not a status transition.
        # Publishing changing event names as the sensor's state creates misleading
        # Activity entries such as "planned → blocked", with no event rationale.
        # Actual decisions are published as native logbook entries.
        return "ready" if self.coordinator.decision_journal.available else "unavailable"

    @property
    def extra_state_attributes(self):
        journal = self.coordinator.decision_journal
        return {
            **journal.summary,
            "last_events": journal.recent(5),
            "full_history": "Settings > Devices & services > Energy Co-Pilot > Download diagnostics",
        }
