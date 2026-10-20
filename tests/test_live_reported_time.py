"""Python HA report times are distinct from frontend last_updated exports."""

from datetime import timedelta

from homeassistant.core import State

from custom_components.energy_copilot.const import HISTORY_ROLES
from custom_components.energy_copilot.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.energy_copilot.validation import measurements

from .conftest import NOW, make_state


def test_old_change_time_with_current_python_report_is_not_artificially_stale():
    states = {}
    for role in HISTORY_ROLES:
        original = make_state(role)
        changed = NOW - timedelta(seconds=15.144) if role == "pv" else NOW
        states[role] = State(
            original.entity_id,
            original.state,
            original.attributes,
            last_updated=changed,
            last_changed=changed,
            last_reported=NOW,
        )
    values, _, issues = measurements(states, NOW)
    assert "home" in values
    assert not issues
    assert all(sample.at == NOW for sample in values.values())


async def test_unchanged_backend_state_re_reports_without_value_change(
    hass, populated_hass, entry, freezer
):
    initial = hass.states.get(entry.data["pv"])
    changed_at = initial.last_updated
    freezer.tick(timedelta(seconds=20))
    for role in HISTORY_ROLES:
        previous = hass.states.get(entry.data[role])
        hass.states.async_set(
            previous.entity_id, previous.state, dict(previous.attributes)
        )
    assert hass.states.get(entry.data["pv"]).last_updated == changed_at
    assert hass.states.get(entry.data["pv"]).last_reported == NOW + timedelta(
        seconds=20
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    diag = await async_get_config_entry_diagnostics(hass, entry)
    timing = diag["observed"]["measurement_source_timing"]["pv"]
    assert timing["last_updated_utc"] == changed_at.isoformat()
    assert timing["last_reported_utc"] == (NOW + timedelta(seconds=20)).isoformat()
    assert timing["freshness_time_basis"] == "last_reported"
    assert timing["report_age_seconds"] == 0
    assert "home" in diag["observed"]["measurement_roles"]
    assert not any(i["code"] == "snapshot_not_synchronous" for i in diag["issues"])
