"""Regression tests for live control, without issuing real HA service writes."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.energy_copilot.deye_commands import (
    CHARGE_CURRENT,
    DISCHARGE_CURRENT,
    GRID_CHARGE,
    GRID_CURRENT,
    SOLAR_SELL,
)
from custom_components.energy_copilot.dynamic_controller import DynamicDeyeController


class States:
    def __init__(self):
        self.items = {
            entity: SimpleNamespace(
                state=value, attributes={"min": 0, "max": 100, "step": 1}
            )
            for entity, value in [
                (CHARGE_CURRENT, "50"),
                (DISCHARGE_CURRENT, "100"),
                (GRID_CURRENT, "0"),
                (GRID_CHARGE, "off"),
                (SOLAR_SELL, "off"),
            ]
        }

    def get(self, key):
        return self.items.get(key)


class Services:
    def __init__(self, states, fail_on=None):
        self.states = states
        self.calls = []
        self.fail_on = fail_on

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))
        entity = data["entity_id"]
        if entity == self.fail_on:
            raise RuntimeError("device failure")
        old = self.states.get(entity)
        value = (
            str(data["value"])
            if domain == "number"
            else "on"
            if service == "turn_on"
            else "off"
        )
        self.states.items[entity] = SimpleNamespace(
            state=value, attributes=old.attributes
        )


def setup_controller(*, fail_on=None):
    states = States()
    service = Services(states, fail_on=fail_on)
    controller = DynamicDeyeController(SimpleNamespace(states=states, services=service))
    return controller, service


def preview(now, *, charge=0.2, discharge=0.0, grid_a=12.0):
    start = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
    return SimpleNamespace(
        status="preview",
        replay_snapshot={
            "expected": {
                "quarters": [
                    {
                        "start": start.isoformat(),
                        "grid_to_battery_ac_kwh": charge,
                        "battery_to_home_dc_kwh": discharge,
                        "grid_charge_current_a": grid_a,
                    }
                ]
            }
        },
        hourly_plan=[
            {
                "start": start.replace(minute=0).isoformat(),
                "solar_sell_planned_on": True,
            }
        ],
    )


@pytest.mark.asyncio
async def test_dynamic_controller_requires_explicit_arm():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    assert await controller.apply(preview(now), now, soc_pct=50, voltage_v=51) == (
        "stopped"
    )
    assert not service.calls


@pytest.mark.asyncio
async def test_dynamic_controller_executes_one_quarter_once():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    result = await controller.apply(preview(now), now, soc_pct=50, voltage_v=51)
    assert result == "applied"
    assert any(c[2]["entity_id"] == GRID_CURRENT for c in service.calls)
    assert any(c[2]["entity_id"] == GRID_CHARGE for c in service.calls)
    assert any(c[2]["entity_id"] == SOLAR_SELL for c in service.calls)
    count = len(service.calls)
    assert (
        await controller.apply(
            preview(now), now + timedelta(minutes=1), soc_pct=50, voltage_v=51
        )
        == "applied"
    )
    assert len(service.calls) == count


@pytest.mark.asyncio
async def test_dynamic_controller_failure_latches_stop():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller(fail_on=GRID_CURRENT)
    controller.arm()
    result = await controller.apply(preview(now), now, soc_pct=50, voltage_v=51)
    assert result == "recovery_required"
    assert controller.halted
    assert not controller.armed
    count = len(service.calls)
    assert await controller.apply(preview(now), now, soc_pct=50, voltage_v=51) == (
        "recovery_required"
    )
    assert len(service.calls) == count


@pytest.mark.asyncio
async def test_discharge_rejected_at_minimum_soc():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    assert await controller.apply(
        preview(now, charge=0.0, discharge=0.1, grid_a=0.0),
        now,
        soc_pct=20.0,
        voltage_v=51.0,
    ) == "recovery_required"
    assert not service.calls
