"""Dynamic M6 controller using the actual optimizer replay, not six-window compression.

Armed on startup in automatic mode; manual STOP inhibits commands until restart.
The configured Deye TOU schedule remains the underlying inverter safeguard.
"""

import asyncio
from datetime import datetime, timedelta
from math import ceil, isfinite
from zoneinfo import ZoneInfo

from .deye_commands import (
    CHARGE_CURRENT,
    GRID_CHARGE,
    GRID_CURRENT,
    SOLAR_SELL,
    TIME_OF_USE,
    CommandRejected,
    DeyeCommandAdapter,
    tou_entities,
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
        self.active_tou_slot = None
        self.target_tou_soc = None
        self.target_tou_grid_charge = None
        self.observed_tou_soc = None
        self.observed_tou_grid_charge = None
        self._lock = asyncio.Lock()
        self._pending_quarter = None
        self.journal = None
        self._write_started = False
        self._last_decision_key = None
        self._last_application_key = None
        self._command_changes = []
        self._attempted_command = None
        self._last_tou_block_quarter = None

    def _audit(self, event, **details):
        if self.journal is not None:
            self.journal.record(event, **details)

    def _decision(self, preview, row, now, soc_pct):
        replay = preview.replay_snapshot or {}
        at = row["start"]
        source = next(
            (item for item in replay.get("quarters", ()) if item.get("start") == at),
            {},
        )
        expected = replay.get("expected", {}).get("quarters", ())
        summary = replay.get("expected", {}).get("summary", {})
        metadata = replay.get("metadata", {})
        source_by_time = {
            item.get("start"): item for item in replay.get("quarters", ())
        }
        later_discharge = next(
            (
                candidate
                for candidate in expected
                if candidate.get("start", "") > at
                and float(candidate.get("battery_to_home_dc_kwh") or 0) > 1e-7
            ),
            None,
        )
        later_discharge_source = (
            source_by_time.get(later_discharge["start"], {}) if later_discharge else {}
        )
        later_grid_charge = next(
            (
                candidate
                for candidate in expected
                if candidate.get("start", "") > at
                and float(candidate.get("grid_to_battery_ac_kwh") or 0) > 1e-7
            ),
            None,
        )
        later_grid_charge_source = (
            source_by_time.get(later_grid_charge["start"], {})
            if later_grid_charge
            else {}
        )
        charge = float(row["grid_to_battery_ac_kwh"])
        discharge = float(row["battery_to_home_dc_kwh"])
        pv_charge = float(row.get("pv_to_battery_dc_kwh", 0))
        if charge > 1e-7:
            action = "grid_charge"
            reason = "optimizer_selected_grid_charge_for_full_horizon_cost"
        elif discharge > 1e-7:
            action = "battery_discharge"
            reason = "optimizer_selected_discharge_for_full_horizon_cost"
        elif pv_charge > 1e-7:
            action = "pv_charge"
            reason = "optimizer_selected_pv_storage"
        elif row.get("grid_import_kwh", 0) > 1e-7:
            action = "grid_import"
            reason = "optimizer_selected_grid_import_preserving_battery"
        else:
            action = "idle"
            reason = "optimizer_selected_no_grid_charge_or_battery_discharge"
        return {
            "reason": reason,
            "action": action,
            "plan_id": f"{metadata.get('forecast_version', 'unknown')}:{at}",
            "quarter_start_utc": at,
            "observed_at_utc": now.isoformat(),
            "forecast_version": metadata.get("forecast_version"),
            "soc_observed_pct": soc_pct,
            "soc_planned_end_pct": row.get("soc_end_pct"),
            "buy_dkk_per_kwh": source.get("buy_dkk_per_kwh"),
            "sell_dkk_per_kwh": source.get("sell_dkk_per_kwh"),
            "pv_forecast_dc_kwh": source.get("pv_dc_kwh"),
            "home_forecast_ac_kwh": source.get("home_ac_kwh"),
            "grid_charge_ac_kwh": charge,
            "battery_discharge_dc_kwh": discharge,
            "pv_charge_dc_kwh": pv_charge,
            "planned_grid_import_kwh": row.get("grid_import_kwh"),
            "grid_charge_current_a": row.get("grid_charge_current_a"),
            "purchase_cost_dkk": row.get("purchase_dkk"),
            "degradation_cost_dkk": row.get("degradation_dkk"),
            "whole_horizon_objective_dkk": summary.get("objective_dkk"),
            "reference_objective_dkk": summary.get("reference_objective_dkk"),
            "cost_basis": "whole_horizon_not_per_quarter_counterfactual",
            "battery_to_ac_efficiency": replay.get("plant", {}).get(
                "eta_battery_to_ac"
            ),
            "later_discharge_start_utc": (
                later_discharge["start"] if later_discharge else None
            ),
            "later_discharge_buy_dkk_per_kwh": later_discharge_source.get(
                "buy_dkk_per_kwh"
            ),
            "later_discharge_dc_kwh": (
                later_discharge.get("battery_to_home_dc_kwh")
                if later_discharge
                else None
            ),
            "later_grid_charge_start_utc": (
                later_grid_charge["start"] if later_grid_charge else None
            ),
            "later_grid_charge_buy_dkk_per_kwh": later_grid_charge_source.get(
                "buy_dkk_per_kwh"
            ),
        }

    TOU_STARTS = (0, 400, 800, 1200, 1600, 2000)

    def _active_tou(self, now):
        """Identify fixed four-hour slots using the inverter's Copenhagen clock."""
        local = now.astimezone(ZoneInfo("Europe/Copenhagen"))
        point = local.hour // 4 + 1
        for index, start in enumerate(self.TOU_STARTS, start=1):
            state = self.adapter._present(tou_entities(index)["start"])
            try:
                observed = float(state.state)
            except ValueError as exc:
                raise CommandRejected("controller:tou_start_invalid") from exc
            if not isfinite(observed) or abs(observed - start) > 0.01:
                raise CommandRejected(
                    f"controller:tou_schedule_mismatch:slot={index}:observed={state.state}"
                )
        return tou_entities(point)

    async def _set_number_if_changed(self, entity, value):
        state = self.adapter._present(entity)
        if abs(float(state.state) - value) > 1e-6:
            change = {"entity_id": entity, "before": state.state, "after": value}
            self._write_started = True
            self._attempted_command = change
            await self.adapter.set_number(entity, value)
            self._command_changes.append(change)
            self._attempted_command = None

    async def _set_switch_if_changed(self, entity, enabled):
        state = self.adapter._present(entity)
        if state.state != ("on" if enabled else "off"):
            change = {
                "entity_id": entity,
                "before": state.state,
                "after": "on" if enabled else "off",
            }
            self._write_started = True
            self._attempted_command = change
            await self.adapter.set_switch(entity, enabled)
            self._command_changes.append(change)
            self._attempted_command = None

    def stop(self, *, manual=False):
        was_armed = self.armed
        self.armed = False
        self._pending_quarter = None
        self.status = "stopped"
        if manual:
            self.reason = "controller:manual_stop"
        if was_armed:
            self._audit(
                "manual_stop" if manual else "stop",
                reason=self.reason,
                state=self.status,
            )

    def arm(self):
        if self.halted:
            raise CommandRejected("controller:recovery_required")
        was_armed = self.armed
        self.armed = True
        self.status = "armed"
        self.reason = None
        if not was_armed:
            self._audit("armed", reason="automatic_mode_or_user_arm", state="armed")

    def _current_quarter(self, preview, now):
        """Cache next-quarter dispatch until its boundary, not just until poll end.

        The planner intentionally starts at the next complete quarter. The
        executor must retain that dispatch and apply it on subsequent polls.
        """
        if preview.status != "preview" or not preview.replay_snapshot:
            raise CommandRejected("controller:plan_missing")
        expected = preview.replay_snapshot.get("expected", {}).get("quarters", ())
        next_row = None
        for row in expected:
            at = datetime.fromisoformat(row["start"].replace("Z", "+00:00"))
            if at.tzinfo is None:
                raise CommandRejected("controller:naive_timestamp")
            if at <= now < at + timedelta(minutes=15):
                self._pending_quarter = None
                return row
            if at > now:
                next_row = row
                break
        pending = self._pending_quarter
        if pending is not None:
            at = datetime.fromisoformat(pending["start"].replace("Z", "+00:00"))
            if at <= now < at + timedelta(minutes=15):
                self._pending_quarter = None
                return pending
            if now >= at + timedelta(minutes=15):
                self._pending_quarter = None
        if next_row is not None:
            at = datetime.fromisoformat(next_row["start"].replace("Z", "+00:00"))
            # Never cache a dispatch further out than the immediately next
            # quarter; this must be refreshed every poll before the boundary.
            if at - now <= timedelta(minutes=15):
                self._pending_quarter = next_row
            return None
        raise CommandRejected("controller:no_current_or_next_quarter")

    async def apply(self, preview, now, *, soc_pct, voltage_v):
        if not self.armed or self.halted:
            return self.status
        if self._lock.locked():
            return self.status
        async with self._lock:
            self._write_started = False
            self._command_changes = []
            self._attempted_command = None
            at = None
            try:
                if not all(isfinite(x) for x in (soc_pct, voltage_v)):
                    raise CommandRejected("controller:invalid_measurements")
                if not 20 <= soc_pct <= 100 or voltage_v <= 0:
                    raise CommandRejected("controller:outside_policy")
                row = self._current_quarter(preview, now)
                if row is None:
                    if self.status != "waiting_for_quarter":
                        self._audit(
                            "waiting",
                            reason="next_complete_quarter_not_started",
                            state="waiting_for_quarter",
                            next_quarter_utc=(
                                self._pending_quarter["start"]
                                if self._pending_quarter
                                else None
                            ),
                        )
                    self.status = "waiting_for_quarter"
                    self.reason = "controller:waiting_for_next_quarter"
                    return self.status
                at = row["start"]
                boundary = datetime.fromisoformat(at.replace("Z", "+00:00"))
                if boundary > now:
                    await asyncio.sleep((boundary - now).total_seconds())
                    if not self.armed or self.halted:
                        return self.status
                    now = boundary
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
                tou_state = self.adapter._present(TIME_OF_USE).state
                if tou_state != "on":
                    reason = f"controller:tou_not_enabled:observed={tou_state}"
                    current_quarter = now.replace(
                        minute=now.minute // 15 * 15,
                        second=0,
                        microsecond=0,
                    ).isoformat()
                    if (
                        self.status != "blocked"
                        or self.reason != reason
                        or self._last_tou_block_quarter != current_quarter
                    ):
                        self._audit(
                            "blocked",
                            reason=reason,
                            state="blocked",
                            quarter_start_utc=current_quarter,
                        )
                        self._last_tou_block_quarter = current_quarter
                    self.status = "blocked"
                    self.reason = reason
                    return self.status
                decision = self._decision(preview, row, now, soc_pct)
                decision_key = (
                    at,
                    decision["action"],
                    charge,
                    discharge,
                    grid_a,
                    decision["buy_dkk_per_kwh"],
                    decision["sell_dkk_per_kwh"],
                )
                if decision_key != self._last_decision_key:
                    self._last_decision_key = decision_key
                    self._audit("decision", **decision)
                slot = self._active_tou(now)
                self.active_tou_slot = (
                    now.astimezone(ZoneInfo("Europe/Copenhagen")).hour // 4 + 1
                )
                charge_enabled = charge > 1e-7 and grid_a > 1e-7
                if charge > 1e-7 and not charge_enabled:
                    raise CommandRejected("controller:charge_plan_without_grid_current")
                projected_soc = float(row["soc_end_pct"])
                if not isfinite(projected_soc) or not 20 - 1e-6 <= projected_soc <= 100 + 1e-6:
                    raise CommandRejected("controller:target_soc_invalid")
                if charge_enabled:
                    # With Grid Charge ON, this SOC becomes the *charging target*.
                    # Never use a PV-only rise to request additional grid charging.
                    grid_efficiency = float(
                        (preview.replay_snapshot or {}).get("plant", {}).get(
                            "eta_grid_to_battery", 0.95
                        )
                    )
                    if not 0 < grid_efficiency <= 1:
                        raise CommandRejected("controller:grid_efficiency_invalid")
                    capacity = float(
                        (preview.replay_snapshot or {}).get("plant", {}).get(
                            "battery_capacity_dc_kwh", 10.24
                        )
                    )
                    if not isfinite(capacity) or capacity <= 0:
                        raise CommandRejected("controller:battery_capacity_invalid")
                    grid_only_end_soc = min(
                        100.0,
                        soc_pct + charge * grid_efficiency / capacity * 100,
                    )
                    target_soc = max(ceil(soc_pct), ceil(grid_only_end_soc))
                    if target_soc <= soc_pct:
                        charge_enabled = False
                elif discharge > 1e-7:
                    # TOU is the discharge floor, not an instantaneous power cap.
                    target_soc = min(ceil(soc_pct), ceil(projected_soc))
                else:
                    # At or below the TOU floor, Deye will preserve the battery.
                    # Continue following measured SOC as PV raises the charge.
                    target_soc = ceil(soc_pct)
                target_soc = self.adapter.quantize_number(
                    slot["soc"], float(max(20, min(100, target_soc))), direction="up"
                )
                self.target_tou_soc = target_soc
                self.target_tou_grid_charge = charge_enabled
                self.observed_tou_soc = float(self.adapter._present(slot["soc"]).state)
                self.observed_tou_grid_charge = self.adapter._present(
                    slot["grid_charge"]
                ).state
                # Read the upcoming export policy before choosing charging speed.
                planned_sell = None
                for hour in preview.hourly_plan:
                    hour_start = datetime.fromisoformat(hour["start"])
                    if hour_start <= now < hour_start + timedelta(hours=1):
                        planned_sell = bool(hour["solar_sell_planned_on"])
                        break
                if planned_sell is None:
                    planned_sell = self.adapter._present(SOLAR_SELL).state == "on"

                pv_charge = float(row.get("pv_to_battery_dc_kwh") or 0)
                if not isfinite(pv_charge) or pv_charge < -1e-9:
                    raise CommandRejected("controller:invalid_pv_charge")
                charge_state = self.adapter._present(CHARGE_CURRENT)
                charge_max = min(50.0, float(charge_state.attributes.get("max", 50)))
                if not isfinite(charge_max) or charge_max < 1:
                    raise CommandRejected("controller:charge_current_range_invalid")
                if pv_charge > 1e-7 or charge_enabled:
                    # A 15-minute DC energy budget translates to an A limit at
                    # measured voltage. Grid energy becomes DC after efficiency.
                    total_dc_kwh = pv_charge + (
                        charge * grid_efficiency if charge_enabled else 0
                    )
                    target_charge_a = max(
                        1.0, min(charge_max, ceil(total_dc_kwh * 4000 / voltage_v))
                    )
                else:
                    # With export prioritized, slow battery charging to the
                    # allowed minimum; otherwise keep PV charging available.
                    target_charge_a = 1.0 if planned_sell else charge_max
                total_charge_a = self.adapter.quantize_number(
                    CHARGE_CURRENT, target_charge_a
                )

                grid_state = self.adapter._present(GRID_CURRENT)
                grid_max = min(50.0, float(grid_state.attributes.get("max", 50)))
                if not isfinite(grid_max) or grid_max < 1:
                    raise CommandRejected("controller:grid_current_range_invalid")
                if charge_enabled:
                    grid_limit = self.adapter.quantize_number(
                        GRID_CURRENT,
                        max(1.0, min(grid_max, ceil(grid_a))),
                        direction="up",
                    )
                    # The global charge limit must not be smaller than the
                    # current needed for the planned grid portion.
                    total_charge_a = self.adapter.quantize_number(
                        CHARGE_CURRENT,
                        min(charge_max, max(total_charge_a, grid_limit)),
                        direction="up",
                    )
                elif float(grid_state.state) < 1:
                    # Repair legacy 0 A from previous releases. Off is governed
                    # by Grid Charge and TOU permission, not by 0 A current.
                    grid_limit = self.adapter.quantize_number(
                        GRID_CURRENT, 1.0, direction="up"
                    )
                else:
                    grid_limit = None
                # Discharge current is never read as a policy input or written.
                # The existing inverter/BMS discharge-current cap is preserved.
                settings = [(CHARGE_CURRENT, total_charge_a)]
                if grid_limit is not None:
                    settings.append((GRID_CURRENT, grid_limit))
                # Stop grid charging first, then update active TOU settings.
                # Never alter window start/end times or non-active SOC settings.
                if (
                    not charge_enabled
                    and self.adapter._present(GRID_CHARGE).state != "off"
                ):
                    await self._set_switch_if_changed(GRID_CHARGE, False)
                if charge_enabled:
                    # Prepare target SOC and slot permission before global enable.
                    await self._set_number_if_changed(slot["soc"], target_soc)
                    await self._set_switch_if_changed(slot["grid_charge"], True)
                else:
                    # Disable slot permission before returning the TOU floor to 20%.
                    await self._set_switch_if_changed(slot["grid_charge"], False)
                    await self._set_number_if_changed(slot["soc"], target_soc)
                for entity, value in settings:
                    await self._set_number_if_changed(entity, value)
                if charge_enabled:
                    await self._set_switch_if_changed(GRID_CHARGE, True)
                # Solar Sell follows the hourly plan; not instantaneous export.
                if self.adapter._present(SOLAR_SELL).state != (
                    "on" if planned_sell else "off"
                ):
                    await self._set_switch_if_changed(SOLAR_SELL, planned_sell)
                self.observed_tou_soc = float(self.adapter._present(slot["soc"]).state)
                self.observed_tou_grid_charge = self.adapter._present(
                    slot["grid_charge"]
                ).state
                self.last_plan_start = at
                self.status = "applied"
                self.reason = None
                application_key = (
                    at,
                    target_soc,
                    charge_enabled,
                    grid_limit,
                    total_charge_a,
                    grid_limit,
                )
                if (
                    application_key != self._last_application_key
                    or self._command_changes
                ):
                    self._last_application_key = application_key
                    self._audit(
                        "applied",
                        reason=(
                            "settings_changed"
                            if self._command_changes
                            else "settings_already_match"
                        ),
                        quarter_start_utc=at,
                        state=self.status,
                        target_tou_soc=target_soc,
                        observed_tou_soc=self.observed_tou_soc,
                        target_tou_grid_charge=charge_enabled,
                        observed_tou_grid_charge=self.observed_tou_grid_charge,
                        grid_limit_a=grid_limit,
                        discharge_limit_a=None,
                        charge_limit_a=total_charge_a,
                        active_tou_slot=self.active_tou_slot,
                        command_changes=list(self._command_changes),
                        commands_sent=len(self._command_changes),
                    )
            except Exception as exc:
                self.reason = f"{type(exc).__name__}:{exc}"
                if self._write_started:
                    # A partially executed command cannot be retried blindly.
                    self.halted = True
                    self.armed = False
                    self.status = "recovery_required"
                    event = "halted"
                    phase = "device_write_result_uncertain"
                else:
                    # A bad measurement/preview must not permanently disarm.
                    self.status = "blocked"
                    event = "blocked"
                    phase = "pre_write_validation"
                quarter = now.replace(
                    minute=now.minute // 15 * 15,
                    second=0,
                    microsecond=0,
                ).isoformat()
                block_fingerprint = (self.reason, quarter)
                if event == "halted" or block_fingerprint != getattr(
                    self, "_last_block_reason", None
                ):
                    self._audit(
                        event,
                        reason=self.reason,
                        state=self.status,
                        quarter_start_utc=at or quarter,
                        phase=phase,
                        completed_commands=list(self._command_changes),
                        attempted_command=self._attempted_command,
                    )
                self._last_block_reason = block_fingerprint
            return self.status
