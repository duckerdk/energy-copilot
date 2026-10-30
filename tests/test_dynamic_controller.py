"""Regression tests for live control, without issuing real HA service writes."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from custom_components.energy_copilot.deye_commands import (
    CHARGE_CURRENT,
    GRID_CHARGE,
    GRID_CURRENT,
    SOLAR_SELL,
    TIME_OF_USE,
    CommandRejected,
    tou_entities,
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
                (GRID_CURRENT, "12"),
                (GRID_CHARGE, "off"),
                (SOLAR_SELL, "off"),
                (TIME_OF_USE, "on"),
            ]
        }
        for index, start in enumerate((0, 400, 800, 1200, 1600, 2000), 1):
            slot = tou_entities(index)
            self.items[slot["start"]] = SimpleNamespace(
                state=str(start), attributes={"min": 0, "max": 2359, "step": 1}
            )
            self.items[slot["soc"]] = SimpleNamespace(
                state="20", attributes={"min": 20, "max": 100, "step": 1}
            )
            self.items[slot["grid_charge"]] = SimpleNamespace(
                state="off", attributes={}
            )

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
                        "soc_end_pct": 65.0,
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
    assert not any(c[2]["entity_id"] == GRID_CURRENT for c in service.calls)
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
async def test_failed_write_recovers_from_fresh_plan_without_disarming():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller(fail_on=GRID_CHARGE)
    controller.arm()
    first = preview(now)
    result = await controller.apply(first, now, soc_pct=50, voltage_v=51)
    assert result == "recovering"
    assert controller.armed
    assert not controller.halted
    assert controller.recovery_attempts == 1
    count = len(service.calls)
    result = await controller.apply(
        first, now + timedelta(seconds=10), soc_pct=50, voltage_v=51
    )
    assert result == "recovering"
    assert len(service.calls) == count
    # The old charge has been cancelled: only the NEW live dispatch is valid.
    service.fail_on = None
    fresh = preview(now, charge=0.0, discharge=0.1, grid_a=0)
    result = await controller.apply(
        fresh, now + timedelta(seconds=31), soc_pct=80, voltage_v=51
    )
    assert result == "applied"
    assert controller.recovery_attempts == 0
    assert controller.armed
    assert float(service.states.get(tou_entities(4)["soc"]).state) == 20.0
    assert service.states.get(GRID_CHARGE).state == "off"


@pytest.mark.asyncio
async def test_discharge_rejected_at_minimum_soc():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    assert (
        await controller.apply(
            preview(now, charge=0.0, discharge=0.1, grid_a=0.0),
            now,
            soc_pct=20.0,
            voltage_v=51.0,
        )
        == "blocked"
    )
    assert not service.calls


@pytest.mark.asyncio
async def test_tou_charge_uses_local_slot_and_soc():
    # 12 UTC is 13:00 local in late October => fourth TOU slot.
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    assert await controller.apply(preview(now), now, soc_pct=50, voltage_v=51) == (
        "applied"
    )
    slot = tou_entities(4)
    assert float(service.states.get(slot["soc"]).state) == 52
    assert service.states.get(slot["grid_charge"]).state == "on"
    assert service.states.get(GRID_CHARGE).state == "on"
    assert not any(
        data["entity_id"] == tou_entities(3)["soc"] for _, _, data in service.calls
    )


@pytest.mark.asyncio
async def test_tou_discharge_sets_floor_without_grid_charging():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    assert (
        await controller.apply(
            preview(now, charge=0.0, discharge=0.3, grid_a=0),
            now,
            soc_pct=80,
            voltage_v=51,
        )
        == "applied"
    )
    slot = tou_entities(4)
    assert float(service.states.get(slot["soc"]).state) == 20
    assert service.states.get(slot["grid_charge"]).state == "off"


@pytest.mark.asyncio
async def test_mismatched_window_configuration_fails_before_any_writes():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    bad = tou_entities(4)["start"]
    service.states.items[bad] = SimpleNamespace(
        state="1230", attributes={"min": 0, "max": 2359, "step": 1}
    )
    controller.arm()
    assert await controller.apply(preview(now), now, soc_pct=50, voltage_v=51) == (
        "blocked"
    )
    assert not service.calls
    assert "tou_schedule_mismatch" in controller.reason


@pytest.mark.asyncio
async def test_soc_target_rounds_up_to_entity_step_without_failure():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    target = tou_entities(4)["soc"]
    service.states.items[target] = SimpleNamespace(
        state="20", attributes={"min": 20, "max": 100, "step": 5}
    )
    controller.arm()
    assert await controller.apply(preview(now), now, soc_pct=50, voltage_v=51) == (
        "applied"
    )
    assert service.states.get(target).state == "52.0"


@pytest.mark.asyncio
async def test_soc_target_noninteger_step_is_rounded_up():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    target = tou_entities(4)["soc"]
    service.states.items[target] = SimpleNamespace(
        state="20", attributes={"min": 20, "max": 100, "step": 10}
    )
    controller.arm()
    assert await controller.apply(preview(now), now, soc_pct=50, voltage_v=51) == (
        "applied"
    )
    assert service.states.get(target).state == "52.0"


@pytest.mark.asyncio
async def test_discharge_is_not_throttled_to_forecast_household_load():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    assert (
        await controller.apply(
            preview(now, charge=0.0, discharge=0.05, grid_a=0.0),
            now,
            soc_pct=80,
            voltage_v=52.9,
        )
        == "applied"
    )


@pytest.mark.asyncio
async def test_tou_manual_override_reconciled_inside_same_quarter():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    plan = preview(now, charge=0.0, discharge=0.1, grid_a=0)
    assert await controller.apply(plan, now, soc_pct=80, voltage_v=52) == "applied"
    slot = tou_entities(4)
    service.states.items[slot["soc"]] = SimpleNamespace(
        state="90", attributes={"min": 20, "max": 100, "step": 1}
    )
    service.states.items[slot["grid_charge"]] = SimpleNamespace(
        state="on", attributes={}
    )
    count = len(service.calls)
    assert (
        await controller.apply(
            plan, now + timedelta(minutes=1), soc_pct=80, voltage_v=52
        )
        == "applied"
    )
    assert len(service.calls) > count
    assert float(service.states.get(slot["soc"]).state) == 20
    assert service.states.get(slot["grid_charge"]).state == "off"
    assert controller.observed_tou_soc == 20
    assert controller.observed_tou_grid_charge == "off"


@pytest.mark.asyncio
async def test_next_quarter_is_latched_and_applied_after_planner_rolls_forward():
    """Planner always returns a future quarter after its boundary passes."""
    now = datetime(2026, 10, 27, 20, 44, 30, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    plan = preview(now + timedelta(seconds=30), charge=0, discharge=0, grid_a=0)
    assert await controller.apply(plan, now, soc_pct=65, voltage_v=52) == (
        "waiting_for_quarter"
    )
    assert controller._pending_quarter is not None
    # At 20:45 UTC the planner already omits the started quarter.
    future = preview(
        now + timedelta(minutes=15, seconds=30), charge=0.2, discharge=0, grid_a=12
    )
    result = await controller.apply(
        future, now + timedelta(seconds=32), soc_pct=65, voltage_v=52
    )
    assert result == "applied"
    assert controller.last_plan_start == "2026-10-27T20:45:00+00:00"


@pytest.mark.asyncio
async def test_next_quarter_cache_is_refreshed_before_boundary():
    now = datetime(2026, 10, 27, 20, 40, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    target = now.replace(minute=45)
    first = preview(target, charge=0, discharge=0.1, grid_a=0)
    second = preview(target, charge=0, discharge=0, grid_a=0)
    await controller.apply(first, now, soc_pct=70, voltage_v=52)
    await controller.apply(second, now + timedelta(minutes=2), soc_pct=70, voltage_v=52)
    next_future = preview(
        target + timedelta(minutes=15), charge=0, discharge=0.2, grid_a=0
    )
    assert (
        await controller.apply(
            next_future, target + timedelta(seconds=4), soc_pct=70, voltage_v=52
        )
        == "applied"
    )


@pytest.mark.asyncio
async def test_temporary_bad_soc_blocks_but_recovers_without_rearming():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, services = setup_controller()
    controller.arm()
    plan = preview(now, charge=0.0, discharge=0.1, grid_a=0.0)
    assert await controller.apply(plan, now, soc_pct=20, voltage_v=51) == "blocked"
    assert controller.armed
    assert not controller.halted
    assert not services.calls
    assert await controller.apply(plan, now, soc_pct=50, voltage_v=51) == "applied"
    assert controller.armed
    assert services.calls


@pytest.mark.asyncio
async def test_charge_decision_explains_prices_costs_and_applied_settings():
    now = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
    controller, _ = setup_controller()
    records = []

    class Journal:
        def record(self, event, **details):
            records.append({"event": event, **details})

    controller.journal = Journal()
    controller.arm()
    plan = preview(now)
    plan.replay_snapshot["metadata"] = {"forecast_version": "forecast-v3"}
    plan.replay_snapshot["quarters"] = [
        {
            "start": plan.replay_snapshot["expected"]["quarters"][0]["start"],
            "buy_dkk_per_kwh": 1.42,
            "sell_dkk_per_kwh": 0.84,
            "pv_dc_kwh": 0.25,
            "home_ac_kwh": 0.5,
        }
    ]
    plan.replay_snapshot["expected"]["summary"] = {
        "objective_dkk": 12.5,
        "reference_objective_dkk": 18.7,
    }
    assert await controller.apply(plan, now, soc_pct=50, voltage_v=51) == "applied"
    decision = next(item for item in records if item["event"] == "decision")
    assert decision["action"] == "grid_charge"
    assert decision["reason"] == "optimizer_selected_grid_charge_for_full_horizon_cost"
    assert decision["buy_dkk_per_kwh"] == 1.42
    assert decision["reference_objective_dkk"] == 18.7
    assert decision["forecast_version"] == "forecast-v3"
    assert any(item["event"] == "applied" for item in records)


@pytest.mark.asyncio
async def test_applied_reports_real_changes_and_next_quarter_noop():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    events = []

    class Journal:
        def record(self, event, **details):
            events.append({"event": event, **details})

    controller.journal = Journal()
    controller.arm()
    first = preview(now, charge=0, discharge=0.1, grid_a=0)
    assert await controller.apply(first, now, soc_pct=70, voltage_v=51) == "applied"
    applied = [event for event in events if event["event"] == "applied"]
    assert len(applied) == 1
    assert applied[0]["commands_sent"] == len(service.calls)
    assert applied[0]["commands_sent"] >= 1
    assert any(c["entity_id"] == SOLAR_SELL for c in applied[0]["command_changes"])
    initial_calls = list(service.calls)
    later = now + timedelta(minutes=15)
    next_plan = preview(later, charge=0, discharge=0.1, grid_a=0)
    assert (
        await controller.apply(next_plan, later, soc_pct=70, voltage_v=51) == "applied"
    )
    applied = [event for event in events if event["event"] == "applied"]
    assert len(applied) == 2
    assert applied[1]["quarter_start_utc"] == later.isoformat()
    assert applied[1]["commands_sent"] == 0
    assert applied[1]["command_changes"] == []
    assert service.calls == initial_calls


@pytest.mark.asyncio
async def test_partial_write_failure_logs_confirmed_and_uncertain_commands():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller(fail_on=SOLAR_SELL)
    events = []

    class Journal:
        def record(self, event, **details):
            events.append({"event": event, **details})

    controller.journal = Journal()
    controller.arm()
    assert await controller.apply(preview(now), now, soc_pct=50, voltage_v=51) == (
        "recovering"
    )
    recovery = [event for event in events if event["event"] == "recovering"]
    assert len(recovery) == 1
    assert recovery[0]["attempted_command"]["entity_id"] == SOLAR_SELL
    assert recovery[0]["attempted_command"]["before"] == "off"
    assert recovery[0]["attempted_command"]["after"] == "on"
    assert recovery[0]["completed_commands"]
    assert controller.armed
    assert not controller.halted
    assert any(call[2]["entity_id"] == SOLAR_SELL for call in service.calls)


@pytest.mark.asyncio
async def test_persistent_tou_block_logged_at_next_quarter_not_every_poll():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    service.states.items[TIME_OF_USE].state = "off"
    events = []

    class Journal:
        def record(self, event, **details):
            events.append({"event": event, **details})

    controller.journal = Journal()
    controller.arm()
    assert (
        await controller.apply(preview(now), now, soc_pct=50, voltage_v=51) == "blocked"
    )
    assert (
        await controller.apply(
            preview(now), now + timedelta(seconds=20), soc_pct=50, voltage_v=51
        )
        == "blocked"
    )
    later = now + timedelta(minutes=15)
    assert (
        await controller.apply(preview(later), later, soc_pct=50, voltage_v=51)
        == "blocked"
    )
    blocked = [event for event in events if event["event"] == "blocked"]
    assert len(blocked) == 2
    assert blocked[0]["quarter_start_utc"] == now.isoformat()
    assert blocked[1]["quarter_start_utc"] == later.isoformat()
    assert controller.armed
    assert not service.calls


@pytest.mark.asyncio
async def test_waiting_records_next_quarter_boundary():
    now = datetime(2026, 10, 27, 12, 8, tzinfo=timezone.utc)
    target = now.replace(minute=15)
    controller, _ = setup_controller()
    events = []

    class Journal:
        def record(self, event, **details):
            events.append({"event": event, **details})

    controller.journal = Journal()
    controller.arm()
    assert (
        await controller.apply(preview(target), now, soc_pct=50, voltage_v=51)
        == "waiting_for_quarter"
    )
    waiting = [event for event in events if event["event"] == "waiting"]
    assert len(waiting) == 1
    assert waiting[0]["next_quarter_utc"] == target.isoformat()


@pytest.mark.asyncio
async def test_preserve_battery_with_tou_safeguard():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    plan = preview(now, charge=0, discharge=0, grid_a=0)
    assert await controller.apply(plan, now, soc_pct=99, voltage_v=58) == "applied"
    assert service.states.get(tou_entities(4)["soc"]).state == "99.0"
    assert service.states.get(GRID_CHARGE).state == "off"
    assert service.states.get(GRID_CURRENT).state == "12"
    assert not any(
        c[2]["entity_id"] == GRID_CURRENT and c[2].get("value") == 0
        for c in service.calls
    )


@pytest.mark.asyncio
async def test_tou_preservation_follows_pv_rising_soc_and_never_enables_grid_charge():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    plan = preview(now, charge=0, discharge=0, grid_a=0)
    await controller.apply(plan, now, soc_pct=70, voltage_v=55)
    assert float(service.states.get(tou_entities(4)["soc"]).state) == 70
    await controller.apply(plan, now + timedelta(minutes=1), soc_pct=73, voltage_v=55)
    assert float(service.states.get(tou_entities(4)["soc"]).state) == 73
    assert service.states.get(GRID_CHARGE).state == "off"


@pytest.mark.asyncio
async def test_grid_charging_only_to_grid_component_not_pv_predicted_soc():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    plan = preview(now, charge=0.1, discharge=0, grid_a=7)
    plan.replay_snapshot["expected"]["quarters"][0]["soc_end_pct"] = 96.0
    plan.replay_snapshot["plant"] = {
        "battery_capacity_dc_kwh": 10.24,
        "eta_grid_to_battery": 0.95,
    }
    assert await controller.apply(plan, now, soc_pct=70, voltage_v=58) == "applied"
    assert float(service.states.get(tou_entities(4)["soc"]).state) == 71
    assert service.states.get(GRID_CHARGE).state == "on"
    assert float(service.states.get(GRID_CURRENT).state) >= 1


@pytest.mark.asyncio
async def test_grid_disabled_retains_legal_positive_rate_not_zero():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    service.states.items[GRID_CURRENT].state = "20"
    controller.arm()
    await controller.apply(
        preview(now, charge=0, discharge=0, grid_a=0),
        now,
        soc_pct=70,
        voltage_v=52,
    )
    assert float(service.states.get(GRID_CURRENT).state) == 20
    assert not any(c[2]["entity_id"] == GRID_CURRENT for c in service.calls)
    assert service.states.get(GRID_CHARGE).state == "off"


@pytest.mark.asyncio
async def test_pv_forecast_does_not_change_global_charge_current_without_a_goal():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    plan = preview(now, charge=0, discharge=0, grid_a=0)
    plan.replay_snapshot["expected"]["quarters"][0]["pv_to_battery_dc_kwh"] = 0.12
    await controller.apply(plan, now, soc_pct=70, voltage_v=60)
    assert float(service.states.get(CHARGE_CURRENT).state) == 50
    assert not any(c[2]["entity_id"] == CHARGE_CURRENT for c in service.calls)


@pytest.mark.asyncio
async def test_solar_sell_alone_does_not_trigger_1a_throttle():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    await controller.apply(
        preview(now, charge=0, discharge=0, grid_a=0),
        now,
        soc_pct=70,
        voltage_v=60,
    )
    assert float(service.states.get(CHARGE_CURRENT).state) == 50
    assert service.states.get(SOLAR_SELL).state == "on"
    assert not any(c[2]["entity_id"] == CHARGE_CURRENT for c in service.calls)


@pytest.mark.asyncio
async def test_soc_99_without_grid_plan_disables_stale_grid_charge():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    slot = tou_entities(4)
    service.states.items[GRID_CHARGE].state = "on"
    service.states.items[slot["grid_charge"]].state = "on"
    service.states.items[slot["soc"]].state = "100"
    controller.arm()
    assert (
        await controller.apply(
            preview(now, charge=0, discharge=0, grid_a=0),
            now,
            soc_pct=99,
            voltage_v=58,
        )
        == "applied"
    )
    assert service.states.get(GRID_CHARGE).state == "off"
    assert service.states.get(slot["grid_charge"]).state == "off"
    assert service.states.get(slot["soc"]).state == "99.0"


@pytest.mark.asyncio
async def test_soc_99_suppresses_cosmetic_grid_topup():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    plan = preview(now, charge=0.10778947, discharge=0, grid_a=6.83)
    plan.replay_snapshot["plant"] = {
        "battery_capacity_dc_kwh": 10.24,
        "eta_grid_to_battery": 0.95,
    }
    plan.replay_snapshot["expected"]["quarters"][0]["soc_end_pct"] = 100.0
    assert await controller.apply(plan, now, soc_pct=99, voltage_v=57.87) == "applied"
    assert service.states.get(GRID_CHARGE).state == "off"
    assert float(service.states.get(tou_entities(4)["soc"]).state) == 99
    assert not any(c[2]["entity_id"] == GRID_CURRENT for c in service.calls)


@pytest.mark.asyncio
async def test_executor_blocks_nonrepresentable_six_tou_projection_without_writes():
    now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    plan = preview(now, charge=0.2, discharge=0, grid_a=12)
    plan.tou_feasibility = {
        "status": "not_representable",
        "reason": "invalid_grid_target",
        "hardware_execution_verified": False,
    }
    assert await controller.apply(plan, now, soc_pct=55, voltage_v=52) == "blocked"
    assert controller.reason == (
        "CommandRejected:controller:plan_not_representable_by_tou"
    )
    assert not service.calls


@pytest.mark.asyncio
async def test_live_soc_revision_releases_discharge_immediately_in_active_quarter():
    now = datetime(2026, 10, 29, 12, 5, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    before = preview(now, charge=0.0, discharge=0.0, grid_a=0.0)
    before.replay_snapshot["expected"]["quarters"][0]["start"] = now.isoformat()
    assert (
        await controller.apply(
            before, now + timedelta(seconds=1), soc_pct=83, voltage_v=52
        )
        == "applied"
    )
    slot = tou_entities(4)
    assert float(service.states.get(slot["soc"]).state) == 83.0

    # Same quarter, measured SOC is 96%, and the reoptimized decision now
    # discharges. Executor must NOT keep the old 83% protection floor.
    updated = preview(
        now + timedelta(minutes=1), charge=0.0, discharge=0.18, grid_a=0.0
    )
    updated.replay_snapshot["expected"]["quarters"][0]["start"] = (
        now + timedelta(minutes=1)
    ).isoformat()
    assert (
        await controller.apply(
            updated, now + timedelta(minutes=1, seconds=1), soc_pct=96, voltage_v=52
        )
        == "applied"
    )
    assert float(service.states.get(slot["soc"]).state) == 20.0
    assert controller.target_tou_soc == 20
    assert controller.last_plan_start == now.replace(minute=0).isoformat()


@pytest.mark.asyncio
async def test_uncertain_write_already_applied_is_reconciled_not_replayed():
    now = datetime(2026, 10, 30, 3, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    original = controller.adapter.set_number
    attempts = 0

    async def written_but_no_readback(entity, value):
        nonlocal attempts
        await original(entity, value)  # The fake device accepts the command.
        attempts += 1
        if attempts == 1:
            raise CommandRejected("device:write_unconfirmed")

    controller.adapter.set_number = written_but_no_readback
    old = preview(now, charge=0, discharge=0, grid_a=0)
    result = await controller.apply(old, now, soc_pct=78, voltage_v=53)
    assert result == "recovering"
    slot = tou_entities(2)["soc"]
    assert service.states.get(slot).state == "78.0"
    assert controller.armed

    # The next fresh plan wants discharge. Never replay the old 78% command.
    controller.adapter.set_number = original
    plan = preview(now, charge=0, discharge=0.25, grid_a=0)
    result = await controller.apply(
        plan, now + timedelta(seconds=31), soc_pct=75, voltage_v=53
    )
    assert result == "applied"
    assert service.states.get(slot).state == "20.0"
    assert any(
        data["entity_id"] == slot and data.get("value") == 20.0
        for _, _, data in service.calls
    )


@pytest.mark.asyncio
async def test_recovery_backoff_is_bounded_and_stop_cancels_retries():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller(fail_on=GRID_CHARGE)
    controller.arm()
    plan = preview(now)
    result = await controller.apply(plan, now, soc_pct=50, voltage_v=51)
    assert result == "recovering"
    result = await controller.apply(
        plan, now + timedelta(seconds=31), soc_pct=50, voltage_v=51
    )
    assert result == "recovering"
    assert controller.recovery_attempts == 2
    count = len(service.calls)
    result = await controller.apply(
        plan, now + timedelta(seconds=60), soc_pct=50, voltage_v=51
    )
    assert result == "recovering"
    assert len(service.calls) == count
    controller.stop(manual=True)
    service.fail_on = None
    result = await controller.apply(
        plan, now + timedelta(minutes=5), soc_pct=50, voltage_v=51
    )
    assert result == "stopped"
    assert not controller.armed
    assert controller.recovery_next_at is None


@pytest.mark.asyncio
async def test_preserve_soc_does_not_write_for_sub_two_percent_fluctuations():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    plan = preview(now, charge=0, discharge=0, grid_a=0)
    result = await controller.apply(plan, now, soc_pct=70, voltage_v=53)
    assert result == "applied"
    target = tou_entities(4)["soc"]
    count = len(service.calls)
    for minute, soc in [(1, 69.8), (2, 70.4), (3, 71.1)]:
        result = await controller.apply(
            plan, now + timedelta(minutes=minute), soc_pct=soc, voltage_v=53
        )
        assert result == "applied"
    assert float(service.states.get(target).state) == 70
    assert len(service.calls) == count
    result = await controller.apply(
        plan, now + timedelta(minutes=4), soc_pct=72.3, voltage_v=53
    )
    assert result == "applied"
    assert float(service.states.get(target).state) == 73


@pytest.mark.asyncio
async def test_manual_stop_during_inflight_confirmation_never_resumes_or_writes_more():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    controller, service = setup_controller()
    controller.arm()
    original = service.async_call

    async def stop_after_first_command(domain, action, data, blocking=False):
        await original(domain, action, data, blocking)
        controller.stop(manual=True)

    service.async_call = stop_after_first_command
    result = await controller.apply(preview(now), now, soc_pct=70, voltage_v=53)
    assert result == "stopped"
    assert not controller.armed
    assert controller.recovery_next_at is None
    assert len(service.calls) == 1
