"""M6 Deye Home Assistant command adapter.

Single-change supervised building block. Not wired to config flow or the planner:
no automatic inverter writes until TOU feasibility and recovery are validated.
"""

import asyncio
from dataclasses import dataclass
from math import ceil, floor, isfinite

CHARGE_CURRENT = "number.sun12k_maximum_battery_charge_current"
DISCHARGE_CURRENT = "number.sun12k_maximum_battery_discharge_current"
GRID_CURRENT = "number.sun12k_maximum_battery_grid_charge_current"
GRID_CHARGE = "switch.sun12k_grid_charge"
SOLAR_SELL = "switch.sun12k_solar_sell"
TIME_OF_USE = "switch.sun12k_time_of_use"

LIMITS = {
    CHARGE_CURRENT: (0.0, 50.0),
    DISCHARGE_CURRENT: (0.0, 100.0),
    GRID_CURRENT: (0.0, 50.0),
}
SWITCHES = frozenset({GRID_CHARGE, SOLAR_SELL, TIME_OF_USE})


def tou_entities(point: int) -> dict[str, str]:
    """Map one of six documented Deye TOU windows."""
    if type(point) is not int or point not in range(1, 7):
        raise ValueError("tou:invalid_point")
    prefix = f"sun12k_time_point_{point}"
    return {
        "start": f"number.{prefix}_start",
        "power": f"number.{prefix}_power",
        "soc": f"number.{prefix}_capacity",
        "grid_charge": f"switch.{prefix}_charge_enable",
    }


@dataclass(frozen=True)
class WriteResult:
    entity_id: str
    requested: float | bool
    confirmed: bool


class CommandRejected(ValueError):
    """A requested setting is unsafe, unknown or unconfirmed."""


class DeyeCommandAdapter:
    """Permit-list and readback gate for a future supervised executor.

    A service call returning normally is NOT proof of device confirmation.
    No retry or automatic rollback is performed on uncertain outcomes.
    """

    def __init__(self, hass):
        self.hass = hass

    def _present(self, entity_id):
        state = self.hass.states.get(entity_id)
        if state is None or state.state in {"unavailable", "unknown"}:
            raise CommandRejected("device:entity_unavailable")
        return state

    async def _confirm_number(self, entity_id: str, value: float):
        for _ in range(40):
            state = self._present(entity_id)
            try:
                if abs(float(state.state) - value) < 1e-6:
                    return
            except ValueError:
                pass
            await asyncio.sleep(0.25)
        raise CommandRejected("device:write_unconfirmed")

    async def _confirm_switch(self, entity_id: str, value: bool):
        expected = "on" if value else "off"
        for _ in range(40):
            if self._present(entity_id).state == expected:
                return
            await asyncio.sleep(0.25)
        raise CommandRejected("device:write_unconfirmed")

    def quantize_number(self, entity_id: str, value: float, *, direction="down"):
        """Select a legal HA value without widening inverter current limits.

        SOC charge targets are rounded upward; currents are rounded downward.
        Never silently clamp outside the documented policy.
        """
        policy = dict(LIMITS)
        for point in range(1, 7):
            slot = tou_entities(point)
            policy[slot["soc"]] = (20.0, 100.0)
        if entity_id not in policy:
            raise CommandRejected(f"device:number_not_allowlisted:{entity_id}")
        if not isfinite(value):
            raise CommandRejected(f"device:number_invalid:{entity_id}")
        low, high = policy[entity_id]
        state = self._present(entity_id)
        try:
            minimum = float(state.attributes.get("min", low))
            maximum = float(state.attributes.get("max", high))
            step = float(state.attributes.get("step", 1))
        except (ValueError, TypeError) as exc:
            raise CommandRejected(f"device:number_metadata_invalid:{entity_id}") from exc
        if not all(isfinite(x) for x in (minimum, maximum, step)) or step <= 0:
            raise CommandRejected(f"device:number_metadata_invalid:{entity_id}")
        low = max(low, minimum)
        high = min(high, maximum)
        if not low <= value <= high:
            raise CommandRejected(
                f"device:number_outside_range:{entity_id}:requested={value}:"
                f"min={low}:max={high}"
            )
        steps = (value - minimum) / step
        index = (
            ceil(steps - 1e-8)
            if direction == "up"
            else floor(steps + 1e-8)
        )
        result = minimum + index * step
        if result < low - 1e-7 or result > high + 1e-7:
            raise CommandRejected(
                f"device:number_unrepresentable:{entity_id}:requested={value}:"
                f"min={minimum}:max={maximum}:step={step}"
            )
        return round(result, 7)

    async def set_number(self, entity_id: str, value: float) -> WriteResult:
        limits = dict(LIMITS)
        for point in range(1, 7):
            window = tou_entities(point)
            limits[window["start"]] = (0.0, 2359.0)
            limits[window["power"]] = (0.0, 12000.0)
            limits[window["soc"]] = (20.0, 100.0)
        if entity_id not in limits:
            raise CommandRejected("device:number_not_allowlisted")
        if type(value) not in (float, int) or not float("-inf") < value < float("inf"):
            raise CommandRejected("device:number_invalid")
        low, high = limits[entity_id]
        if not low <= value <= high:
            raise CommandRejected("device:number_outside_policy")
        before = self._present(entity_id)
        attrs = before.attributes
        try:
            device_low = float(attrs.get("min", low))
            device_high = float(attrs.get("max", high))
            step = float(attrs.get("step", 1))
        except (TypeError, ValueError) as exc:
            raise CommandRejected("device:number_metadata_invalid") from exc
        if not device_low <= value <= device_high or step <= 0:
            raise CommandRejected("device:number_outside_device_range")
        device_base = device_low
        if (
            abs((value - device_base) / step - round((value - device_base) / step))
            > 1e-7
        ):
            raise CommandRejected(
                f"device:number_step_invalid:{entity_id}:requested={value}:"
                f"min={device_low}:step={step}"
            )
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )
        await self._confirm_number(entity_id, value)
        return WriteResult(entity_id, value, True)

    async def set_switch(self, entity_id: str, value: bool) -> WriteResult:
        if entity_id not in SWITCHES and entity_id not in {
            tou_entities(i)["grid_charge"] for i in range(1, 7)
        }:
            raise CommandRejected("device:switch_not_allowlisted")
        if type(value) is not bool:
            raise CommandRejected("device:switch_invalid")
        self._present(entity_id)
        await self.hass.services.async_call(
            "switch",
            "turn_on" if value else "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )
        await self._confirm_switch(entity_id, value)
        return WriteResult(entity_id, value, True)
