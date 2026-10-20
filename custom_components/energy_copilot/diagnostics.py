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
    buy_state = hass.states.get(coordinator.entities["buy"])
    buy_attrs = buy_state.attributes if buy_state else {}
    price_raw_today = buy_attrs.get("raw_today")
    price_raw_tomorrow = buy_attrs.get("raw_tomorrow")
    price_raw_today_count = len(price_raw_today) if isinstance(price_raw_today, list) else None
    price_raw_tomorrow_count = len(price_raw_tomorrow) if isinstance(price_raw_tomorrow, list) else None
    price_first = data.prices[0].start.isoformat() if data.prices else None
    price_last = data.prices[-1].end.isoformat() if data.prices else None
    forecast_periods = data.forecast.periods if data.forecast else ()
    forecast_first = forecast_periods[0].start.isoformat() if forecast_periods else None
    forecast_last = forecast_periods[-1].end.isoformat() if forecast_periods else None
    return {
        "mode": coordinator.settings.get("mode", "monitor"),
        "read_only": True,
        "observed": {
            "at": data.at.isoformat(),
            "measurement_roles": sorted(data.measurements),
            "price_slots": len(data.prices),
            "price_first_start_utc": price_first,
            "price_last_end_utc": price_last,
            "price_buy_raw_today_count": price_raw_today_count,
            "price_buy_raw_tomorrow_count": price_raw_tomorrow_count,
            "price_buy_tomorrow_valid": buy_attrs.get("tomorrow_valid"),
            "forecast_version": data.forecast.version if data.forecast else None,
            "forecast_first_start_utc": forecast_first,
            "forecast_last_end_utc": forecast_last,
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
