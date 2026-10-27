"""Deye execution boundary: explicit allowlists and confirmed reads."""
from types import SimpleNamespace

import pytest

from custom_components.energy_copilot.deye_commands import (
    CHARGE_CURRENT,
    GRID_CHARGE,
    CommandRejected,
    DeyeCommandAdapter,
    tou_entities,
)


class FakeStates:
    def __init__(self):
        self.values = {
            CHARGE_CURRENT: SimpleNamespace(
                state="10", attributes={"min": 0, "max": 200, "step": 1}
            ),
            GRID_CHARGE: SimpleNamespace(state="off", attributes={}),
        }

    def get(self, entity_id):
        return self.values.get(entity_id)


class FakeServices:
    def __init__(self, states, *, acknowledge=True):
        self.states = states
        self.acknowledge = acknowledge
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))
        if self.acknowledge:
            entity = self.states.values[data["entity_id"]]
            value = str(data["value"]) if domain == "number" else (
                "on" if service == "turn_on" else "off"
            )
            self.states.values[data["entity_id"]] = SimpleNamespace(
                state=value, attributes=entity.attributes
            )


def adapter(*, acknowledge=True):
    states = FakeStates()
    services = FakeServices(states, acknowledge=acknowledge)
    return DeyeCommandAdapter(SimpleNamespace(states=states, services=services)), services


def test_tou_mapping_all_six_and_invalid_numbers():
    assert tou_entities(1)["soc"] == "number.sun12k_time_point_1_capacity"
    assert tou_entities(6)["grid_charge"] == (
        "switch.sun12k_time_point_6_charge_enable"
    )
    for invalid in (0, 7, "1", True):
        with pytest.raises(ValueError):
            tou_entities(invalid)


@pytest.mark.asyncio
async def test_number_write_policy_and_readback():
    device, services = adapter()
    result = await device.set_number(CHARGE_CURRENT, 12)
    assert result.confirmed is True
    assert len(services.calls) == 1
    with pytest.raises(CommandRejected, match="outside_policy"):
        await device.set_number(CHARGE_CURRENT, 51)
    with pytest.raises(CommandRejected, match="not_allowlisted"):
        await device.set_number("number.some_unapproved_number", 12)
    assert len(services.calls) == 1


@pytest.mark.asyncio
async def test_unconfirmed_write_does_not_retry():
    device, services = adapter(acknowledge=False)
    with pytest.raises(CommandRejected, match="write_unconfirmed"):
        await device.set_switch(GRID_CHARGE, True)
    assert len(services.calls) == 1


@pytest.mark.asyncio
async def test_switch_write_validation():
    device, services = adapter()
    assert (await device.set_switch(GRID_CHARGE, True)).confirmed
    with pytest.raises(CommandRejected, match="not_allowlisted"):
        await device.set_switch("switch.unapproved", True)
    assert len(services.calls) == 1
