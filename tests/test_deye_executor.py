"""The M6 supervised executor must never partially apply without quarantine."""

from types import SimpleNamespace

import pytest

from custom_components.energy_copilot.deye_commands import tou_entities
from custom_components.energy_copilot.deye_executor import SupervisedTOUExecutor
from custom_components.energy_copilot.tou_compiler import TOUProgram, TOUWindow


def program():
    return TOUProgram(
        tuple(TOUWindow(hour * 60, 2560, 20 + hour, False) for hour in range(6))
    )


class States:
    def __init__(self):
        self.data = {}
        for i in range(1, 7):
            entities = tou_entities(i)
            for key, entity_id in entities.items():
                value = "off" if key == "grid_charge" else "0"
                self.data[entity_id] = SimpleNamespace(
                    state=value, attributes={"min": 0, "max": 12000, "step": 1}
                )

    def get(self, entity_id):
        return self.data.get(entity_id)


class Services:
    def __init__(self, states, fail_after=None):
        self.states = states
        self.calls = []
        self.fail_after = fail_after

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))
        if self.fail_after and len(self.calls) == self.fail_after:
            raise RuntimeError("disconnected")
        entity_id = data["entity_id"]
        old = self.states.data[entity_id]
        state = (
            str(data["value"])
            if domain == "number"
            else ("on" if service == "turn_on" else "off")
        )
        self.states.data[entity_id] = SimpleNamespace(
            state=state, attributes=old.attributes
        )


def executor(*, fail_after=None):
    states = States()
    services = Services(states, fail_after=fail_after)
    result = SupervisedTOUExecutor(
        SimpleNamespace(states=states, services=services)
    )
    return result, services


@pytest.mark.asyncio
async def test_executor_stays_disarmed_by_default():
    writer, services = executor()
    result = await writer.apply(program(), plan_id="plan-1")
    assert result.state == "blocked"
    assert result.reason == "executor:stopped"
    assert services.calls == []


@pytest.mark.asyncio
async def test_supervised_six_window_write_has_readback():
    writer, services = executor()
    writer.arm()
    result = await writer.apply(program(), plan_id="plan-1")
    assert result.state == "applied"
    assert len(result.applied) == 24
    assert len(services.calls) == 24
    writer.stop()
    blocked = await writer.apply(program(), plan_id="plan-2")
    assert blocked.state == "blocked"
    assert len(services.calls) == 24


@pytest.mark.asyncio
async def test_partial_write_never_blindly_retries():
    writer, services = executor(fail_after=5)
    writer.arm()
    result = await writer.apply(program(), plan_id="plan-1")
    assert result.state == "recovery_required"
    assert len(result.applied) == 4
    assert len(services.calls) == 5


@pytest.mark.asyncio
async def test_invalid_plan_never_writes():
    writer, services = executor()
    writer.arm()
    malformed = TOUProgram(
        tuple(TOUWindow(60, 2560, 20, False) for _ in range(6))
    )
    result = await writer.apply(malformed, plan_id="plan-1")
    assert result.state == "blocked"
    assert services.calls == []
