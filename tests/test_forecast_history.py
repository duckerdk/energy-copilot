"""Original forecast retention, deduplication and decision-time replay."""

from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import json as json_helper
from homeassistant.helpers.storage import Store

from custom_components.energy_copilot.forecast_history import ForecastHistory

from .conftest import NOW
from .test_validation import forecast_response


async def test_original_response_and_replay_exclude_later_revision(hass):
    archive = ForecastHistory(hass, "entry")
    await archive.async_load(NOW)
    response = forecast_response()
    first = await archive.async_record(response, NOW, "solar")
    assert archive.as_of(NOW - timedelta(microseconds=1)) is None
    revised = deepcopy(response)
    revised["wh_period"][next(iter(revised["wh_period"]))] = 1234
    changed_at = NOW + timedelta(minutes=5)
    await archive.async_record(revised, changed_at, "solar")
    assert archive.original_at(NOW + timedelta(minutes=1)) == response
    assert archive.original_at(changed_at) == revised
    assert archive.as_of(NOW).version == first.version
    assert archive.as_of(NOW).periods[0].kwh == 1
    assert archive.as_of(changed_at).periods[0].start == NOW
    original = archive.original_at(NOW)
    original["watts"].clear()
    assert archive.original_at(NOW) == response  # Callers cannot alter observations.
    assert archive.original_at(NOW, source_entry="other") is None


async def test_identical_polls_and_reload_do_not_rewrite(hass):
    archive = ForecastHistory(hass, "entry")
    response = forecast_response()
    # Count writes without replacing storage behavior.
    original_save = Store.async_save
    with patch(
        "homeassistant.helpers.storage.Store.async_save",
        autospec=True,
        side_effect=original_save,
    ) as save:
        await archive.async_load(NOW)
        first = await archive.async_record(response, NOW, "solar")
        await archive.async_record(
            deepcopy(response), NOW + timedelta(minutes=1), "solar"
        )
        assert save.await_count == 1
        assert len(archive.versions) == 1
        assert archive.versions[0]["captured_at"] == NOW.isoformat()
        restored = ForecastHistory(hass, "entry")
        await restored.async_load(NOW + timedelta(minutes=2))
        await restored.async_record(response, NOW + timedelta(minutes=2), "solar")
        await restored.async_prune(NOW + timedelta(minutes=3))
        assert save.await_count == 1
        assert restored.as_of(NOW).version == first.version


async def test_reversion_records_availability_without_duplicate_payload(hass):
    archive = ForecastHistory(hass, "entry")
    a = forecast_response()
    b = deepcopy(a)
    b["watts"][next(iter(b["watts"]))] = 499
    for offset, response in enumerate((a, b, a)):
        await archive.async_record(response, NOW + timedelta(minutes=offset), "solar")
    assert len(archive.versions) == 3
    assert len(archive.payloads) == 2
    assert archive.original_at(NOW) == a
    assert archive.original_at(NOW + timedelta(minutes=1)) == b
    assert archive.original_at(NOW + timedelta(minutes=2)) == a
    assert archive.as_of(NOW + timedelta(minutes=2)).captured_at == NOW + timedelta(
        minutes=2
    )


async def test_version_cap_age_pruning_and_settings_reload(hass):
    archive = ForecastHistory(hass, "entry", retention_days=1, max_versions=2)
    for minute in range(3):
        response = forecast_response()
        response["watts"][next(iter(response["watts"]))] += minute
        await archive.async_record(response, NOW + timedelta(minutes=minute), "solar")
    assert len(archive.versions) == len(archive.payloads) == 2
    assert archive.as_of(NOW) is None
    restored = ForecastHistory(hass, "entry", retention_days=1, max_versions=1)
    await restored.async_load(NOW + timedelta(minutes=3))
    assert len(restored.versions) == len(restored.payloads) == 1
    await restored.async_prune(NOW + timedelta(days=2))
    assert restored.versions == [] and restored.payloads == {}
    assert (await restored.store.async_load())["versions"] == []


async def test_byte_cap_bounds_file_and_collects_orphan_payloads(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.energy_copilot.forecast_history.MAX_STORAGE_BYTES", 1600
    )
    archive = ForecastHistory(hass, "entry")
    for minute in range(10):
        response = forecast_response()
        response["watts"][next(iter(response["watts"]))] += minute
        await archive.async_record(response, NOW + timedelta(minutes=minute), "solar")
    stored = await archive.store.async_load()
    _, serialized = json_helper.prepare_save_json(
        {
            "version": 1,
            "minor_version": 1,
            "key": archive.store.key,
            "data": stored,
        }
    )
    assert len(serialized) <= 1600
    assert 0 < len(archive.versions) < 10
    assert set(archive.payloads) == {v["version"] for v in archive.versions}


async def test_legacy_migration_keeps_known_periods_without_fabricated_originals(hass):
    store = Store(hass, 1, "energy_copilot.entry.forecasts")
    await store.async_save(
        {
            "versions": [
                {
                    "captured_at": NOW.isoformat(),
                    "version": "old",
                    "periods": [
                        {
                            "start": NOW.isoformat(),
                            "end": (NOW + timedelta(hours=1)).isoformat(),
                            "kwh": 1,
                        }
                    ],
                }
            ]
        }
    )
    archive = ForecastHistory(hass, "entry")
    await archive.async_load(NOW)
    assert (
        archive.as_of(NOW) is None
    )  # Legacy normalized Wh used the wrong interval index.
    assert archive.original_at(NOW) is None
    assert archive.summary["legacy_versions_without_originals"] == 1
    assert (await store.async_load())["format"] == 2
    restored = ForecastHistory(hass, "entry")
    await restored.async_load(NOW)
    assert restored.as_of(NOW) is None
    assert restored.summary["legacy_versions_without_originals"] == 1


@pytest.mark.parametrize(
    "corruption", ["date", "future", "digest", "source", "legacy_nan", "legacy_reverse"]
)
async def test_corrupt_storage_is_preserved_and_not_replayed(hass, corruption):
    archive = ForecastHistory(hass, "entry")
    await archive.async_record(forecast_response(), NOW, "solar")
    data = deepcopy(await archive.store.async_load())
    if corruption == "date":
        payload = next(iter(data["payloads"].values()))
        payload["watts"]["invalid-date"] = 1
    elif corruption == "future":
        data["versions"][0]["captured_at"] = (NOW + timedelta(days=1)).isoformat()
    elif corruption == "digest":
        next(iter(data["payloads"].values()))["watts"][NOW.isoformat()] = 1
    elif corruption == "source":
        data["versions"][0]["source_entry"] = 123
    else:
        data = {
            "versions": [
                {
                    "captured_at": NOW.isoformat(),
                    "version": "old",
                    "periods": [
                        {
                            "start": NOW.isoformat(),
                            "end": (NOW + timedelta(hours=1)).isoformat(),
                            "kwh": "NaN" if corruption == "legacy_nan" else 1,
                        }
                    ],
                }
            ]
        }
        if corruption == "legacy_reverse":
            data["versions"][0]["periods"][0]["end"] = (
                NOW - timedelta(hours=1)
            ).isoformat()
    await archive.store.async_save(data)
    restored = ForecastHistory(hass, "entry")
    with pytest.raises(HomeAssistantError, match="invalid_forecast_storage"):
        await restored.async_load(NOW)
    assert restored.versions == []
    assert await archive.store.async_load() == data


async def test_storage_failure_retries_without_duplicating_observation(hass):
    archive = ForecastHistory(hass, "entry")
    with patch(
        "homeassistant.helpers.storage.Store.async_save",
        side_effect=HomeAssistantError("disk"),
    ):
        with pytest.raises(HomeAssistantError):
            await archive.async_record(forecast_response(), NOW, "solar")
    assert len(archive.versions) == 1
    await archive.async_record(forecast_response(), NOW + timedelta(minutes=1), "solar")
    assert len((await archive.store.async_load())["versions"]) == 1


async def test_oversized_series_rejected_before_storage(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.energy_copilot.forecast_history.MAX_SERIES_POINTS", 2
    )
    archive = ForecastHistory(hass, "entry")
    with pytest.raises(ValueError, match="too_large"):
        await archive.async_record(forecast_response(), NOW, "solar")
    assert archive.versions == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"retention_days": 0},
        {"retention_days": 367},
        {"max_versions": 0},
        {"max_versions": 50001},
        {"max_versions": True},
    ],
)
def test_retention_settings_are_also_enforced_at_runtime(hass, kwargs):
    with pytest.raises(ValueError, match="invalid_forecast_retention"):
        ForecastHistory(hass, "entry", **kwargs)


async def test_original_format2_replays_corrected_end_energy_without_future_revision(
    hass,
):
    start = NOW + timedelta(hours=8)
    end = start + timedelta(minutes=6, seconds=30)
    response = {
        "watts": {start.isoformat(): 162, end.isoformat(): 0},
        "wh_period": {start.isoformat(): 400, end.isoformat(): 9},
    }
    first_capture = start + timedelta(minutes=1)
    archive = ForecastHistory(hass, "entry")
    first = await archive.async_record(response, first_capture, "solar")
    assert first.periods[0].kwh == 0.009
    assert first.periods[0].start == start and first.periods[0].end == end
    assert first.unbounded_energy_at == ()
    assert first.unbounded_prior_energy_at == (start,)
    restored = ForecastHistory(hass, "entry")
    await restored.async_load(start + timedelta(minutes=2))
    assert restored.original_at(first_capture) == response
    assert restored.as_of(first_capture).periods[0].kwh == 0.009
    assert restored.as_of(first_capture - timedelta(microseconds=1)) is None
    revised = deepcopy(response)
    revised["wh_period"][end.isoformat()] = 18
    changed_at = start + timedelta(minutes=3)
    await restored.async_record(revised, changed_at, "solar")
    assert (
        restored.as_of(changed_at - timedelta(microseconds=1)).periods[0].kwh == 0.009
    )
    assert restored.as_of(changed_at).periods[0].kwh == 0.018
    assert restored.original_at(first_capture) == response
