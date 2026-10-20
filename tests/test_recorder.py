from datetime import timedelta
from unittest.mock import patch

import pytest

from .conftest import NOW


@pytest.fixture
def mock_recorder_before_hass(recorder_db_url):
    """Configure Recorder database before the HA fixture initializes."""


async def test_real_recorder_query(
    recorder_db_url, hass, populated_hass, entry, freezer, async_setup_recorder_instance
):
    """Exercise the adapter against HA's real in-memory Recorder and history API."""
    from pytest_homeassistant_custom_component.components.recorder.common import (
        async_wait_recording_done,
    )

    from custom_components.energy_copilot.const import HISTORY_ROLES

    from .conftest import make_state

    freezer.move_to(NOW - timedelta(minutes=15))
    await async_setup_recorder_instance(hass)
    await hass.async_start()
    for minute in range(16):
        freezer.move_to(NOW - timedelta(minutes=15 - minute))
        for role in HISTORY_ROLES:
            state = make_state(role)
            hass.states.async_set(
                state.entity_id, state.state, {**state.attributes, "sequence": minute}
            )
        await hass.async_block_till_done()
        await async_wait_recording_done(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    data = entry.runtime_data.coordinator.data
    assert len(data.history) == 96
    last = data.history[-1]
    assert last.end == NOW
    assert last.home_kwh == pytest.approx(5.234 / 4)
    assert not last.issues
    # The other 23h45m are explicitly missing, not manufactured training zeros.
    assert all(s.home_kwh is None for s in data.history[:-1])
    assert "historical_quality_unverifiable" in {i.code for i in data.issues}


async def test_recorder_database_failure_is_diagnostic(
    recorder_db_url, hass, populated_hass, entry, async_setup_recorder_instance
):
    from sqlalchemy.exc import SQLAlchemyError

    await async_setup_recorder_instance(hass)
    with patch(
        "homeassistant.components.recorder.history.get_significant_states",
        side_effect=SQLAlchemyError("test"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert "recorder_query_failed" in {
        i.code for i in entry.runtime_data.coordinator.data.issues
    }
