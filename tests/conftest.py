"""Native HA fixtures. Tests cannot reach external networks or an inverter."""

from datetime import UTC, datetime

import pytest
from homeassistant.core import State
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_copilot.const import DEFAULT_ENTITIES, DOMAIN, POWER_ROLES

NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def settings():
    return {
        **DEFAULT_ENTITIES,
        "mode": "monitor",
        "solar_sell": "switch.sun12k_solar_sell",
    }


def make_state(role, value=None, at=NOW, unit=None):
    values = {
        "pv": 3034,
        "pv1": 2387,
        "pv2": 647,
        "grid": 1200,
        "grid_alternative": 1200,
        "battery": 1000,
        "home": 5234,
        "voltage": 50,
        "current": 20,
        "soc": 50,
        "daily_pv": 10,
        "daily_charge": 2,
        "daily_discharge": 1,
    }
    units = {
        "voltage": "V",
        "current": "A",
        "soc": "%",
        "daily_pv": "kWh",
        "daily_charge": "kWh",
        "daily_discharge": "kWh",
    }
    attrs = {
        "unit_of_measurement": unit
        or ("W" if role in POWER_ROLES else units.get(role, "DKK/kWh"))
    }
    if role in {"buy", "sell"}:
        attrs.update(
            raw_today=[{"hour": NOW.isoformat(), "price": 0.4}],
            raw_tomorrow=[],
            tomorrow_valid=False,
            current_price=0.4,
        )
    return State(
        DEFAULT_ENTITIES[role],
        str(values.get(role, 0.4) if value is None else value),
        attrs,
        last_updated=at,
        last_changed=at,
        last_reported=at,
    )


@pytest.fixture
def source_states():
    return {r: make_state(r) for r in DEFAULT_ENTITIES}


@pytest.fixture
def populated_hass(hass, source_states, freezer):
    freezer.move_to(NOW)
    for state in source_states.values():
        hass.states.async_set(state.entity_id, state.state, dict(state.attributes))
    hass.states.async_set("switch.sun12k_solar_sell", "off")
    return hass


@pytest.fixture
def entry(hass, settings):
    entry = MockConfigEntry(domain=DOMAIN, data=settings, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    return entry
