"""Regression coverage for persistent, bounded audit evidence."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from custom_components.energy_copilot.decision_journal import (
    MAX_EVENTS,
    RETENTION_DAYS,
    DecisionJournal,
)


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
    journal.record("planned", reason="optimizer_selected_grid_import_preserving_battery",
                   action="grid_import",
                   quarter_start_utc="2026-10-28T07:00:00+00:00",
                   soc_observed_pct=52, soc_planned_end_pct=52,
                   buy_dkk_per_kwh=2.728, sell_dkk_per_kwh=2.244,
                   pv_forecast_dc_kwh=0.081, home_forecast_ac_kwh=0.1657,
                   planned_grid_import_kwh=0.0888)
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0]["name"] == "Energy Co-Pilot"
    assert "2,73 DKK/kWh" in events[0]["message"]
    assert "09:00" in events[0]["message"]
    assert "Uzasadnienie" in events[0]["message"]
    assert "optimizer_selected_" not in events[0]["message"]
    await journal.async_close()


@pytest.mark.asyncio
async def test_activity_blocked_and_recovered_are_visible(hass):
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    journal = DecisionJournal(hass, "human-recovery")
    await journal.async_load()
    journal.record("blocked", reason="controller:input_or_plan_unavailable",
                   missing_measurements=["soc"], issue_codes=["invalid_input"])
    journal.record("recovered", reason="fresh_valid_measurements_and_plan")
    await hass.async_block_till_done()
    assert len(events) == 2
    assert "Brak pomiarów: soc" in events[0]["message"]
    assert "ARM pozostaje aktywny" in events[0]["message"]
    assert "Wznowiono" in events[1]["message"]
    await journal.async_close()


@pytest.mark.asyncio
async def test_applied_does_not_claim_physical_confirmation(hass):
    events = []
    hass.bus.async_listen("logbook_entry", lambda event: events.append(event.data))
    journal = DecisionJournal(hass, "human-apply")
    await journal.async_load()
    journal.record("applied", quarter_start_utc="2026-10-28T07:00:00+00:00",
                   grid_limit_a=25, discharge_limit_a=0,
                   target_tou_soc=60, target_tou_grid_charge=True)
    await hass.async_block_till_done()
    assert "25 A" in events[0]["message"]
    assert "nie potwierdza jeszcze rzeczywistego przepływu" in events[0]["message"]
    await journal.async_close()
