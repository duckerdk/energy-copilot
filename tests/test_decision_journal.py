"""Regression coverage for persistent, bounded audit evidence."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from custom_components.energy_copilot.decision_journal import (
    DecisionJournal,
    MAX_EVENTS,
    RETENTION_DAYS,
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
