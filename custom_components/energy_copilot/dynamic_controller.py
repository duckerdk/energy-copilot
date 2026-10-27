"""Dynamic M6 controller using the actual optimizer replay, not six-window compression.

Explicitly armed and stopped from HA. Never writes without a fresh plan.
The configured Deye TOU schedule remains the underlying inverter safeguard.
"""

import asyncio
from datetime import datetime, timedelta
from math import floor, isfinite

from .deye_commands import (
    CHARGE_CURRENT,
    DISCHARGE_CURRENT,
    GRID_CHARGE,
    GRID_CURRENT,
    SOLAR_SELL,
    TIME_OF_USE,
    CommandRejected,
    DeyeCommandAdapter,
)


class DynamicDeyeController:
    """Apply the current quarter's bounded battery-current policy."""

    def __init__(self, hass):
        self.adapter = DeyeCommandAdapter(hass)
        self.armed = False
        self.halted = False
        self.status = "stopped"
        self.reason = None
        self.last_plan_start = None
        self._lock = asyncio.Lock()

    def stop(self):
        self.armed = False
        self.status = "stopped"

    def arm(self):
        if self.halted:
            raise CommandRejected("controller:recovery_required")
        self.armed = True
        self.status = "armed"

    @staticmethod
    def _current_quarter(preview, now):
        if preview.status != "preview" or not preview.replay_snapshot:
            raise CommandRejected("controller:plan_missing")
        replay = preview.replay_snapshot
        expected = replay.get("expected", {}).get("quarters", ())
        future = False
        for row in expected:
            at = datetime.fromisoformat(row["start"].replace("Z", "+00:00"))
            if at.tzinfo is None:
                raise CommandRejected("controller:naive_timestamp")
            if now < at:
                future = True
                if at - now <= timedelta(seconds=30):
                    return row
            if at <= now < at + timedelta(minutes=15):
                if (now - at).total_seconds() > 14 * 60:
                    raise CommandRejected("controller:stale_quarter")
                return row
        if future:
            return None
        raise CommandRejected("controller:no_current_quarter")

    async def apply(self, preview, now, *, soc_pct, voltage_v):
        if not self.armed or self.halted:
            return self.status
        if self._lock.locked():
            return self.status
        async with self._lock:
            try:
                if not all(isfinite(x) for x in (soc_pct, voltage_v)):
                    raise CommandRejected("controller:invalid_measurements")
                if not 20 <= soc_pct <= 100 or voltage_v <= 0:
                    raise CommandRejected("controller:outside_policy")
                row = self._current_quarter(preview, now)
                if row is None:
                    self.status = "waiting_for_quarter"
                    return self.status
                at = row["start"]
                boundary = datetime.fromisoformat(at.replace("Z", "+00:00"))
                if boundary > now:
                    await asyncio.sleep((boundary - now).total_seconds())
                    if not self.armed or self.halted:
                        return self.status
                    now = boundary
                if at == self.last_plan_start:
                    return self.status
                charge = float(row["grid_to_battery_ac_kwh"])
                discharge = float(row["battery_to_home_dc_kwh"])
                grid_a = float(row["grid_charge_current_a"])
                if not all(isfinite(x) for x in (charge, discharge, grid_a)):
                    raise CommandRejected("controller:invalid_dispatch")
                if min(charge, discharge, grid_a) < -1e-9:
                    raise CommandRejected("controller:negative_dispatch")
                if grid_a > 50 + 1e-6:
                    raise CommandRejected("controller:grid_current_limit")
                if charge > 1e-7 and discharge > 1e-7:
                    raise CommandRejected("controller:simultaneous_flow")
                if soc_pct <= 20.1 and discharge > 1e-7:
                    raise CommandRejected("controller:minimum_soc")
                if self.adapter._present(TIME_OF_USE).state != "on":
                    raise CommandRejected("controller:tou_not_enabled")
                charge_enabled = charge > 1e-7
                # Positive current allowance permits PV charging. Never
                # set it to zero just to suppress grid charging.
                total_charge_a = 50.0
                discharge_state = self.adapter._present(DISCHARGE_CURRENT)
                discharge_step = float(discharge_state.attributes.get("step", 1))
                if not isfinite(discharge_step) or discharge_step <= 0:
                    raise CommandRejected("controller:discharge_step_invalid")
                discharge_limit = min(
                    100.0,
                    max(
                        0.0,
                        floor(discharge * 4000 / voltage_v / discharge_step)
                        * discharge_step,
                    ),
                )
                grid_state = self.adapter._present(GRID_CURRENT)
                grid_step = float(grid_state.attributes.get("step", 1))
                if not isfinite(grid_step) or grid_step <= 0:
                    raise CommandRejected("controller:grid_step_invalid")
                grid_limit = min(50.0, max(0.0, floor(grid_a / grid_step) * grid_step))
                # Device steps are validated by the command adapter.
                settings = (
                    (CHARGE_CURRENT, total_charge_a),
                    (DISCHARGE_CURRENT, discharge_limit),
                    (GRID_CURRENT, grid_limit),
                )
                # Disable grid charging before changing discharge policy.
                if (
                    not charge_enabled
                    and self.adapter._present(GRID_CHARGE).state != "off"
                ):
                    await self.adapter.set_switch(GRID_CHARGE, False)
                for entity, value in settings:
                    current = self.adapter._present(entity)
                    if abs(float(current.state) - value) > 1e-6:
                        await self.adapter.set_number(entity, value)
                if charge_enabled and self.adapter._present(GRID_CHARGE).state != "on":
                    await self.adapter.set_switch(GRID_CHARGE, True)
                # Solar Sell is price-controlled by the planner, not by the
                # instantaneous inverter export measurement.
                for entry in preview.hourly_plan:
                    start = datetime.fromisoformat(entry["start"])
                    if start <= now < start + timedelta(hours=1):
                        planned_sell = bool(entry["solar_sell_planned_on"])
                        if self.adapter._present(SOLAR_SELL).state != (
                            "on" if planned_sell else "off"
                        ):
                            await self.adapter.set_switch(SOLAR_SELL, planned_sell)
                        break
                self.last_plan_start = at
                self.status = "applied"
                self.reason = None
            except Exception as exc:
                self.halted = True
                self.armed = False
                self.status = "recovery_required"
                self.reason = f"{type(exc).__name__}:{exc}"
            return self.status
