"""Regression coverage for persistent, bounded audit evidence."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.energy_copilot.decision_journal import (
    MAX_EVENTS,
    RETENTION_DAYS,
    DecisionJournal,
    readable_event,
)
from custom_components.energy_copilot.dynamic_controller import DynamicDeyeController
from custom_components.energy_copilot.sensor import DecisionJournalSensor


@pytest.mark.asyncio
async def test_decisions_survive_restart_and_keep_explanations(hass):
    first = DecisionJournal(hass, "audit-regression")
    await first.async_load()
    first.record(
        "decision",
        reason="optimizer_selected_grid_charge_for_full_horizon_cost",
        action="grid_charge",
        buy_dkk_per_kwh=1.23,
        soc_observed_pct=51,
        quarter_start_utc="2026-10-28T00:00:00+00:00",
    )
    await first.async_close()
    restored = DecisionJournal(hass, "audit-regression")
    await restored.async_load()
    assert len(restored.entries) == 1
    assert restored.entries[0]["action"] == "grid_charge"
    assert restored.entries[0]["buy_dkk_per_kwh"] == 1.23
    assert restored.entries[0]["decision_id"]
    assert restored.summary["retention_days"] == 30


@pytest.mark.asyncio
async def test_old_events_are_removed_without_losing_recent_history(hass):
    journal = DecisionJournal(hass, "audit-retention")
    await journal.async_load()
    now = datetime(2026, 10, 28, tzinfo=timezone.utc)
    journal.entries = [
        {
            "event": "old",
            "time_utc": (now - timedelta(days=RETENTION_DAYS + 1)).isoformat(),
        },
        {"event": "new", "time_utc": now.isoformat()},
    ]
    with patch(
        "custom_components.energy_copilot.decision_journal.dt_util.utcnow",
        return_value=now,
    ):
        journal._trim()
        assert [item["event"] for item in journal.entries] == ["new"]
        journal.entries = [journal.entries[0]] * (MAX_EVENTS + 1)
        journal._trim()
        assert len(journal.entries) == MAX_EVENTS


@pytest.mark.asyncio
async def test_activity_event_is_human_readable_and_explains_plan(hass):
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    journal = DecisionJournal(hass, "human-ui")
    await journal.async_load()
    journal.record(
        "planned",
        reason="optimizer_selected_grid_import_preserving_battery",
        action="grid_import",
        quarter_start_utc="2026-10-28T07:00:00+00:00",
        soc_observed_pct=52,
        soc_planned_end_pct=52,
        buy_dkk_per_kwh=2.728,
        sell_dkk_per_kwh=2.244,
        pv_forecast_dc_kwh=0.081,
        home_forecast_ac_kwh=0.1657,
        planned_grid_import_kwh=0.0888,
    )
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0]["name"] == "Energy Co-Pilot"
    assert events[0]["domain"] == "energy_copilot"
    assert events[0]["entity_id"] == "sensor.energy_co_pilot_decision_journal"
    assert "2,73 DKK/kWh" in events[0]["message"]
    assert "08:00" in events[0]["message"]
    assert "Uzasadnienie:" in events[0]["message"]
    assert "optimizer_selected_" not in events[0]["message"]
    await journal.async_close()


@pytest.mark.asyncio
async def test_activity_blocked_and_recovered_are_visible(hass):
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    journal = DecisionJournal(hass, "human-recovery")
    await journal.async_load()
    journal.record(
        "blocked",
        reason="controller:input_or_plan_unavailable",
        missing_measurements=["soc"],
        issue_codes=["invalid_input"],
    )
    journal.record("recovered", reason="fresh_valid_measurements_and_plan")
    await hass.async_block_till_done()
    assert len(events) == 2
    assert "brak pomiarów: soc" in events[0]["message"]
    assert "ARM zachowany" in events[0]["message"]
    assert "Wznowiono" in events[1]["message"]
    await journal.async_close()


@pytest.mark.asyncio
async def test_applied_does_not_claim_physical_confirmation(hass):
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    journal = DecisionJournal(hass, "human-apply")
    await journal.async_load()
    journal.record(
        "applied",
        quarter_start_utc="2026-10-28T07:00:00+00:00",
        grid_limit_a=25,
        discharge_limit_a=0,
        target_tou_soc=60,
        target_tou_grid_charge=True,
        observed_tou_grid_charge="on",
        commands_sent=1,
        command_changes=[
            {
                "entity_id": "number.sun12k_maximum_battery_grid_charge_current",
                "before": "0",
                "after": 25,
            }
        ],
    )
    await hass.async_block_till_done()
    assert "25 A" in events[0]["message"]
    assert "Limit ładowania z sieci 0 A → 25 A" in events[0]["message"]
    assert "potwierdzone odczytem" in events[0]["message"]
    assert "przepływu energii" not in events[0]["message"]
    await journal.async_close()


def test_grid_import_has_evidence_not_tautological_justification():
    message = readable_event(
        {
            "event": "planned",
            "reason": "optimizer_selected_grid_import_preserving_battery",
            "action": "grid_import",
            "quarter_start_utc": "2026-10-28T07:00:00+00:00",
            "soc_observed_pct": 52,
            "soc_planned_end_pct": 52,
            "buy_dkk_per_kwh": 2.728,
            "sell_dkk_per_kwh": 2.244,
            "planned_grid_import_kwh": 0.0888,
            "later_discharge_start_utc": "2026-10-28T07:45:00+00:00",
            "later_discharge_buy_dkk_per_kwh": 2.728,
        }
    )
    assert "08:00" in message
    assert "08:45" in message
    assert "0,09 kWh AC" in message
    assert "Cena późniejszego rozładowania jest taka sama" in message
    assert "Brak obliczonego kosztu wariantu" in message
    assert "minimalizując modelowany koszt" not in message


def test_discharge_explains_avoided_purchase_and_degradation():
    message = readable_event(
        {
            "event": "decision",
            "action": "battery_discharge",
            "quarter_start_utc": "2026-10-28T07:45:00+00:00",
            "soc_observed_pct": 52,
            "soc_planned_end_pct": 51,
            "buy_dkk_per_kwh": 3.0,
            "battery_discharge_dc_kwh": 0.2,
            "battery_to_ac_efficiency": 0.95,
            "degradation_cost_dkk": 0.08,
        }
    )
    assert "0,20 kWh DC" in message
    assert "0,19 kWh AC" in message
    assert "0,57 DKK" in message
    assert "0,08 DKK" in message
    assert "0,49 DKK" in message
    assert "minimalizując modelowany koszt" not in message


def test_charge_with_future_discharge_shows_price_comparison():
    message = readable_event(
        {
            "event": "planned",
            "action": "grid_charge",
            "quarter_start_utc": "2026-10-28T07:00:00+00:00",
            "buy_dkk_per_kwh": 1.0,
            "grid_charge_ac_kwh": 0.5,
            "later_discharge_start_utc": "2026-10-28T16:00:00+00:00",
            "later_discharge_buy_dkk_per_kwh": 3.5,
        }
    )
    assert "2,50 DKK/kWh" in message
    assert "17:00" in message
    assert "przed stratami i degradacją" in message


def test_blocked_event_shows_real_planner_reason_not_historical_noise():
    message = readable_event(
        {
            "event": "blocked",
            "reason": "controller:input_or_plan_unavailable",
            "quality": "valid",
            "planning_status": "blocked",
            "planning_reason": "price:published_gap",
            "issue_codes": [
                "home_profile_unverified",
                "historical_quality_unverifiable",
            ],
            "categorized_issues": [
                {
                    "code": "historical_quality_unverifiable",
                    "category": "historical",
                }
            ],
        }
    )
    assert "Luka w opublikowanych cenach" in message
    assert "niepotwierdzona jakość danych historycznych" not in message


def test_decision_selects_future_discharge_from_actual_plan(hass):
    controller = DynamicDeyeController(hass)
    at = "2026-10-28T07:00:00+00:00"
    later = "2026-10-28T07:45:00+00:00"
    current = {
        "start": at,
        "grid_to_battery_ac_kwh": 0.0,
        "battery_to_home_dc_kwh": 0.0,
        "pv_to_battery_dc_kwh": 0.0,
        "grid_import_kwh": 0.0888,
        "soc_end_pct": 52.0,
        "grid_charge_current_a": 0.0,
    }
    future = {
        "start": later,
        "grid_to_battery_ac_kwh": 0.0,
        "battery_to_home_dc_kwh": 0.065,
    }
    preview = SimpleNamespace(
        replay_snapshot={
            "metadata": {"forecast_version": "version1"},
            "plant": {"eta_battery_to_ac": 0.95},
            "quarters": [
                {"start": at, "buy_dkk_per_kwh": 2.728},
                {"start": later, "buy_dkk_per_kwh": 2.728},
            ],
            "expected": {"quarters": [current, future], "summary": {}},
        }
    )
    decision = controller._decision(
        preview, current, datetime(2026, 10, 28, 7, tzinfo=timezone.utc), 52
    )
    assert decision["later_discharge_start_utc"] == later
    assert decision["later_discharge_buy_dkk_per_kwh"] == 2.728
    assert decision["battery_to_ac_efficiency"] == 0.95


def test_journal_sensor_does_not_create_state_change_activity(hass):
    journal = DecisionJournal(hass, "no-fake-activity")
    coordinator = SimpleNamespace(decision_journal=journal)
    sensor = SimpleNamespace(coordinator=coordinator)
    assert DecisionJournalSensor.native_value.fget(sensor) == "ready"
    journal.entries = [{"event": "blocked", "time_utc": "2026-10-28T07:00:00+00:00"}]
    assert DecisionJournalSensor.native_value.fget(sensor) == "ready"
    journal.available = False
    assert DecisionJournalSensor.native_value.fget(sensor) == "unavailable"


@pytest.mark.asyncio
async def test_activity_uses_custom_entity_registry_id(hass):
    registry = er.async_get(hass)
    record = registry.async_get_or_create(
        "sensor",
        "energy_copilot",
        "renamed-activity_decision_journal",
        suggested_object_id="copilot_custom_audit",
    )
    journal = DecisionJournal(hass, "renamed-activity")
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    await journal.async_load()
    journal.record("armed", reason="automatic_mode_or_user_arm")
    await hass.async_block_till_done()
    assert events[0]["entity_id"] == record.entity_id
    await journal.async_close()


@pytest.mark.asyncio
async def test_activity_planner_state_transition_explains_block(hass):
    journal = DecisionJournal(hass, "plan-transition")
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    await journal.async_load()
    journal.record(
        "plan_status",
        planning_status="blocked",
        previous_planning_status="preview",
        reason="price:published_gap",
    )
    journal.record(
        "blocked",
        reason="controller:input_or_plan_unavailable",
        quarter_start_utc="2026-10-28T08:00:00+00:00",
        planning_status="blocked",
        planning_reason="price:published_gap",
        quality="valid",
        categorized_issues=[
            {
                "code": "historical_quality_unverifiable",
                "source": "recorder",
                "category": "historical",
            },
        ],
    )
    await hass.async_block_till_done()
    assert len(events) == 2
    assert "preview → blocked" in events[0]["message"]
    assert "Luka w opublikowanych cenach" in events[0]["message"]
    assert "planer: Luka w opublikowanych cenach" in events[1]["message"]
    assert "historycznych" not in events[1]["message"]
    await journal.async_close()


@pytest.mark.asyncio
async def test_activity_same_settings_reports_no_commands(hass):
    journal = DecisionJournal(hass, "noop-apply")
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    await journal.async_load()
    journal.record(
        "applied",
        quarter_start_utc="2026-10-28T08:15:00+00:00",
        commands_sent=0,
        command_changes=[],
        observed_tou_soc=20,
        grid_limit_a=0,
        discharge_limit_a=100,
        observed_tou_grid_charge="off",
        active_tou_slot=3,
    )
    await hass.async_block_till_done()
    msg = events[0]["message"]
    assert "09:15" in msg
    assert "nie wysłano poleceń" in msg
    assert "TOU 3" in msg
    assert "wysłane i odczytane" not in msg
    assert "przepływu energii" not in msg
    await journal.async_close()


@pytest.mark.asyncio
async def test_activity_failed_write_has_requested_setting_and_safety_state(hass):
    journal = DecisionJournal(hass, "write-failure")
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    await journal.async_load()
    journal.record(
        "halted",
        reason="CommandRejected:device:write_unconfirmed",
        phase="device_write_result_uncertain",
        attempted_command={
            "entity_id": "number.sun12k_maximum_battery_discharge_current",
            "before": "0",
            "after": 100,
        },
        completed_commands=[
            {"entity_id": "switch.sun12k_grid_charge", "before": "on", "after": "off"},
        ],
    )
    await hass.async_block_till_done()
    msg = events[0]["message"]
    assert "Falownik nie potwierdził zmiany nastawy" in msg
    assert "Limit rozładowania 0 A → 100 A" in msg
    assert "Wcześniejsze potwierdzone zmiany: 1" in msg
    assert "ARM wyłączony" in msg
    await journal.async_close()


@pytest.mark.asyncio
async def test_same_valid_quality_with_only_historical_issue_does_not_spam_activity(
    hass,
):
    journal = DecisionJournal(hass, "valid-history")
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    await journal.async_load()
    journal.record(
        "input_quality",
        previous_quality="valid",
        quality="valid",
        categorized_issues=[
            {"code": "home_profile_unverified", "category": "historical"}
        ],
    )
    await hass.async_block_till_done()
    assert not events
    assert journal.entries[-1]["event"] == "input_quality"
    await journal.async_close()


def test_pv_economic_reason_gives_conclusion_without_repeating_input_values():
    message = readable_event(
        {
            "event": "planned",
            "action": "pv_charge",
            "quarter_start_utc": "2026-10-28T10:00:00+00:00",
            "soc_observed_pct": 73.0,
            "soc_planned_end_pct": 74.1,
            "buy_dkk_per_kwh": 2.27,
            "sell_dkk_per_kwh": 1.79,
            "pv_forecast_dc_kwh": 0.31,
            "home_forecast_ac_kwh": 0.18,
            "pv_charge_dc_kwh": 0.12,
            "economic_comparison_status": "evaluated",
            "economic_saving_dkk": 0.073,
            "economic_alternative_first_sale_dkk": 0.198,
            "economic_selected_first_sale_dkk": 0.0,
            "pv_export_enabled": True,
        }
    )
    assert "Uzasadnienie: Ta akcja obniża koszt całego planu o 0,073 DKK" in message
    assert "najlepszego wariantu bez magazynowania PV teraz" in message
    assert "dodatkowo 0,198 DKK" in message
    assert "Dane kwadransa" not in message
    assert "Koszt zakupu w kwadransie: 0,00" not in message


def test_same_quarter_revision_is_delta_not_duplicate_plan():
    previous = {
        "quarter_start_utc": "2026-10-28T10:00:00+00:00",
        "action": "pv_charge",
        "pv_forecast_dc_kwh": 0.30,
        "home_forecast_ac_kwh": 0.18,
        "pv_charge_dc_kwh": 0.11,
        "soc_planned_end_pct": 74.0,
        "buy_dkk_per_kwh": 2.27,
        "sell_dkk_per_kwh": 1.79,
    }
    message = readable_event(
        {
            **previous,
            "event": "revised",
            "previous_plan": previous,
            "pv_forecast_dc_kwh": 0.31,
            "pv_charge_dc_kwh": 0.12,
            "soc_planned_end_pct": 74.1,
        }
    )
    assert message.startswith("Korekta planu na 11:00:")
    assert "PV 0,30 kWh → 0,31 kWh" in message
    assert "ładowanie PV 0,11 kWh → 0,12 kWh" in message
    assert "SOC końcowy 74,0 % → 74,1 %" in message
    assert "(po aktualizacji danych)" in message
    assert "Sprzedaż:" not in message
    assert "Uzasadnienie:" not in message


def test_change_of_action_in_revision_includes_new_compared_cost():
    previous = {
        "action": "grid_import",
        "quarter_start_utc": "2026-10-28T10:00:00+00:00",
    }
    message = readable_event(
        {
            "event": "revised",
            "quarter_start_utc": previous["quarter_start_utc"],
            "action": "pv_charge",
            "previous_plan": previous,
            "economic_comparison_status": "evaluated",
            "economic_saving_dkk": 0.041,
        }
    )
    assert "akcja zasilanie domu z sieci" in message
    assert "ładowanie baterii z instalacji PV" in message
    assert "0,041 DKK" in message


def test_equal_cost_comparison_does_not_claim_unproved_benefit():
    message = readable_event(
        {
            "event": "planned",
            "action": "pv_charge",
            "quarter_start_utc": "2026-10-28T10:00:00+00:00",
            "economic_comparison_status": "evaluated",
            "economic_saving_dkk": 0.0,
        }
    )
    assert "praktycznie taki sam koszt" in message
    assert "nie wykazuje istotnej przewagi" in message


def test_audit_timeout_never_invents_economic_reason():
    message = readable_event(
        {
            "event": "planned",
            "action": "pv_charge",
            "economic_comparison_status": "unavailable",
        }
    )
    assert "Brak policzonego porównania" in message
    assert "obniża koszt" not in message



def test_sub_cent_grid_charge_benefit_is_logged_as_immaterial():
    message = readable_event(
        {
            "event": "planned",
            "action": "grid_import",
            "quarter_start_utc": "2026-10-28T12:45:00+00:00",
            "soc_observed_pct": 98.5,
            "economic_policy_reason": "grid_charge_below_materiality_threshold",
            "economic_policy_benefit_dkk": 0.0096,
        }
    )
    assert "poniżej 0,01 DKK (pomijalna)" in message
    assert "progu 0,10 DKK" in message


def test_soc99_grid_charge_rejection_is_explicit_in_plan():
    message = readable_event(
        {
            "event": "planned",
            "action": "grid_import",
            "soc_observed_pct": 99,
            "quarter_start_utc": "2026-10-28T12:45:00+00:00",
            "economic_policy_reason": "soc_99_satisfies_grid_charge_target",
        }
    )
    assert "SOC 99% uznano za osiągnięty cel 100%" in message


def test_charge_current_change_explains_why_not_just_values():
    message = readable_event(
        {
            "event": "applied",
            "commands_sent": 1,
            "command_changes": [
                {
                    "entity_id": "number.sun12k_maximum_battery_charge_current",
                    "before": "50",
                    "after": 1,
                }
            ],
            "charging_current_policy": "defer_pv_storage_for_export_then_charge_later",
        }
    )
    assert "eksport teraz, magazynowanie później" in message
