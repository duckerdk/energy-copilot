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

    def _legacy_charge_restore(self, observed_a):
        """Recover a previous PV-deferral limit using persisted OWN writes.

        A missing journal or any later controller write prevents guessing.
        Do not replace an observed operator setting other than that exact
        legacy 1 A limit with proven 1 A provenance.
        """
        if abs(observed_a - 1.0) > 1e-6:
            return None
        if self.journal is None or not self.journal.available:
            return None
        for event in reversed(self.journal.entries):
            for change in reversed(event.get("command_changes") or []):
                if change.get("entity_id") != CHARGE_CURRENT:
                    continue
                try:
                    before = float(change["before"])
                    after = float(change["after"])
                except ValueError, TypeError, KeyError:
                    return None
                if (
                    abs(after - 1.0) < 1e-6
                    and isfinite(before)
                    and 1.0 < before <= 50.0
                    and event.get("event") == "applied"
                ):
                    return before
                return None
        return None

    def _decision(self, preview, row, now, soc_pct):
        replay = preview.replay_snapshot or {}
        at = row["start"]
        start_dt = datetime.fromisoformat(at.replace("Z", "+00:00"))
        logical_quarter = start_dt.replace(
            minute=start_dt.minute // 15 * 15, second=0, microsecond=0
        ).isoformat()
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
        risk = metadata.get("load_risk_policy") or {}
        robust = metadata.get("robust_policy") or {}
        risk_campaign = (
            risk.get("status") == "applied"
            and risk.get("charge_start_utc", "") <= at
            and at < risk.get("charge_end_utc", "")
        )
        if charge > 1e-7:
            action = "grid_charge"
            reason = (
                "load_risk_reserve_before_price_peak"
                if risk_campaign
                else "optimizer_selected_grid_charge_for_full_horizon_cost"
            )
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
            "robust_strategy": robust.get("selection"),
            "robust_risk_reduction_dkk": robust.get("estimated_risk_reduction_dkk"),
            "robust_nominal_objective_dkk": robust.get("nominal_objective_dkk"),
            "robust_selected_objective_dkk": robust.get("selected_objective_dkk"),
            "robust_scenario_weights_calibrated": (
                robust.get("scenarios", {}).get("weights_are_calibrated_probabilities")
            ),
            "plan_id": f"{metadata.get('forecast_version', 'unknown')}:{logical_quarter}",
            "quarter_start_utc": logical_quarter,
            "live_plan_sample_utc": at,
            "observed_at_utc": now.isoformat(),
            "forecast_version": metadata.get("forecast_version"),
            "load_risk_extra_soc_points": (
                risk.get("applied_extra_soc_points") if risk_campaign else None
            ),
            "load_risk_peak_start_utc": (
                risk.get("peak_start_utc") if risk_campaign else None
            ),
            "load_risk_estimated_value_dkk": (
                risk.get("estimated_avoided_risk_dkk") if risk_campaign else None
            ),
            "load_risk_nominal_cost_dkk": (
                risk.get("extra_nominal_objective_dkk") if risk_campaign else None
            ),
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
        source_by_start = {
            q["start"]: q for q in preview.replay_snapshot.get("quarters", ())
        }
        next_row = None
        for row in expected:
            at = datetime.fromisoformat(row["start"].replace("Z", "+00:00"))
            if at.tzinfo is None:
                raise CommandRejected("controller:naive_timestamp")
            source = source_by_start.get(row["start"], {})
            end = datetime.fromisoformat(
                source.get("end", (at + timedelta(minutes=15)).isoformat()).replace(
                    "Z", "+00:00"
                )
            )
            if at <= now < end:
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
                projection = getattr(preview, "tou_feasibility", None)
                if (
                    isinstance(projection, dict)
                    and projection.get("status") == "not_representable"
                ):
                    raise CommandRejected("controller:plan_not_representable_by_tou")
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
                logical_quarter = boundary.replace(
                    minute=boundary.minute // 15 * 15,
                    second=0,
                    microsecond=0,
                ).isoformat()
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
                    logical_quarter,
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
                # 99% is a completed grid-charge objective; leave remaining
                # headroom for natural PV rather than a cosmetic grid top-up.
                if soc_pct >= 99.0:
                    charge_enabled = False
                if charge > 1e-7 and grid_a <= 1e-7:
                    raise CommandRejected("controller:charge_plan_without_grid_current")
                projected_soc = float(row["soc_end_pct"])
                if (
                    not isfinite(projected_soc)
                    or not 20 - 1e-6 <= projected_soc <= 100 + 1e-6
                ):
                    raise CommandRejected("controller:target_soc_invalid")
                if charge_enabled:
                    # With Grid Charge ON, this SOC becomes the *charging target*.
                    # Never use a PV-only rise to request additional grid charging.
                    grid_efficiency = float(
                        (preview.replay_snapshot or {})
                        .get("plant", {})
                        .get("eta_grid_to_battery", 0.95)
                    )
                    if not 0 < grid_efficiency <= 1:
                        raise CommandRejected("controller:grid_efficiency_invalid")
                    capacity = float(
                        (preview.replay_snapshot or {})
                        .get("plant", {})
                        .get("battery_capacity_dc_kwh", 10.24)
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
                    # A quarter's predicted end SOC is NOT the discharge reserve.
                    # Release the full usable battery range immediately; the
                    # inverter's 20% safety floor remains in force. Replanning
                    # every quarter must not ration access to stored energy.
                    target_soc = 20.0
                else:
                    # At or below the TOU floor, Deye will preserve the battery.
                    # Continue following measured SOC as PV raises the charge.
                    target_soc = ceil(soc_pct)
                target_soc = self.adapter.quantize_number(
                    slot["soc"],
                    float(max(20, min(100, target_soc))),
                    direction="down" if discharge > 1e-7 else "up",
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

                # Global battery charging current stays untouched by default.
                # A PV forecast or high SOC is not a reason to write a new cap.
                source_quarters = (preview.replay_snapshot or {}).get("quarters", ())
                expected_quarters = (
                    (preview.replay_snapshot or {})
                    .get("expected", {})
                    .get("quarters", ())
                )
                # Forecast dispatch is descriptive, not a hard PV charge cap.
                # Do not throttle the shared battery charge current to force
                # forecast PV export: real surplus may exceed the forecast.
                # A grid-charge campaign intentionally spread over several
                # similarly cheap quarters is the other valid current policy.
                current_input = next(
                    (q for q in source_quarters if q.get("start") == at), {}
                )
                spreading_grid = charge_enabled and any(
                    float(q.get("grid_to_battery_ac_kwh") or 0) > 1e-7
                    and any(
                        src.get("start") == q.get("start")
                        and abs(
                            float(src["buy_dkk_per_kwh"])
                            - float(current_input["buy_dkk_per_kwh"])
                        )
                        <= 0.01
                        for src in source_quarters
                        if current_input
                    )
                    for q in expected_quarters
                    if q.get("start", "") > at
                )

                charge_state = self.adapter._present(CHARGE_CURRENT)
                grid_state = self.adapter._present(GRID_CURRENT)
                current_charge_a = float(charge_state.state)
                current_grid_a = float(grid_state.state)
                settings = []
                charge_policy = "unchanged_no_rate_control_needed"
                restore = self._legacy_charge_restore(current_charge_a)
                if restore is not None:
                    settings.append((CHARGE_CURRENT, restore))
                    charge_policy = "restore_after_legacy_pv_deferral"

                # A new current write is justified ONLY by a deliberate
                # time-spreading campaign. Grid-charge enablement alone is
                # not a third reason to adjust an arbitrary current.
                if charge_enabled and current_grid_a < 1.0 and not spreading_grid:
                    raise CommandRejected(
                        "controller:grid_charge_limit_requires_campaign"
                    )
                if spreading_grid:
                    # Deliberately spread charging over several equally cheap
                    # quarters. Never track forecast current outside a campaign.
                    desired_grid_a = self.adapter.quantize_number(
                        GRID_CURRENT,
                        max(1.0, min(50.0, ceil(grid_a))),
                        direction="up",
                    )
                    if abs(current_grid_a - desired_grid_a) > 1e-6:
                        settings.append((GRID_CURRENT, desired_grid_a))
                    # Raise the shared cap only if it would prevent the
                    # specifically planned controlled charging rate.
                    effective_charge_a = next(
                        (
                            v
                            for entity, v in reversed(settings)
                            if entity == CHARGE_CURRENT
                        ),
                        current_charge_a,
                    )
                    if effective_charge_a < desired_grid_a - 1e-6:
                        settings.append(
                            (
                                CHARGE_CURRENT,
                                self.adapter.quantize_number(
                                    CHARGE_CURRENT, desired_grid_a, direction="up"
                                ),
                            )
                        )
                    charge_policy = "spread_grid_charge_over_low_price_window"
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
                    # Disable slot permission before updating the TOU SOC floor.
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
                self.last_plan_start = logical_quarter
                self.status = "applied"
                self.reason = None
                application_key = (
                    logical_quarter,
                    target_soc,
                    charge_enabled,
                    tuple(settings),
                    charge_policy,
                    planned_sell,
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
                        quarter_start_utc=logical_quarter,
                        state=self.status,
                        target_tou_soc=target_soc,
                        observed_tou_soc=self.observed_tou_soc,
                        target_tou_grid_charge=charge_enabled,
                        observed_tou_grid_charge=self.observed_tou_grid_charge,
                        grid_limit_a=float(self.adapter._present(GRID_CURRENT).state),
                        charge_limit_a=float(
                            self.adapter._present(CHARGE_CURRENT).state
                        ),
                        charging_current_policy=charge_policy,
                        discharge_control="tou_soc_floor",
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
