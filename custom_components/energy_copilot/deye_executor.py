"""Supervised Deye TOU executor; fail closed and never auto-actuate.

A live integration must explicitly own and invoke this executor. Compilation
alone cannot verify inverter semantics. No service registrations here.
"""

import asyncio
from dataclasses import dataclass

from .deye_commands import CommandRejected, DeyeCommandAdapter, tou_entities
from .tou_compiler import TOUProgram


@dataclass(frozen=True)
class ExecutionOutcome:
    state: str
    applied: tuple[str, ...]
    reason: str | None = None


class SupervisedTOUExecutor:
    """One writer, explicit arming and STOP, with a complete preflight.

    Any partially executed update is marked recovery_required and NOT
    automatically repeated. Existing settings are not blindly overwritten.
    """

    def __init__(self, hass):
        self.hass = hass
        self.adapter = DeyeCommandAdapter(hass)
        self._lock = asyncio.Lock()
        self._stopped = True

    def stop(self):
        """Stop any subsequent writes; never claim physical inverter shutdown."""
        self._stopped = True

    def arm(self):
        """Explicit local arming; not exposed by the HA integration."""
        self._stopped = False

    def _snapshot(self, program: TOUProgram):
        if len(program.windows) != 6:
            raise CommandRejected("tou:must_have_six_windows")
        starts = [window.start_minute for window in program.windows]
        if starts[0] != 0 or starts != sorted(set(starts)):
            raise CommandRejected("tou:invalid_window_order")
        if any(
            window.minimum_soc_pct < 20
            or window.minimum_soc_pct > 100
            or window.power_w < 0
            or window.power_w > 12000
            or window.start_minute < 0
            or window.start_minute >= 1440
            or window.start_minute % 60
            for window in program.windows
        ):
            raise CommandRejected("tou:outside_policy")

        settings = []
        for i, window in enumerate(program.windows, 1):
            entities = tou_entities(i)
            # Minute-of-day -> HHMM. This must be verified against the
            # actual HA number entity units before being enabled live.
            hour, minute = divmod(window.start_minute, 60)
            settings.extend(
                (
                    (entities["start"], hour * 100 + minute),
                    (entities["power"], window.power_w),
                    (entities["soc"], window.minimum_soc_pct),
                    (entities["grid_charge"], window.grid_charge),
                )
            )
        for entity_id, _ in settings:
            self.adapter._present(entity_id)
        return tuple(settings)

    async def apply(self, program: TOUProgram, *, plan_id: str) -> ExecutionOutcome:
        if not plan_id or not isinstance(plan_id, str):
            return ExecutionOutcome("blocked", (), "tou:missing_plan_id")
        if self._stopped:
            return ExecutionOutcome("blocked", (), "executor:stopped")
        if self._lock.locked():
            return ExecutionOutcome("blocked", (), "executor:busy")
        async with self._lock:
            try:
                settings = self._snapshot(program)
            except (CommandRejected, ValueError) as error:
                return ExecutionOutcome("blocked", (), str(error))
            applied = []
            for entity_id, value in settings:
                if self._stopped:
                    return ExecutionOutcome(
                        "recovery_required" if applied else "blocked",
                        tuple(applied),
                        "executor:stopped",
                    )
                try:
                    if entity_id.startswith("number."):
                        await self.adapter.set_number(entity_id, value)
                    else:
                        await self.adapter.set_switch(entity_id, value)
                except Exception as error:
                    # Unknown outcome: do not retry and do not guess rollback
                    # order when the device accepted only part of the plan.
                    return ExecutionOutcome(
                        "recovery_required" if applied else "uncertain",
                        tuple(applied),
                        f"device:write_failed:{type(error).__name__}",
                    )
                applied.append(entity_id)
            return ExecutionOutcome("applied", tuple(applied))
