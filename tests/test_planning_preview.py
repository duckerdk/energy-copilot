"""M3 Home Assistant dry-run preview acceptance and read-only behavior."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from custom_components.energy_copilot.models import (
    ForecastPeriod,
    ForecastSnapshot,
    HistorySlot,
    InputSnapshot,
    Issue,
    PriceSlot,
    Sample,
)
from custom_components.energy_copilot.planning_preview import evaluate_preview

BASE = datetime(2026, 10, 21, 10, tzinfo=UTC)
STEP = timedelta(minutes=15)
DAY = timedelta(days=1)


def snapshot(*, hours=2, pv=0.0, soc=50.0, voltage=51.2):
    periods = tuple(
        ForecastPeriod(
            BASE + i * STEP,
            BASE + (i + 1) * STEP,
            pv,
        )
        for i in range(hours * 4)
    )
    history = tuple(
        HistorySlot(
            p.start - DAY,
            p.end - DAY,
            0.50,
            observed_seconds=900,
        )
        for p in periods
    )
    prices = tuple(
        PriceSlot(
            BASE + i * timedelta(hours=1),
            BASE + (i + 1) * timedelta(hours=1),
            0.10 if i == 0 else 1.40,
            0.0,
        )
        for i in range(hours)
    )
    return InputSnapshot(
        at=BASE,
        measurements={
            "soc": Sample(soc, BASE),
            "voltage": Sample(voltage, BASE),
        },
        prices=prices,
        forecast=ForecastSnapshot(BASE, "test-known-forecast", periods),
        history=history,
    )


def test_cost_preview_uses_actual_hourly_prices_and_returns_soc_to_initial():
    preview = evaluate_preview(snapshot(), mode="dry_run")
    assert preview.status == "preview"
    assert preview.reason is None
    assert preview.coverage == "complete"
    assert preview.quarters == 8
    assert preview.pv_version == "test-known-forecast"
    assert preview.evaluated_scenarios > 1
    assert preview.scenario_cost_dkk < preview.reference_cost_dkk
    assert preview.modeled_saving_dkk > 0
    assert 0 < preview.max_charge_current_a <= 50
    assert BASE <= preview.charge_start < preview.discharge_start
    assert preview.executable is False


def test_dry_run_zero_battery_headroom_stays_computable_with_no_charge():
    result = evaluate_preview(snapshot(soc=100), mode="dry_run")
    assert result.status == "preview"
    assert result.evaluated_scenarios == 1
    assert result.charge_start is None
    assert result.modeled_saving_dkk == 0


def test_monitor_does_not_evaluate_or_expose_fake_savings():
    result = evaluate_preview(snapshot(), mode="monitor")
    assert result.status == "monitor"
    assert result.reason == "dry_run_not_enabled"
    assert result.modeled_saving_dkk is None


def test_missing_pv_and_soc_block_preview_without_fabrication():
    s = snapshot()
    s.forecast = None
    result = evaluate_preview(s, mode="dry_run")
    assert result.status == "blocked"
    assert result.reason == "pv:forecast_missing"
    assert result.modeled_saving_dkk is None
    s = snapshot()
    del s.measurements["soc"]
    result = evaluate_preview(s, mode="dry_run")
    assert result.reason == "soc:invalid_or_missing"


def test_partial_pv_forecast_is_usable_only_as_labeled_prefix():
    s = snapshot()
    s.forecast = replace(s.forecast, periods=s.forecast.periods[:5])
    result = evaluate_preview(s, mode="dry_run")
    assert result.status == "preview"
    assert result.coverage == "partial"
    assert result.quarters == 5
    assert result.reason == "pv:coverage_or_resolution_gap"
    assert result.first_uncovered_at == BASE + 5 * STEP
    assert result.end < result.published_price_horizon_end


def test_no_forecast_for_first_future_quarter_is_a_real_blocker():
    s = snapshot()
    s.forecast = replace(s.forecast, periods=s.forecast.periods[1:])
    result = evaluate_preview(s, mode="dry_run")
    assert result.status == "blocked"
    assert result.reason == "pv:coverage_or_resolution_gap"


def test_dry_run_explicitly_models_coarse_forecast_for_preview_only():
    s = snapshot()
    s.forecast = replace(
        s.forecast,
        periods=(ForecastPeriod(BASE, BASE + timedelta(hours=2), 2.0),),
    )
    result = evaluate_preview(s, mode="dry_run")
    assert result.status == "preview"
    assert result.pv_temporal_model == "uniform_power_unverified"
    assert result.pv_temporal_modeled_quarters == 8
    assert result.quarters == 8
    assert result.executable is False


def test_realistic_started_irregular_forecast_has_partial_preview_not_pv_block():
    s = snapshot()
    s.at = BASE + timedelta(minutes=33)
    s.forecast = replace(
        s.forecast,
        periods=(
            ForecastPeriod(BASE, BASE + timedelta(minutes=59), 0.6),
            ForecastPeriod(
                BASE + timedelta(minutes=59), BASE + timedelta(hours=2), 0.1
            ),
        ),
    )
    # Day-before Recorder gap still stops the prefix; it is never backfilled.
    s.history = tuple(
        h for h in s.history if h.start < BASE + timedelta(minutes=90) - DAY
    )
    result = evaluate_preview(s, mode="dry_run")
    assert result.status == "preview"
    assert result.coverage == "partial"
    assert result.quarters == 3
    assert result.reason == "load:coverage_or_resolution_gap"
    assert result.first_uncovered_at == BASE + timedelta(minutes=90)
    assert result.pv_temporal_model == "uniform_power_unverified"
    assert result.executable is False


def test_missing_recent_history_cannot_be_replaced_with_arbitrary_load():
    s = snapshot()
    s.history = ()
    result = evaluate_preview(s, mode="dry_run")
    assert result.status == "blocked"
    assert result.reason == "load:coverage_or_resolution_gap"


def test_absent_optional_battery_voltage_is_labeled_nominal_not_measured():
    s = snapshot()
    del s.measurements["voltage"]
    result = evaluate_preview(s, mode="dry_run")
    assert result.status == "preview"
    assert result.voltage_source == "nominal_unverified"


def test_real_price_ambiguity_blocks_export_preview_activation():
    s = snapshot(pv=0.1)
    s.issues.append(Issue("PRICE_THRESHOLD_AMBIGUOUS", "sell"))
    result = evaluate_preview(s, mode="dry_run", pv_export_enabled=True)
    assert result.status == "blocked"
    assert result.reason == "pv_export:price_ambiguous"



async def test_ha_diagnostics_labels_unverified_pv_resolution_and_no_commands(
    hass, populated_hass, entry, freezer
):
    from custom_components.energy_copilot.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    from .conftest import NOW

    freezer.move_to(NOW)
    hass.config_entries.async_update_entry(entry, options={"mode": "dry_run"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    coordinator._forecast = ForecastSnapshot(
        NOW - timedelta(minutes=1),
        "forecast-coarse",
        (ForecastPeriod(NOW, NOW + timedelta(hours=2), 0.2),),
    )
    coordinator._history = tuple(
        HistorySlot(
            NOW + i * STEP - DAY,
            NOW + (i + 1) * STEP - DAY,
            0.5,
            observed_seconds=900,
        )
        for i in range(8)
    )
    coordinator._last_external = NOW
    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        side_effect=AssertionError("no HA service permitted during preview"),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_co_pilot_planning_status")
    assert state.state == "preview"
    assert state.attributes["pv_temporal_model"] == "uniform_power_unverified"
    assert state.attributes["pv_temporal_modeled_quarters"] > 0
    assert state.attributes["executable"] is False
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert (
        diag["planning_preview"]["pv_temporal_model"]
        == "uniform_power_unverified"
    )
    assert diag["planning_preview"]["pv_temporal_modeled_quarters"] > 0
    assert diag["read_only"] is True


async def test_ha_sensors_exist_and_default_mode_does_not_issue_commands(
    hass, populated_hass, entry
):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_co_pilot_planning_status")
    assert state is not None
    assert state.state == "monitor"
    assert state.attributes["executable"] is False
    assert state.attributes["physical_calibration_verified"] is False
    assert state.attributes["tou_six_window_feasibility_verified"] is False
    modeled = hass.states.get("sensor.energy_co_pilot_modeled_saving")
    assert modeled is not None and modeled.state == "unknown"
    assert modeled.attributes["not_actual_savings"] is True
    assert entry.runtime_data.coordinator.planning_preview.executable is False


async def test_ha_dry_run_without_forecast_shows_specific_blocker_in_diagnostics(
    hass, populated_hass, entry
):
    from custom_components.energy_copilot.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    hass.config_entries.async_update_entry(entry, options={"mode": "dry_run"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_co_pilot_planning_status")
    assert state is not None and state.state == "blocked"
    assert state.attributes["reason"] == "pv:forecast_missing"
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["planning_preview"]["reason"] == "pv:forecast_missing"
    assert diag["planning_preview"]["executable"] is False
    assert diag["read_only"] is True


async def test_ha_dry_run_with_real_coordinator_snapshot_renders_model_result(
    hass, populated_hass, entry, freezer
):
    from .conftest import NOW

    freezer.move_to(NOW)
    for role, prices in (
        ("buy", [0.1, 1.4]),
        ("sell", [0.0, 0.0]),
    ):
        entity_id = entry.data[role]
        hass.states.async_set(
            entity_id,
            "0.1",
            {
                "unit_of_measurement": "DKK/kWh",
                "raw_today": [
                    {
                        "hour": (NOW + timedelta(hours=i)).isoformat(),
                        "price": value,
                    }
                    for i, value in enumerate(prices)
                ],
                "raw_tomorrow": [],
                "tomorrow_valid": False,
                "current_price": prices[0],
            },
        )
    hass.config_entries.async_update_entry(entry, options={"mode": "dry_run"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    forecast = tuple(
        ForecastPeriod(NOW + i * STEP, NOW + (i + 1) * STEP, 0) for i in range(8)
    )
    coordinator._forecast = ForecastSnapshot(
        NOW - timedelta(minutes=1),
        "test-service-forecast",
        forecast,
    )
    coordinator._history = tuple(
        HistorySlot(q.start - DAY, q.end - DAY, 0.5, observed_seconds=900)
        for q in forecast
    )
    coordinator._last_external = NOW

    with patch(
        "homeassistant.core.ServiceRegistry.async_call",
        side_effect=AssertionError("no HA service permitted during preview"),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    state = hass.states.get("sensor.energy_co_pilot_planning_status")
    assert state.state == "preview"
    assert state.attributes["coverage"] == "complete"
    assert state.attributes["modeled_saving_dkk"] > 0
    assert state.attributes["executable"] is False
    modeled = hass.states.get("sensor.energy_co_pilot_modeled_saving")
    assert float(modeled.state) > 0


async def test_preview_exception_does_not_turn_m2_input_quality_unavailable(
    hass, populated_hass, entry
):
    hass.config_entries.async_update_entry(entry, options={"mode": "dry_run"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    with patch(
        "custom_components.energy_copilot.coordinator.evaluate_preview",
        side_effect=RuntimeError("broken experimental optimizer"),
    ):
        await coordinator.async_refresh()
        await hass.async_block_till_done()
    assert coordinator.planning_preview.status == "blocked"
    assert coordinator.planning_preview.reason == "planner:internal_error"
    assert hass.states.get("sensor.energy_co_pilot_input_quality").state == "valid"
    assert hass.states.get("sensor.energy_co_pilot_planning_status").state == "blocked"
