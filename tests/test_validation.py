from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from homeassistant.core import State

from custom_components.energy_copilot.const import DEFAULT_ENTITIES, HISTORY_ROLES
from custom_components.energy_copilot.recorder_reconstruction import RecordingRun
from custom_components.energy_copilot.validation import (
    forecast,
    history_slots,
    measurement,
    measurements,
    number,
    prices,
    utc,
)

from .conftest import NOW, make_state


def codes(issues):
    return {i.code for i in issues}


@pytest.mark.parametrize("value", [True, False, "nan", "inf", "-inf", "unknown", None])
def test_nonfinite_is_not_zero(value):
    with pytest.raises((ValueError, TypeError)):
        number(value)


@pytest.mark.parametrize(
    "role,value,unit,code",
    [
        ("pv", "unavailable", "W", "invalid_input"),
        ("grid", 1, "kWh", "invalid_unit"),
        ("battery", "nan", "W", "invalid_input"),
        ("soc", 101, "%", "invalid_input"),
        ("pv", -1, "W", "invalid_input"),
    ],
)
def test_measurement_validation(role, value, unit, code):
    with pytest.raises(ValueError, match=code):
        measurement(role, make_state(role, value, unit=unit), NOW)


@pytest.mark.parametrize("age", [timedelta(minutes=6), -timedelta(seconds=11)])
def test_stale_or_future(age):
    with pytest.raises(ValueError, match="stale_input"):
        measurement("pv", make_state("pv", at=NOW - age), NOW)


@pytest.mark.parametrize(
    "grid,battery,expected",
    [
        (
            1200,
            1000,
            {
                "grid_import": 1.2,
                "grid_export": 0,
                "battery_charge": 0,
                "battery_discharge": 1,
            },
        ),
        (
            -2470,
            -1000,
            {
                "grid_import": 0,
                "grid_export": 2.47,
                "battery_charge": 1,
                "battery_discharge": 0,
            },
        ),
    ],
)
def test_flow_signs_and_no_double_counting(source_states, grid, battery, expected):
    source_states["grid"] = make_state("grid", grid)
    source_states["battery"] = make_state("battery", battery)
    _, flows, _ = measurements(source_states, NOW)
    assert flows == {**expected, "pv_dc": 3.034}


def test_masked_zero_is_invalid(source_states):
    source_states["pv"] = make_state("pv", "unavailable")
    source_states["home"] = make_state("home", 2200)
    values, _, issues = measurements(source_states, NOW)
    assert "home" not in values
    assert "invalid_input" in codes(issues)


def test_snapshot_skew(source_states):
    source_states["grid"] = make_state("grid", at=NOW - timedelta(seconds=20))
    values, _, issues = measurements(source_states, NOW)
    assert "snapshot_not_synchronous" in codes(issues)
    assert "home" not in values


def test_physical_consistency_is_not_inferred(source_states):
    source_states["voltage"] = make_state("voltage", 56)
    source_states["current"] = make_state("current", 100)
    source_states["soc"] = make_state("soc", 19)
    source_states["pv1"] = make_state("pv1", 1)
    _, _, issues = measurements(source_states, NOW)
    assert codes(issues) >= {
        "battery_power_inconsistent",
        "pv_sum_inconsistent",
        "below_policy_minimum",
    }


def price_state(records, *, tomorrow=None, valid=False, current=0.4, unit="DKK/kWh"):
    return State(
        "sensor.price",
        ".4",
        {
            "unit_of_measurement": unit,
            "raw_today": records,
            "raw_tomorrow": tomorrow or [],
            "tomorrow_valid": valid,
            "current_price": current,
        },
    )


@pytest.mark.parametrize("day,hours", [("2026-03-29", 23), ("2026-10-25", 25)])
def test_published_dst_horizon(day, hours):
    zone = ZoneInfo("Europe/Copenhagen")
    start = utc(datetime.fromisoformat(day).replace(tzinfo=zone))
    records = [
        {
            "hour": (start + timedelta(hours=n)).astimezone(zone).isoformat(),
            "price": -0.2 + n / 100,
        }
        for n in range(hours)
    ]
    state = price_state(records, current=-0.2)
    slots, issues = prices(state, state, start)
    assert len(slots) == hours
    assert len({s.start for s in slots}) == hours
    assert all(s.end - s.start == timedelta(hours=1) for s in slots)
    assert not issues
    assert slots[0].buy == -0.2  # No tax, fee or tariff transformation.


def test_tomorrow_not_published_and_threshold_ambiguity():
    today = [{"hour": NOW.isoformat(), "price": 0.400}]
    tomorrow = [{"hour": (NOW + timedelta(days=1)).isoformat(), "price": 99}]
    state = price_state(today, tomorrow=tomorrow, current=0.3996)
    slots, issues = prices(state, state, NOW)
    assert len(slots) == 1
    assert "PRICE_THRESHOLD_AMBIGUOUS" in codes(issues)


@pytest.mark.parametrize("price", [0.399, 0.400, 0.401])
def test_threshold_without_artificial_hysteresis(price):
    state = price_state([{"hour": NOW.isoformat(), "price": price}], current=price)
    slots, issues = prices(state, state, NOW)
    assert slots[0].sell == price
    assert "PRICE_THRESHOLD_AMBIGUOUS" not in codes(issues)


def test_duplicate_invalid_and_mismatched_prices():
    records = [{"hour": NOW.isoformat(), "price": 0.4}] * 2
    records += [
        {"hour": "2026-10-20T12:00:00", "price": 0.4},
        {"hour": "nonsense", "price": "nan"},
    ]
    buy = price_state(records)
    sell = price_state([{"hour": NOW.isoformat(), "price": 0.4}])
    slots, issues = prices(buy, sell, NOW)
    assert not slots
    assert codes(issues) >= {
        "duplicate_price",
        "invalid_price_slot",
        "price_horizon_mismatch",
        "empty_prices",
    }


def test_price_units_gaps_stale_and_tomorrow():
    records = [
        {"hour": (NOW + timedelta(hours=h)).isoformat(), "price": 0.4} for h in (0, 2)
    ]
    records.append({"hour": (NOW - timedelta(days=1)).isoformat(), "price": 0.4})
    state = price_state(
        records,
        tomorrow=[{"hour": (NOW + timedelta(days=1)).isoformat(), "price": 0.4}],
        valid=True,
    )
    slots, issues = prices(state, state, NOW)
    assert len(slots) == 3
    assert codes(issues) >= {"price_gap", "invalid_price_slot"}
    assert not prices(price_state(records, unit="EUR/MWh"), None, NOW)[0]


def forecast_response():
    keys = [(NOW + timedelta(hours=n)).isoformat() for n in range(3)]
    return {
        "watts": dict.fromkeys(keys, 500),
        "wh_period": {keys[0]: 1000, keys[1]: 500, keys[2]: 0},
    }


def test_forecast_wh_start_intervals_and_version():
    snapshot = forecast(forecast_response(), NOW)
    assert snapshot.periods[0].start == NOW
    assert snapshot.periods[0].end == NOW + timedelta(hours=1)
    assert snapshot.periods[0].kwh == 1
    assert snapshot.periods[1].kwh == 0.5
    assert snapshot.captured_at == NOW
    assert (
        snapshot.version
        != forecast(forecast_response(), NOW - timedelta(seconds=1)).version
    )


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {"daily_total": 1000},
        {"wh_period": {"naive": 1}},
        {"watts": {}, "wh_period": {NOW.isoformat(): -1}},
    ],
)
def test_forecast_never_invents_daily_intervals(response):
    with pytest.raises((ValueError, TypeError)):
        forecast(response, NOW)


def history_rows(*, corrupt=False, missing=False, sparse=False):
    result = {}
    for role in HISTORY_ROLES:
        times = [0] if sparse else range(16)
        result[DEFAULT_ENTITIES[role]] = [
            make_state(role, at=NOW + timedelta(minutes=n)) for n in times
        ]
    if corrupt:
        result[DEFAULT_ENTITIES["pv"]][5] = make_state(
            "pv", "unavailable", at=NOW + timedelta(minutes=5)
        )
    if missing:
        result.pop(DEFAULT_ENTITIES["grid"])
    return result


def test_recorder_integrates_only_corroborated_history():
    slots = history_slots(
        history_rows(),
        DEFAULT_ENTITIES,
        NOW,
        NOW + timedelta(minutes=15),
        recording_runs=[RecordingRun(NOW, NOW + timedelta(minutes=15))],
    )
    assert len(slots) == 1
    assert slots[0].home_kwh == pytest.approx(5.234 / 4)
    assert not slots[0].issues


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"corrupt": True}, "invalid_input"),
        ({"missing": True}, "historical_quality_unverifiable"),
    ],
)
def test_recorder_masked_history_never_becomes_zero(kwargs, code):
    slot = history_slots(
        history_rows(**kwargs),
        DEFAULT_ENTITIES,
        NOW,
        NOW + timedelta(minutes=15),
        recording_runs=[RecordingRun(NOW, NOW + timedelta(minutes=15))],
    )[0]
    assert slot.home_kwh is None
    assert code in codes(slot.issues)


def test_forecast_partially_elapsed_period_keeps_original_energy():
    snapshot = forecast(forecast_response(), NOW + timedelta(minutes=1))
    assert snapshot.periods[0].start == NOW
    assert snapshot.periods[0].kwh == 1
    assert snapshot.captured_at == NOW + timedelta(minutes=1)


def test_forecast_invalid_watts_and_duplicate_utc():
    response = forecast_response()
    response["watts"][NOW.isoformat()] = "nan"
    with pytest.raises(ValueError):
        forecast(response, NOW)
    response = forecast_response()
    response["wh_period"][NOW.astimezone(ZoneInfo("Europe/Copenhagen")).isoformat()] = (
        1000
    )
    with pytest.raises(ValueError):
        forecast(response, NOW)


def test_sparse_recorded_states_need_context_not_fake_heartbeats():
    end = NOW + timedelta(minutes=15)
    rows = history_rows(sparse=True)
    assert history_slots(rows, DEFAULT_ENTITIES, NOW, end)[0].home_kwh is None
    slot = history_slots(
        rows, DEFAULT_ENTITIES, NOW, end, recording_runs=[RecordingRun(NOW, end)]
    )[0]
    assert slot.home_kwh == pytest.approx(5.234 / 4)
    assert not slot.issues
