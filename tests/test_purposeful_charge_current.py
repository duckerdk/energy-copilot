"""Charge current is left alone unless an economic scheduling objective needs it."""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.energy_copilot.deye_commands import (
    CHARGE_CURRENT,
    GRID_CHARGE,
    GRID_CURRENT,
)
from tests.test_dynamic_controller import preview, setup_controller


@pytest.mark.asyncio
async def test_soc99_keeps_existing_one_and_seven_amp_limits():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    ctrl, service = setup_controller()
    service.states.items[CHARGE_CURRENT].state = "1"
    service.states.items[GRID_CURRENT].state = "7"
    ctrl.arm()
    plan = preview(now, charge=0, discharge=0, grid_a=0)
    plan.replay_snapshot["expected"]["quarters"][0]["pv_to_battery_dc_kwh"] = 0.08
    assert await ctrl.apply(plan, now, soc_pct=99, voltage_v=58) == "applied"
    assert service.states.get(GRID_CHARGE).state == "off"
    assert service.states.get(CHARGE_CURRENT).state == "1"
    assert service.states.get(GRID_CURRENT).state == "7"
    assert not any(
        call[2]["entity_id"] in {CHARGE_CURRENT, GRID_CURRENT} for call in service.calls
    )


@pytest.mark.asyncio
async def test_forecast_export_never_caps_real_pv_charging():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    ctrl, service = setup_controller()
    ctrl.arm()
    plan = preview(now, charge=0, discharge=0, grid_a=0)
    current = plan.replay_snapshot["expected"]["quarters"][0]
    current["pv_to_export_dc_kwh"] = 0.50
    plan.replay_snapshot["expected"]["quarters"].append(
        {
            **current,
            "start": (now + timedelta(minutes=15)).isoformat(),
            "pv_to_export_dc_kwh": 0.0,
            "pv_to_battery_dc_kwh": 0.3,
        }
    )
    assert await ctrl.apply(plan, now, soc_pct=70, voltage_v=55) == "applied"
    assert float(service.states.get(CHARGE_CURRENT).state) == 50
    assert not any(call[2]["entity_id"] == CHARGE_CURRENT for call in service.calls)
    current["pv_to_export_dc_kwh"] = 0.0
    current["pv_to_battery_dc_kwh"] = 0.2
    assert (
        await ctrl.apply(plan, now + timedelta(seconds=30), soc_pct=70, voltage_v=55)
        == "applied"
    )
    assert float(service.states.get(CHARGE_CURRENT).state) == 50
    assert not any(call[2]["entity_id"] == CHARGE_CURRENT for call in service.calls)


@pytest.mark.asyncio
async def test_deliberate_multi_quarter_grid_charge_uses_rate_for_smoothing():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    ctrl, service = setup_controller()
    service.states.items[GRID_CURRENT].state = "50"
    ctrl.arm()
    plan = preview(now, charge=0.10, discharge=0, grid_a=7)
    current = plan.replay_snapshot["expected"]["quarters"][0]
    future = (now + timedelta(minutes=15)).isoformat()
    plan.replay_snapshot["expected"]["quarters"].append({**current, "start": future})
    plan.replay_snapshot["quarters"] = [
        {"start": current["start"], "buy_dkk_per_kwh": 0.5},
        {"start": future, "buy_dkk_per_kwh": 0.5},
    ]
    assert await ctrl.apply(plan, now, soc_pct=60, voltage_v=52) == "applied"
    assert float(service.states.get(GRID_CURRENT).state) == 7
    assert float(service.states.get(CHARGE_CURRENT).state) == 50
    assert sum(c[2]["entity_id"] == GRID_CURRENT for c in service.calls) == 1
    assert not any(c[2]["entity_id"] == CHARGE_CURRENT for c in service.calls)


@pytest.mark.asyncio
async def test_grid_charge_switches_on_without_rewriting_existing_positive_limits():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    ctrl, service = setup_controller()
    service.states.items[GRID_CURRENT].state = "7"
    service.states.items[CHARGE_CURRENT].state = "50"
    ctrl.arm()
    plan = preview(now, charge=0.10, discharge=0, grid_a=7)
    assert await ctrl.apply(plan, now, soc_pct=70, voltage_v=52) == "applied"
    assert service.states.get(GRID_CHARGE).state == "on"
    assert not any(
        c[2]["entity_id"] in {CHARGE_CURRENT, GRID_CURRENT} for c in service.calls
    )
