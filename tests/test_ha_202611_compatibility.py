"""Regressions for the Forecast.Solar 2026.11 timestamp contract and failed refresh."""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from homeassistant.helpers.storage import Store

from custom_components.energy_copilot import validation
from custom_components.energy_copilot.coordinator import EnergyCoordinator
from custom_components.energy_copilot.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.energy_copilot.forecast_history import ForecastHistory
from custom_components.energy_copilot.validation import forecast

from .conftest import NOW
from .test_validation import forecast_response


def start_indexed_response():
    keys = [(NOW + timedelta(hours=hour)).isoformat() for hour in range(3)]
    return {
        "watts": dict.fromkeys(keys, 500),
        "wh_period": {keys[0]: 600, keys[1]: 400, keys[2]: 0},
    }


def test_ha_202611_start_timestamp_contract():
    snapshot = forecast(start_indexed_response(), NOW, period_index="start")
    assert [(period.start, period.end, period.kwh) for period in snapshot.periods] == [
        (NOW, NOW + timedelta(hours=1), 0.6),
        (NOW + timedelta(hours=1), NOW + timedelta(hours=2), 0.4),
    ]
    assert snapshot.unbounded_prior_energy_at == ()
    assert snapshot.unbounded_energy_at == ()
    assert snapshot.missing_energy_at == ()


def test_ha_202611_no_fabricated_energy_when_first_timestamp_missing():
    response = start_indexed_response()
    del response["wh_period"][NOW.isoformat()]
    snapshot = forecast(response, NOW, period_index="start")
    assert snapshot.missing_energy_at == (NOW,)
    assert len(snapshot.periods) == 1
    assert snapshot.periods[0].start == NOW + timedelta(hours=1)


def test_ha_202611_rejects_unbounded_final_energy():
    response = start_indexed_response()
    last = (NOW + timedelta(hours=2)).isoformat()
    response["wh_period"][last] = 7
    snapshot = forecast(response, NOW, period_index="start")
    assert snapshot.unbounded_energy_at == (NOW + timedelta(hours=2),)


def test_period_index_selection_follows_home_assistant_minor(monkeypatch):
    response = forecast_response()
    monkeypatch.setattr(validation, "MAJOR_VERSION", 2026)
    monkeypatch.setattr(validation, "MINOR_VERSION", 10)
    assert forecast(response, NOW).periods[0].kwh == 1
    monkeypatch.setattr(validation, "MINOR_VERSION", 11)
    assert forecast(response, NOW).periods[0].kwh == 0.194


async def test_archive_upgrade_preserves_old_wh_and_labels_new_records(
    hass, monkeypatch
):
    archive = ForecastHistory(hass, "ha_202611")
    await archive.async_record(forecast_response(), NOW, "solar")
    store = Store(hass, 1, "energy_copilot.ha_202611.forecasts")
    old = await store.async_load()
    old["format"] = 2
    for row in old["versions"]:
        row.pop("period_index")
    await store.async_save(old)

    monkeypatch.setattr(
        "custom_components.energy_copilot.forecast_history.HA_PERIOD_INDEX",
        "start",
    )
    upgraded = ForecastHistory(hass, "ha_202611")
    await upgraded.async_load(NOW + timedelta(minutes=1))
    assert upgraded.as_of(NOW).periods[0].kwh == 1
    assert upgraded.versions[0]["period_index"] == "end"
    assert (await store.async_load())["format"] == 3

    captured = NOW + timedelta(minutes=2)
    current = await upgraded.async_record(start_indexed_response(), captured, "solar")
    assert current.periods[0].kwh == 0.6
    assert upgraded.as_of(NOW).periods[0].kwh == 1
    assert upgraded.as_of(captured).periods[0].kwh == 0.6
    assert [row["period_index"] for row in upgraded.versions] == ["end", "start"]


async def test_unexpected_refresh_failure_keeps_reason_for_diagnostics(
    populated_hass, entry, monkeypatch
):
    coordinator = EnergyCoordinator(populated_hass, entry)
    coordinator.decision_journal.record = Mock()

    async def failing_refresh():
        raise RuntimeError("simulated coordinator error")

    monkeypatch.setattr(coordinator, "_async_update_data_impl", failing_refresh)
    with pytest.raises(RuntimeError, match="simulated coordinator error"):
        await coordinator._async_update_data()

    assert coordinator.last_refresh_error["type"] == "RuntimeError"
    coordinator.decision_journal.record.assert_called_once()
    kwargs = coordinator.decision_journal.record.call_args.kwargs
    assert kwargs["reason"] == "coordinator:unhandled_exception"

    entry.runtime_data = SimpleNamespace(
        coordinator=coordinator,
        installed_build={"installed_version": "2.0.4"},
    )
    diagnostic = await async_get_config_entry_diagnostics(populated_hass, entry)
    assert diagnostic["status"] == "coordinator_not_ready"
    assert diagnostic["last_refresh_error"]["type"] == "RuntimeError"
    assert "decision_journal" in diagnostic
