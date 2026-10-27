"""Privacy-conscious diagnostics: source quality, no raw household series."""

from collections import Counter
from copy import deepcopy

from homeassistant.util import dt as dt_util

from .const import OPTIONAL_ENTITY_ROLES
from .sensor import local_hourly_plan, local_timestamp
from .validation import DERIVED_SUM_TOLERANCE_W


def history_diagnostics(summary):
    """Export aggregate audit evidence only, even if a local audit added events."""
    if summary is None:
        return None
    result = deepcopy(summary)
    allowed = {
        "records",
        "context_counts",
        "timestamp_basis",
        "causal_conclusion",
        "physical_consumption_verified",
        "template_residual_tolerance_w",
    }
    for key in ("negative_home_audit", "negative_home_audit_last_chunk"):
        if isinstance(result.get(key), dict):
            result[key] = {k: v for k, v in result[key].items() if k in allowed}
    return result


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    unconfigured = [
        role for role in OPTIONAL_ENTITY_ROLES if not coordinator.entities[role]
    ]
    if not coordinator.settings.get("solar_sell", "switch.sun12k_solar_sell"):
        unconfigured.append("solar_sell")
    buy_state = hass.states.get(coordinator.entities["buy"])
    buy_attrs = buy_state.attributes if buy_state else {}
    price_raw_today = buy_attrs.get("raw_today")
    price_raw_tomorrow = buy_attrs.get("raw_tomorrow")
    price_raw_today_count = (
        len(price_raw_today) if isinstance(price_raw_today, list) else None
    )
    price_raw_tomorrow_count = (
        len(price_raw_tomorrow) if isinstance(price_raw_tomorrow, list) else None
    )
    price_first = data.prices[0].start.isoformat() if data.prices else None
    price_last = data.prices[-1].end.isoformat() if data.prices else None
    forecast_periods = data.forecast.periods if data.forecast else ()
    forecast_first = forecast_periods[0].start.isoformat() if forecast_periods else None
    forecast_last = forecast_periods[-1].end.isoformat() if forecast_periods else None
    preview = coordinator.planning_preview
    load_forecast = coordinator.load_forecast
    return {
        "load_forecast": {
            "status": "ready" if load_forecast else "unavailable",
            "reason": coordinator.load_forecast_error,
            "forecast_quarters": len(load_forecast.projection.periods)
            if load_forecast
            else 0,
            "training_hours": load_forecast.training_hours if load_forecast else 0,
            "training_days": load_forecast.training_days if load_forecast else 0,
            "method": load_forecast.projection.method if load_forecast else None,
            "historical_source_is_derived": bool(
                load_forecast and load_forecast.source.startswith("derived_")
            ),
            "physical_accuracy_verified": False,
            "holdout_accuracy": coordinator.load_backtest,
        },
        "planner_replay": preview.replay_snapshot,
        "display_timezone": "Europe/Copenhagen",
        "hourly_plan_local": local_hourly_plan(preview.hourly_plan),
        "planning_preview": {
            "status": preview.status,
            "reason": preview.reason,
            "coverage": preview.coverage,
            "first_uncovered_at_utc": (
                preview.first_uncovered_at.isoformat()
                if preview.first_uncovered_at
                else None
            ),
            "quarter_count": preview.quarters,
            "start_utc": preview.start.isoformat() if preview.start else None,
            "end_utc": preview.end.isoformat() if preview.end else None,
            "price_horizon_end_utc": (
                preview.published_price_horizon_end.isoformat()
                if preview.published_price_horizon_end
                else None
            ),
            "forecast_version": preview.pv_version,
            "load_method": preview.source_load_method,
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
            "pv_headroom_cost_premium_dkk": preview.pv_headroom_cost_premium_dkk,
            "post_horizon_load_kwh": preview.post_horizon_load_kwh,
            "maximum_charging_current_a": preview.max_charge_current_a,
            "scenarios_evaluated": preview.evaluated_scenarios,
            "evaluated_transitions": preview.evaluated_transitions,
            "soc_resolution_dc_kwh": preview.soc_resolution_dc_kwh,
            "final_soc_pct": preview.final_soc_pct,
            "terminal_value_dkk_per_kwh_dc": preview.terminal_value_dkk_per_kwh_dc,
            "grid_charge_kwh": preview.grid_charge_kwh,
            "pv_charge_dc_kwh": preview.pv_charge_dc_kwh,
            "discharge_dc_kwh": preview.discharge_dc_kwh,
            "dispatch_scope": "whole_published_horizon",
            "tou_feasibility": "not_evaluated",
            "voltage_source": preview.voltage_source,
            "executable": False,
            "scenario_selection": "whole_horizon_continuous_min_cost_flow",
            "real_deye_baseline": False,
            "efficiency_calibrated": False,
            "pv_forecast_dc_basis_verified": False,
            "tou_six_windows_verified": False,
        },
        "integration_manifest": {
            "domain": "energy_copilot",
            "version": entry.runtime_data.installed_build["installed_version"],
        },
        "installed_version": entry.runtime_data.installed_build["installed_version"],
        "installed_build": entry.runtime_data.installed_build,
        "mode": coordinator.settings.get("mode", "monitor"),
        "read_only": not coordinator.dynamic_controller.armed,
        "execution": {
            "armed": coordinator.dynamic_controller.armed,
            "status": coordinator.dynamic_controller.status,
            "reason": coordinator.dynamic_controller.reason,
            "last_plan_start": coordinator.dynamic_controller.last_plan_start,
            "last_plan_start_local": local_timestamp(
                coordinator.dynamic_controller.last_plan_start
            ),
            "halted": coordinator.dynamic_controller.halted,
            "active_tou_slot": coordinator.dynamic_controller.active_tou_slot,
            "target_tou_soc": coordinator.dynamic_controller.target_tou_soc,
            "target_tou_grid_charge": coordinator.dynamic_controller.target_tou_grid_charge,
            "observed_tou_soc": coordinator.dynamic_controller.observed_tou_soc,
            "observed_tou_grid_charge": coordinator.dynamic_controller.observed_tou_grid_charge,
        },
        "quality": coordinator.quality,
        "observed": {
            "at": data.at.isoformat(),
            "measurement_roles": sorted(data.measurements),
            "home_sample_normalized": "home" in data.measurements
            and data.measurements["home"].raw_value is not None,
            "measurement_source_timing": coordinator.measurement_source_timing,
            "live_measurement_window": coordinator.live_window.summary(
                dt_util.utcnow()
            ),
            "price_slots": len(data.prices),
            "price_first_start_utc": price_first,
            "price_last_end_utc": price_last,
            "price_buy_today_records": price_raw_today_count,
            "price_buy_tomorrow_records": price_raw_tomorrow_count,
            "price_buy_tomorrow_valid": buy_attrs.get("tomorrow_valid"),
            "forecast_version": data.forecast.version if data.forecast else None,
            "forecast_coverage": coordinator.forecast_coverage,
            "prospective_forecast_accuracy": coordinator.forecast_accuracy.summary,
            "forecast_first_start_utc": forecast_first,
            "forecast_raw_first_start_utc": data.forecast.source_start.isoformat()
            if data.forecast and data.forecast.source_start
            else None,
            "forecast_raw_last_end_utc": data.forecast.source_end.isoformat()
            if data.forecast and data.forecast.source_end
            else None,
            "forecast_last_end_utc": forecast_last,
            "forecast_captured_at": data.forecast.captured_at.isoformat()
            if data.forecast
            else None,
            "forecast_versions_retained": len(coordinator.versions),
            "forecast_history": {
                **coordinator.forecast_history.summary,
                "available": coordinator._archive_available,
            },
            "recent_history": history_diagnostics(
                coordinator.history_reader.last_read_summary
            ),
            "requested_history": history_diagnostics(
                coordinator.history_reader.last_backfill_summary
            ),
            "unconfigured_optional_roles": sorted(unconfigured),
            "history_slots": len(data.history),
            "history_issue_counts": dict(
                Counter(i.code for s in data.history for i in s.issues)
            ),
            "history_valid_slots": sum(s.home_kwh is not None for s in data.history),
        },
        "issues": [{"code": i.code, "source": i.source} for i in data.issues],
        "user_confirmed": {
            "minimum_soc_percent": 20,
            "degradation_dkk_per_kwh_dc": 0.4,
            "pv_export_threshold_dkk_per_kwh": 0.4,
            "home_negative_power_policy": "max_zero_when_sources_valid",
        },
        "assumed": {
            "live_as_of_skew_warning_seconds": 10,
            "live_future_timestamp_tolerance_seconds": 10,
            "derived_sum_tolerance_w": DERIVED_SUM_TOLERANCE_W,
            "preview_nominal_battery_kwh": 10.24,
            "preview_efficiency_each_path": 0.95,
            "preview_forecast_to_dc_multiplier": 1.0,
            "recent_history_lookback_hours": 24,
            "history_on_demand_max_days": 366,
            "history_chunk_hours": 24,
        },
        "unverified": [
            "physical_home_consumption_and_ac_dc_model",
            "physical_ac_dc_efficiencies",
            "unconstrained_pv_production",
            "live_installation_compatibility",
        ],
    }
