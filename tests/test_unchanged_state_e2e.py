"""Regression: unchanged HA states must not age into degraded input quality."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from .conftest import NOW


async def test_real_ha_states_can_remain_unchanged_for_eight_hours(
    hass, populated_hass, entry, freezer
):
    zone = ZoneInfo("Europe/Copenhagen")
    midnight = NOW.astimezone(zone).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    prices = [
        {"hour": (midnight + timedelta(hours=hour)).isoformat(), "price": 0.4}
        for hour in range(48)
    ]
    for role in ("buy", "sell"):
        entity_id = entry.data[role]
        state = hass.states.get(entity_id)
        attrs = {
            **state.attributes,
            "raw_today": prices[:24],
            "raw_tomorrow": prices[24:],
            "tomorrow_valid": True,
            "current_price": 0.4,
        }
        hass.states.async_set(entity_id, state.state, attrs)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    first_soc_report = hass.states.get(entry.data["soc"]).last_reported
    first_pv_report = hass.states.get(entry.data["pv"]).last_reported

    freezer.tick(timedelta(hours=8))
    await coordinator.async_refresh()
    assert coordinator.quality["input_state"] == "valid"
    assert hass.states.get(entry.data["soc"]).last_reported == first_soc_report
    assert hass.states.get(entry.data["pv"]).last_reported == first_pv_report
    assert set(coordinator.data.measurements) == {
        "pv",
        "grid",
        "battery",
        "home",
        "soc",
        "voltage",
        "current",
        "grid_alternative",
        "daily_pv",
        "daily_charge",
        "daily_discharge",
    }
    assert not any(issue.code == "stale_input" for issue in coordinator.data.issues)
    assert (
        hass.states.get("sensor.energy_co_pilot_input_quality").state == "valid"
    )
