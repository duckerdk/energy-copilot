from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.energy_copilot.const import DOMAIN
from custom_components.energy_copilot.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import NOW
from .test_validation import forecast_response


async def test_config_flow(hass, populated_hass, settings):
    with patch("custom_components.energy_copilot.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], settings
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        assert result["data"] == settings
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["reason"] == "already_configured"


async def test_config_flow_bad_mapping(hass, populated_hass, settings):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    bad = {**settings, "pv": "sensor.missing", "forecast_entry": "missing"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], bad)
    assert result["errors"] == {
        "pv": "entity_missing",
        "forecast_entry": "forecast_entry_missing",
    }
    bad = {**settings, "pv": settings["grid"]}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], bad)
    assert result["errors"]["base"] == "duplicate_entity"


@pytest.mark.parametrize("mode", ["monitor", "dry_run"])
async def test_setup_poll_unload_and_remove(hass, populated_hass, entry, freezer, mode):
    freezer.move_to(NOW)
    hass.config_entries.async_update_entry(entry, options={"mode": mode})
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        autospec=True,
        side_effect=type(hass.services).async_call,
    ) as service_calls:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        coordinator = entry.runtime_data.coordinator
        assert coordinator.data.flows_kw["pv_dc"] == 3.034
        assert len(coordinator.data.prices) == 1
        state = hass.states.get("sensor.energy_co_pilot_input_quality")
        assert state is not None and state.state == "degraded"
        assert state.attributes["read_only"] is True
        assert {i.code for i in coordinator.data.issues} >= {
            "recorder_unavailable",
            "forecast_entry_missing",
        }
        diag = await async_get_config_entry_diagnostics(hass, entry)
        assert diag["read_only"] is True
        assert "sensor.sun12k" not in str(diag)
        assert "raw_today" not in str(diag)
        freezer.tick(timedelta(seconds=31))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert coordinator.data.at > NOW
        assert not service_calls.called  # No HA service, including inverter commands.
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.NOT_LOADED
        assert (
            hass.states.get("sensor.energy_co_pilot_input_quality").state
            == "unavailable"
        )
        old = coordinator.data.at
        freezer.tick(timedelta(minutes=1))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert coordinator.data.at == old
        assert await hass.config_entries.async_remove(entry.entry_id)


async def test_options_reload(hass, populated_hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    before = entry.runtime_data.coordinator
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    settings = {**entry.data, "mode": "dry_run"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], settings
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator is not before
    assert entry.runtime_data.coordinator.settings["mode"] == "dry_run"


async def test_forecast_service_is_only_allowed_call(
    hass, populated_hass, entry, freezer
):
    freezer.move_to(NOW)
    solar = MockConfigEntry(domain="forecast_solar")
    solar.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={"forecast_entry": solar.entry_id}
    )
    response = forecast_response()
    callback = AsyncMock(return_value=response)
    hass.services.async_register(
        "forecast_solar",
        "get_forecast",
        callback,
        supports_response=SupportsResponse.ONLY,
    )
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        autospec=True,
        side_effect=type(hass.services).async_call,
    ) as calls:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.runtime_data.coordinator.data.forecast.periods[0].kwh == 1
        assert len(entry.runtime_data.coordinator.versions) == 1
        assert calls.call_count == 1
        assert calls.call_args.args[1:3] == ("forecast_solar", "get_forecast")
        assert calls.call_args.kwargs["return_response"] is True
        assert calls.call_args.args[3]["config_entry"] == solar.entry_id
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert len(entry.runtime_data.coordinator.versions) == 2
        assert {c.args[1:3] for c in calls.call_args_list} == {
            ("forecast_solar", "get_forecast")
        }


async def test_absent_forecast_service_is_quality_issue(hass, populated_hass, entry):
    solar = MockConfigEntry(domain="forecast_solar")
    solar.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={"forecast_entry": solar.entry_id}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.coordinator.data.forecast is None
    assert "forecast_unavailable_or_invalid" in {
        i.code for i in entry.runtime_data.coordinator.data.issues
    }


async def test_possible_curtailment(hass, populated_hass, entry):
    hass.states.async_set(entry.data["soc"], "100", {"unit_of_measurement": "%"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert "possible_curtailment" in {
        i.code for i in entry.runtime_data.coordinator.data.issues
    }


async def test_native_forecast_solar_service_contract(hass, populated_hass, entry):
    """Run HA's actual get_forecast implementation against an in-memory estimate."""
    from types import SimpleNamespace

    from homeassistant.components.forecast_solar.services import async_setup_services
    from homeassistant.helpers.storage import Store

    from custom_components.energy_copilot.validation import utc

    response = forecast_response()
    solar = MockConfigEntry(domain="forecast_solar")
    solar.add_to_hass(hass)
    # No provider setup or HTTP: only the native response service is under test.
    solar.runtime_data = SimpleNamespace(
        data=SimpleNamespace(
            watts={utc(k): v for k, v in response["watts"].items()},
            wh_period={utc(k): v for k, v in response["wh_period"].items()},
            timezone="Europe/Copenhagen",
        )
    )
    solar.mock_state(hass, ConfigEntryState.LOADED)
    async_setup_services(hass)
    hass.config_entries.async_update_entry(
        entry, options={"forecast_entry": solar.entry_id}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    snapshot = entry.runtime_data.coordinator.data.forecast
    assert snapshot is not None
    assert snapshot.periods[0].start == NOW
    assert snapshot.periods[0].kwh == 1
    store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.forecasts")
    assert (await store.async_load())["versions"][0]["version"] == snapshot.version
    assert await hass.config_entries.async_remove(entry.entry_id)
    assert (
        await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.forecasts").async_load()
        is None
    )
    # Avoid attempting to unload an upstream integration we did not start.
    solar.mock_state(hass, ConfigEntryState.NOT_LOADED)


async def test_forecast_capture_uses_response_time(
    hass, populated_hass, entry, freezer
):
    solar = MockConfigEntry(domain="forecast_solar")
    solar.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={"forecast_entry": solar.entry_id}
    )

    async def delayed_forecast(call):
        freezer.tick(timedelta(seconds=2))
        return forecast_response()

    hass.services.async_register(
        "forecast_solar",
        "get_forecast",
        delayed_forecast,
        supports_response=SupportsResponse.ONLY,
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    data = entry.runtime_data.coordinator.data
    assert data.forecast.captured_at == NOW + timedelta(seconds=2)
    assert data.forecast.periods[0].start == NOW + timedelta(hours=1)
    assert "forecast_horizon_incomplete" in {i.code for i in data.issues}
