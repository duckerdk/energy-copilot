"""Privacy-conscious diagnostics: source quality, no raw household series."""

from collections import Counter

from .const import OPTIONAL_ENTITY_ROLES


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    unconfigured = [
        role for role in OPTIONAL_ENTITY_ROLES if not coordinator.entities[role]
    ]
    if not coordinator.settings.get("solar_sell", "switch.sun12k_solar_sell"):
        unconfigured.append("solar_sell")
    return {
        "mode": coordinator.settings.get("mode", "monitor"),
        "read_only": True,
        "observed": {
            "at": data.at.isoformat(),
            "measurement_roles": sorted(data.measurements),
            "price_slots": len(data.prices),
            "forecast_version": data.forecast.version if data.forecast else None,
            "forecast_captured_at": data.forecast.captured_at.isoformat()
            if data.forecast
            else None,
            "forecast_versions_retained": len(coordinator.versions),
            "forecast_history": {
                **coordinator.forecast_history.summary,
                "available": coordinator._archive_available,
            },
            "recent_history": coordinator.history_reader.last_read_summary,
            "requested_history": coordinator.history_reader.last_backfill_summary,
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
        },
        "assumed": {
            "freshness_seconds": 300,
            "maximum_skew_seconds": 10,
            "recent_history_lookback_hours": 24,
            "history_on_demand_max_days": 366,
            "history_chunk_hours": 24,
        },
        "unverified": [
            "physical_ac_dc_efficiencies",
            "unconstrained_pv_production",
            "live_installation_compatibility",
        ],
    }
