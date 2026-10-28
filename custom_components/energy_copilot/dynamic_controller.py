"""Dynamic M6 controller using the actual optimizer replay, not six-window compression.

Armed on startup in automatic mode; manual STOP inhibits commands until restart.
The configured Deye TOU schedule remains the underlying inverter safeguard.
"""

import asyncio
from datetime import datetime, timedelta
from math import ceil, floor, isfinite
from zoneinfo import ZoneInfo

from .deye_commands import (
    CHARGE_CURRENT,
    DISCHARGE_CURRENT,
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
            source_by_time.get(later_discharge["start"], {})
            if later_discharge
            else {}
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
            self._write_started = True
            await self.adapter.set_number(entity, value)

    async def _set_switch_if_changed(self, entity, enabled):
        if self.adapter._present(entity).state != ("on" if enabled else "off"):
            self._write_started = True
            await self.adapter.set_switch(entity, enabled)

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
                    if self.status != "blocked" or self.reason != reason:
                        self._audit("blocked", reason=reason, state="blocked")
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
                if charge_enabled:
                    projected_soc = float(row["soc_end_pct"])
                    if not isfinite(projected_soc):
                        raise CommandRejected("controller:target_soc_invalid")
                    target_soc = max(ceil(soc_pct), ceil(projected_soc))
                    target_soc = max(20, min(100, target_soc))
                    if target_soc <= soc_pct:
                        charge_enabled = False
                else:
                    target_soc = 20
                target_soc = self.adapter.quantize_number(
                    slot["soc"], float(target_soc), direction="up"
                )
                self.target_tou_soc = target_soc
                self.target_tou_grid_charge = charge_enabled
                self.observed_tou_soc = float(self.adapter._present(slot["soc"]).state)
                self.observed_tou_grid_charge = self.adapter._present(
                    slot["grid_charge"]
                ).state
                # Positive current allowance permits PV charging. Never
                # set it to zero just to suppress grid charging.
                total_charge_a = 50.0
                # A quarter energy budget is not an instantaneous power limit.
                # When discharging is authorised, let Deye follow actual load.
                # Never command more than 100 A or the entity's lower device cap.
                discharge_state = self.adapter._present(DISCHARGE_CURRENT)
                discharge_max = float(discharge_state.attributes.get("max", 100))
                if not isfinite(discharge_max) or discharge_max < 0:
                    raise CommandRejected("controller:discharge_max_invalid")
                discharge_limit = min(100.0, discharge_max) if discharge > 1e-7 else 0.0
                grid_state = self.adapter._present(GRID_CURRENT)
                grid_step = float(grid_state.attributes.get("step", 1))
                if not isfinite(grid_step) or grid_step <= 0:
                    raise CommandRejected("controller:grid_step_invalid")
                grid_limit = min(50.0, max(0.0, floor(grid_a / grid_step) * grid_step))
                # Device steps are validated by the command adapter.
                settings = (
                    (
                        CHARGE_CURRENT,
                        self.adapter.quantize_number(CHARGE_CURRENT, total_charge_a),
                    ),
                    (
                        DISCHARGE_CURRENT,
                        self.adapter.quantize_number(
                            DISCHARGE_CURRENT, discharge_limit
                        ),
                    ),
                    (
                        GRID_CURRENT,
                        self.adapter.quantize_number(GRID_CURRENT, grid_limit),
                    ),
                )
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
                # Solar Sell is price-controlled by the planner, not by the
                # instantaneous inverter export measurement.
                for entry in preview.hourly_plan:
                    start = datetime.fromisoformat(entry["start"])
                    if start <= now < start + timedelta(hours=1):
                        planned_sell = bool(entry["solar_sell_planned_on"])
                        if self.adapter._present(SOLAR_SELL).state != (
                            "on" if planned_sell else "off"
                        ):
                            await self._set_switch_if_changed(SOLAR_SELL, planned_sell)
                        break
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
                    discharge_limit,
                )
                if application_key != self._last_application_key:
                    self._last_application_key = application_key
                    self._audit(
                        "applied",
                        reason="settings_written_and_read_back",
                        quarter_start_utc=at,
                        state=self.status,
                        target_tou_soc=target_soc,
                        observed_tou_soc=self.observed_tou_soc,
                        target_tou_grid_charge=charge_enabled,
                        observed_tou_grid_charge=self.observed_tou_grid_charge,
                        grid_limit_a=grid_limit,
                        discharge_limit_a=discharge_limit,
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
                if event == "halted" or self.reason != getattr(
                    self, "_last_block_reason", None
                ):
                    self._audit(
                        event,
                        reason=self.reason,
                        state=self.status,
                        quarter_start_utc=at,
                        phase=phase,
                    )
                self._last_block_reason = self.reason
            return self.status
