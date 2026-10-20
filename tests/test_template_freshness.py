"""PR #10: stable native templates need live evidence from their base sources."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import SupportsResponse
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.energy_copilot.const import DOMAIN
from custom_components.energy_copilot.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.energy_copilot.live_measurements import (
    LiveMeasurementWindow,
    derived_templates,
)
from custom_components.energy_copilot.models import Issue
from custom_components.energy_copilot.quality import quality_report
from custom_components.energy_copilot.validation import measurements

from .conftest import NOW, make_state
from .test_validation import forecast_response


@pytest.fixture
async def native_templates(hass, settings, source_states, freezer):
    """Real YAML-style template entities without registry unique IDs."""
    freezer.move_to(NOW)
    for role, state in source_states.items():
        if role not in {"pv", "home"}:
            hass.states.async_set(
                state.entity_id,
                "0" if role in {"pv1", "pv2"} else state.state,
                dict(state.attributes),
            )
    hass.states.async_set("switch.sun12k_solar_sell", "off")
    assert await async_setup_component(
        hass,
        "template",
        {
            "template": [
                {
                    "sensor": [
                        {
                            "name": "PV sum",
                            "unit_of_measurement": "W",
                            "state": "{% if is_state('binary_sensor.synthetic_template_pending', 'on') %}{{ this.state }}{% else %}{{ states('sensor.sun12k_pv1_power') | float(0) + states('sensor.sun12k_pv2_power') | float(0) }}{% endif %}",
                        },
                        {
                            "name": "Home energy consumption",
                            "unit_of_measurement": "W",
                            "state": "{% if is_state('binary_sensor.synthetic_template_pending', 'on') %}{{ this.state }}{% else %}{{ states('sensor.pv_sum') | float(0) + states('sensor.sun12k_total_grid_power') | float(0) + states('sensor.sun12k_battery_output_power') | float(0) }}{% endif %}",
                        },
                    ]
                }
            ]
        },
    )
    await hass.async_start()
    await hass.async_block_till_done()
    entry = MockConfigEntry(domain=DOMAIN, data=settings, unique_id=DOMAIN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(settings["pv"]).state == "0.0"
    assert hass.states.get(settings["home"]).state == "2200.0"
    return entry


def report_leaves(hass, settings, *, omit=()):
    for role in ("pv1", "pv2", "grid", "battery", "soc"):
        if role not in omit:
            state = hass.states.get(settings[role])
            hass.states.async_set(state.entity_id, state.state, dict(state.attributes))


async def stable_for_ten_minutes(hass, entry, freezer):
    for _ in range(10):
        freezer.tick(timedelta(seconds=60))
        report_leaves(hass, entry.data)
        await hass.async_block_till_done()
        await entry.runtime_data.coordinator.async_refresh()


async def test_real_stable_night_pv_and_constant_home_use_live_leaf_evidence(
    hass, native_templates, freezer
):
    entry = native_templates
    coordinator = entry.runtime_data.coordinator
    originals = {
        r: hass.states.get(entry.data[r]).last_reported for r in ("pv", "home")
    }
    assert set(derived_templates(hass, coordinator.entities)) == {"pv", "home"}
    await stable_for_ten_minutes(hass, entry, freezer)
    for role in ("pv", "home"):
        sample = coordinator.data.measurements[role]
        assert (
            sample.at == originals[role] < coordinator.data.at - timedelta(seconds=300)
        )
        assert hass.states.get(entry.data[role]).last_reported == originals[role]
        assert sample.context_at == coordinator.data.at
        assert (
            Issue("derived_value_from_fresh_sources", role) in coordinator.data.issues
        )
        assert Issue("stale_input", role) not in coordinator.data.issues
    assert coordinator.data.measurements["pv"].value == 0
    assert coordinator.data.measurements["home"].value == 2200
    # Fresh Modbus leaves were observed; neither HA template was force-refreshed.
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    pv = diagnostic["observed"]["measurement_source_timing"]["pv"]
    assert pv["report_age_seconds"] >= 600
    assert pv["last_reported_utc"] == originals["pv"].isoformat()
    assert pv["freshness_time_basis"] == "validated_configured_sources"
    assert pv["context_oldest_report_utc"] == coordinator.data.at.isoformat()
    assert not pv["template_dependency_graph_verified"]
    window = diagnostic["observed"]["live_measurement_window"]
    assert window["home_rejected"] == 0
    assert window["home_retained_with_uncertainty"] == 5
    assert window["timing_seconds"]["source_report_skew_seconds"]["max"] >= 600
    assert window["timing_seconds"]["source_context_skew_seconds"]["max"] == 0
    assert Issue("forecast_entry_missing", "forecast_solar") in coordinator.data.issues
    assert coordinator.quality["input_state"] == "degraded"  # Independent forecast.


@pytest.mark.parametrize("dead", ["pv1", "pv2", "grid", "battery"])
async def test_dead_leaf_is_not_rescued_by_stable_native_templates(
    hass, native_templates, freezer, dead
):
    entry = native_templates
    await stable_for_ten_minutes(hass, entry, freezer)
    for _ in range(6):
        freezer.tick(timedelta(seconds=60))
        report_leaves(hass, entry.data, omit={dead})
        await hass.async_block_till_done()
        await entry.runtime_data.coordinator.async_refresh()
    coordinator = entry.runtime_data.coordinator
    assert "home" not in coordinator.data.measurements
    assert Issue("stale_input", dead) in coordinator.data.issues
    assert coordinator.quality["input_state"] == "degraded"


@pytest.mark.parametrize(
    "value,unit",
    [("unknown", "W"), ("unavailable", "W"), ("nan", "W"), ("0", "kWh"), (None, "W")],
)
async def test_float_zero_cannot_hide_bad_pv_leaf(
    hass, native_templates, freezer, value, unit
):
    entry = native_templates
    freezer.tick(timedelta(seconds=1))
    if value is None:
        hass.states.async_remove(entry.data["pv1"])
    else:
        hass.states.async_set(entry.data["pv1"], value, {"unit_of_measurement": unit})
    await hass.async_block_till_done()
    assert hass.states.get(entry.data["pv"]).state == "0.0"
    await entry.runtime_data.coordinator.async_refresh()
    data = entry.runtime_data.coordinator.data
    assert "pv" not in data.measurements and "home" not in data.measurements
    assert Issue("derived_source_invalid", "pv") in data.issues
    assert not any(i.code == "negative_home_normalized" for i in data.issues)


@pytest.mark.parametrize("leaf", ["pv1", "pv2"])
async def test_leaf_outage_between_polls_keeps_unchanged_templates_untrusted(
    hass, native_templates, freezer, leaf
):
    entry = native_templates
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(entry.data[leaf], "unavailable", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(entry.data[leaf], "0", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    await entry.runtime_data.coordinator.async_refresh()
    coordinator = entry.runtime_data.coordinator
    assert "home" not in coordinator.data.measurements
    assert Issue("derived_predates_source_recovery", "pv") in coordinator.data.issues
    recovered_at = coordinator.live_context.recovery_at[leaf]
    # Eight later hourly observations: even fresh leaves cannot certify the
    # pre-outage template. This intentional overnight gate is not a live replay.
    for hour in range(1, 9):
        freezer.move_to(NOW + timedelta(hours=hour))
        report_leaves(hass, entry.data)
        await hass.async_block_till_done()
        await coordinator.async_refresh()
        assert "pv" not in coordinator.data.measurements
        assert "home" not in coordinator.data.measurements
        assert (
            Issue("derived_predates_source_recovery", "pv") in coordinator.data.issues
        )
        assert coordinator.live_context.recovery_at[leaf] == recovered_at
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    pv = diagnostic["observed"]["measurement_source_timing"]["pv"]
    assert pv["report_age_seconds"] == 8 * 3600
    assert pv["recovery_pending_sources"] == [leaf]
    assert not pv["accepted"]
    # A real subsequent template evaluation/report re-establishes its context.
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(entry.data[leaf], "10", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    await coordinator.async_refresh()
    assert coordinator.data.measurements["home"].value == 2210
    assert not coordinator.live_context.recovery_at


@pytest.mark.parametrize("removed", [("pv1",), ("pv1", "pv2")])
async def test_missing_optional_mappings_report_unverifiable_stable_pv(
    hass, native_templates, freezer, removed
):
    entry = native_templates
    hass.config_entries.async_update_entry(entry, options={r: None for r in removed})
    await hass.async_block_till_done()
    coordinator = entry.runtime_data.coordinator
    # The template itself has live leaves, but Co-Pilot has no mapped evidence.
    await stable_for_ten_minutes(hass, entry, freezer)
    assert "home" not in coordinator.data.measurements
    assert Issue("stale_input", "pv") in coordinator.data.issues
    assert Issue("derived_freshness_unverifiable", "pv") in coordinator.data.issues
    assert all(coordinator.entities[r] is None for r in removed)
    assert all(
        Issue("optional_entity_unconfigured", r) in coordinator.data.issues
        for r in removed
    )


async def test_reload_accepts_old_native_values_only_with_current_valid_leaves(
    hass, native_templates, freezer
):
    entry = native_templates
    await stable_for_ten_minutes(hass, entry, freezer)
    old = entry.runtime_data.coordinator
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    new = entry.runtime_data.coordinator
    assert new is not old
    assert new.data.measurements["home"].value == 2200
    assert new.data.measurements["home"].context_at == new.data.at
    assert new.live_window.summary(new.data.at)["observations"] == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    hass.states.async_set(entry.data["pv1"], "unknown", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    assert not new.live_context.recovery_at and not old.live_context.recovery_at


async def test_supported_old_templates_are_uncertain_with_healthy_forecast(
    hass, native_templates, freezer
):
    entry = native_templates
    await stable_for_ten_minutes(hass, entry, freezer)
    source = MockConfigEntry(domain="forecast_solar")
    source.add_to_hass(hass)
    hass.services.async_register(
        "forecast_solar",
        "get_forecast",
        AsyncMock(return_value=forecast_response()),
        supports_response=SupportsResponse.ONLY,
    )
    hass.config_entries.async_update_entry(
        entry, options={"forecast_entry": source.entry_id}
    )
    await hass.async_block_till_done()
    sensor = hass.states.get("sensor.energy_co_pilot_input_quality")
    assert sensor.state == "uncertain"
    assert sensor.attributes["home_available"]
    assert sensor.attributes["issue_categories"]["blocking"] == 0
    assert sensor.attributes["issue_categories"]["uncertainty"] == 2


@pytest.mark.parametrize("fault", ["unknown", "nan", "unit", "future", "inconsistent"])
def test_old_derived_payload_is_not_excused_by_healthy_components(fault):
    states = {r: make_state(r) for r in ("pv", "grid", "battery")}
    states["home"] = make_state(
        "home",
        value=fault if fault in {"unknown", "nan"} else 999,
        at=NOW + timedelta(seconds=11)
        if fault == "future"
        else NOW - timedelta(hours=2),
        unit="kWh" if fault == "unit" else "W",
    )
    values, _, issues = measurements(
        states, NOW, derived_templates={"home": ("pv", "grid", "battery")}
    )
    assert "home" not in values
    assert Issue("derived_value_from_fresh_sources", "home") not in issues
    if fault == "inconsistent":
        assert Issue("derived_value_inconsistent", "home") in issues


def test_old_signed_home_keeps_raw_value_context_and_approved_normalization():
    states = {
        "pv": make_state("pv", 0),
        "grid": make_state("grid", -300),
        "battery": make_state("battery", 100),
        "home": make_state("home", -200, at=NOW - timedelta(hours=2)),
    }
    values, _, issues = measurements(
        states, NOW, derived_templates={"home": ("pv", "grid", "battery")}
    )
    home = values["home"]
    assert home.value == 0 and home.raw_value == -200
    assert home.at == NOW - timedelta(hours=2) and home.context_at == NOW
    assert Issue("negative_home_normalized", "home") in issues
    assert Issue("derived_value_from_fresh_sources", "home") in issues


def sum_states(role, difference=0, *, age=0):
    """Synthetic powers, nearly simultaneous reports, no device-frame proof."""
    powers = {
        "pv1": 400,
        "pv2": 600,
        "pv": 1000,
        "grid": 100,
        "battery": 0,
        "home": 1100,
    }
    powers[role] += difference
    if role == "pv":
        powers["home"] = powers["pv"] + powers["grid"] + powers["battery"]
    return {
        r: make_state(
            r, value, at=NOW - timedelta(seconds=age if r == role else index / 10)
        )
        for index, (r, value) in enumerate(powers.items())
    }


@pytest.mark.parametrize("role", ["pv", "home"])
@pytest.mark.parametrize(
    "difference", [0, -1, 1, -0.5, 0.5, -1.01, 1.01, 99, 100, -100.01, 100.01, 400]
)
def test_fresh_sum_residual_has_explicit_temporal_uncertainty(role, difference):
    states = sum_states(role, difference)
    values, _, issues = measurements(
        states,
        NOW,
        derived_templates={
            "pv": ("pv1", "pv2"),
            "home": ("pv", "grid", "battery"),
        },
    )
    report = quality_report(issues)
    assert "pv" in values and "home" in values
    assert values[role].value == float(states[role].state)
    assert values[role].at == states[role].last_reported
    assert (Issue("derived_sum_time_uncertain", role) in issues) == (
        abs(difference) > 1
    )
    assert report["input_state"] == ("uncertain" if abs(difference) > 1 else "valid")
    assert report["categories"]["blocking"] == 0
    if abs(difference) > 1:
        assert values[role].context_at is None  # No coherent sum was certified.
        warning = next(
            i for i in report["issues"] if i["code"] == "derived_sum_time_uncertain"
        )
        assert warning["effect"] == "configured_sum_differs_without_atomic_frame"
    if role == "pv" and abs(difference) > 100:
        assert Issue("pv_sum_inconsistent", "pv") in issues
        assert (
            next(i for i in report["issues"] if i["code"] == "pv_sum_inconsistent")[
                "category"
            ]
            == "uncertainty"
        )


def test_existing_unexplained_non_template_pv_inconsistency_remains_blocking():
    _, _, issues = measurements(sum_states("pv", 400), NOW)
    assert Issue("pv_sum_inconsistent", "pv") in issues
    assert quality_report(issues)["input_state"] == "degraded"


@pytest.mark.parametrize("role", ["pv", "home"])
def test_short_transition_warning_clears_with_coherent_template_without_losing_home(
    role,
):
    states = sum_states(role, 50)
    templates = {"pv": ("pv1", "pv2"), "home": ("pv", "grid", "battery")}
    values, _, issues = measurements(states, NOW, derived_templates=templates)
    assert "home" in values and quality_report(issues)["input_state"] == "uncertain"
    settled = sum_states(role)
    values, _, issues = measurements(
        settled, NOW + timedelta(seconds=1), derived_templates=templates
    )
    assert "home" in values and not issues
    assert quality_report(issues)["input_state"] == "valid"


@pytest.mark.parametrize("role", ["pv", "home"])
def test_expired_incoherent_template_still_blocks_instead_of_receiving_fresh_warning(
    role,
):
    values, _, issues = measurements(
        sum_states(role, 50, age=301),
        NOW,
        derived_templates={
            "pv": ("pv1", "pv2"),
            "home": ("pv", "grid", "battery"),
        },
    )
    assert "home" not in values
    assert Issue("derived_value_inconsistent", role) in issues
    assert Issue("derived_sum_time_uncertain", role) not in issues
    assert quality_report(issues)["input_state"] == "degraded"


@pytest.mark.parametrize(
    "leaf_state",
    [
        "unconfigured",
        "unconfigured_both",
        "unconfigured_unknown",
        "stale",
        "unknown",
        "unavailable",
        "missing",
    ],
)
async def test_public_fresh_core_with_unverifiable_pv1_is_an_explicit_acceptance_gate(
    hass, native_templates, freezer, leaf_state
):
    entry = native_templates
    if leaf_state.startswith("unconfigured"):
        removed = ("pv1", "pv2") if leaf_state == "unconfigured_both" else ("pv1",)
        hass.config_entries.async_update_entry(
            entry, options={r: None for r in removed}
        )
        await hass.async_block_till_done()
    # Core report ages are from the public 17:30 diagnostic; the 600-second
    # leaf age and powers are synthetic because the exact PV1 age is unknown.
    end = NOW + timedelta(seconds=600)
    freezer.move_to(end - timedelta(seconds=35.739319))
    hass.states.async_set(entry.data["pv2"], "1", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    freezer.move_to(end - timedelta(seconds=4.875376))
    hass.states.async_set(entry.data["battery"], "1001", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    freezer.move_to(end - timedelta(seconds=2.264175))
    hass.states.async_set(entry.data["grid"], "1201", {"unit_of_measurement": "W"})
    await hass.async_block_till_done()
    freezer.move_to(end - timedelta(seconds=2.263149))
    old = hass.states.get(entry.data["home"])
    hass.states.async_set(old.entity_id, old.state, dict(old.attributes))
    if leaf_state in {"unknown", "unavailable"}:
        hass.states.async_set(
            entry.data["pv1"], leaf_state, {"unit_of_measurement": "W"}
        )
    elif leaf_state == "missing":
        hass.states.async_remove(entry.data["pv1"])
    elif leaf_state == "unconfigured_unknown":
        hass.states.async_set(
            entry.data["pv1"], "unknown", {"unit_of_measurement": "W"}
        )
    await hass.async_block_till_done()
    freezer.move_to(end)
    hass.states.async_set(entry.data["soc"], "50", {"unit_of_measurement": "%"})
    coordinator = entry.runtime_data.coordinator
    before = coordinator.live_window.summary(end)
    await coordinator.async_refresh()
    diagnostic = await async_get_config_entry_diagnostics(hass, entry)
    timing = diagnostic["observed"]["measurement_source_timing"]
    pv = timing["pv"]
    assert pv["self_report_valid"]
    assert pv["report_age_seconds"] == pytest.approx(35.739319)
    assert timing["grid"]["report_age_seconds"] == pytest.approx(2.264175)
    assert timing["battery"]["report_age_seconds"] == pytest.approx(4.875376)
    assert timing["home"]["report_age_seconds"] == pytest.approx(2.263149)
    assert (
        coordinator.quality["live_measurement_acceptance"]
        == "pending_day_and_night_ha_evidence"
    )
    if leaf_state.startswith("unconfigured"):
        assert pv["accepted"] and "home" in coordinator.data.measurements
        assert (
            Issue("derived_source_confirmation_unavailable", "pv")
            in coordinator.data.issues
        )
        assert "pv1" not in pv["configured_sources"]
        assert "pv1" not in timing
        assert Issue("optional_entity_unconfigured", "pv1") in coordinator.data.issues
        if leaf_state == "unconfigured_both":
            assert not pv["configured_sources"] and "pv2" not in timing
    else:
        assert not pv["accepted"] and "home" not in coordinator.data.measurements
        assert "pv1" in pv["configured_source_issues"]
        assert not timing["home"]["accepted"]
        code = (
            "derived_source_freshness_unverifiable"
            if leaf_state == "stale"
            else "derived_source_invalid"
        )
        assert code in pv["issue_codes"]
        assert (
            next(
                i
                for i in coordinator.quality["issues"]
                if i["code"] == code and i["source"] == "pv"
            )["category"]
            == "blocking"
        )
        window = diagnostic["observed"]["live_measurement_window"]
        assert window["pv_rejected"] - before["pv_rejected"] == 1
        assert window["home_rejected"] - before["home_rejected"] == 1
        assert (
            window["pv_rejection_reasons"][f"pv:{code}"]
            - before["pv_rejection_reasons"].get(f"pv:{code}", 0)
            == 1
        )
        if leaf_state == "stale":
            assert pv["configured_source_issues"]["pv1"] == ["stale_input"]
            assert (
                next(i for i in coordinator.quality["issues"] if i["source"] == "pv1")[
                    "category"
                ]
                == "informational"
            )
            assert window["timing_seconds"]["pv1_report_age_seconds"]["max"] == 600
    assert diagnostic["read_only"]
    assert "source_w" not in str(diagnostic) and "sensor." not in str(diagnostic)


@pytest.mark.parametrize("age", [300, 300.000001])
def test_configured_pv1_freshness_boundary_applies_even_to_fresh_native_pv(age):
    states = sum_states("pv")
    states["pv1"] = make_state("pv1", 400, at=NOW - timedelta(seconds=age))
    values, _, issues = measurements(
        states, NOW, derived_templates={"pv": ("pv1", "pv2")}
    )
    assert ("pv" in values) == (age == 300)
    assert ("home" in values) == (age == 300)
    assert (Issue("derived_source_freshness_unverifiable", "pv") in issues) == (
        age > 300
    )


def test_optional_stale_leaf_does_not_poison_independent_pv_report():
    states = sum_states("pv")
    states["pv1"] = make_state("pv1", 400, at=NOW - timedelta(seconds=600))
    values, _, issues = measurements(states, NOW)  # No native derived PV evidence.
    assert "pv" in values and "home" in values
    assert issues == [Issue("stale_input", "pv1")]
    assert quality_report(issues)["input_state"] == "valid"


@pytest.mark.parametrize("native", [False, True])
def test_temporal_residual_does_not_override_recovery_or_forecast_blockers(native):
    values, _, issues = measurements(
        sum_states("home", -1200),
        NOW,
        derived_templates={"home": ("pv", "grid", "battery")} if native else {},
        source_recovery_at={"grid": NOW + timedelta(microseconds=1)},
    )
    assert "home" not in values
    assert (
        Issue(
            "derived_predates_source_recovery"
            if native
            else "home_predates_source_recovery",
            "home",
        )
        in issues
    )
    assert Issue("negative_home_normalized", "home") not in issues
    report = quality_report(
        issues + [Issue("forecast_horizon_incomplete", "forecast_solar")]
    )
    assert report["input_state"] == "degraded"
    assert report["categories"]["blocking"] == (3 if native else 2)
    assert report["categories"]["uncertainty"] == 0


def test_fresh_negative_sum_warning_keeps_clamp_and_independent_forecast_blocker():
    values, _, issues = measurements(
        sum_states("home", -1200),
        NOW,
        derived_templates={"home": ("pv", "grid", "battery")},
    )
    assert values["home"].value == 0 and values["home"].raw_value == -100
    assert Issue("derived_sum_time_uncertain", "home") in issues
    assert Issue("negative_home_normalized", "home") in issues
    report = quality_report(
        issues + [Issue("forecast_horizon_incomplete", "forecast_solar")]
    )
    assert report["input_state"] == "degraded"
    assert report["categories"] == {
        "blocking": 1,
        "uncertainty": 1,
        "historical": 0,
        "informational": 1,
    }


@pytest.mark.parametrize(
    "role,leaf,new_value,settled_home",
    [
        ("pv", "pv1", "100", 2300),
        ("home", "grid", "1300", 2300),
    ],
)
async def test_native_template_delayed_publication_is_uncertain_then_clears(
    hass, native_templates, freezer, role, leaf, new_value, settled_home
):
    entry = native_templates
    coordinator = entry.runtime_data.coordinator
    hass.states.async_set("binary_sensor.synthetic_template_pending", "on")
    await hass.async_block_till_done()
    freezer.tick(timedelta(seconds=1))
    hass.states.async_set(entry.data[leaf], new_value, {"unit_of_measurement": "W"})
    # A native state-based template holds its prior result while publication
    # is pending. This emulates lag without assuming HA callback scheduling.
    # Reports differ by only one second; this is not a physical fault proof.
    await hass.async_block_till_done()
    await coordinator.async_refresh()
    snapshot = coordinator.data
    assert "home" in snapshot.measurements
    assert Issue("derived_sum_time_uncertain", role) in snapshot.issues
    assert (
        next(
            i
            for i in coordinator.quality["issues"]
            if i["code"] == "derived_sum_time_uncertain" and i["source"] == role
        )["category"]
        == "uncertainty"
    )
    hass.states.async_set("binary_sensor.synthetic_template_pending", "off")
    await hass.async_block_till_done()
    await coordinator.async_refresh()
    assert coordinator.data.measurements["home"].value == settled_home
    assert not any(
        i.code == "derived_sum_time_uncertain" for i in coordinator.data.issues
    )


def test_multiple_bad_leaves_retain_both_freshness_and_payload_failures():
    states = sum_states("pv")
    states["pv1"] = make_state("pv1", 400, at=NOW - timedelta(seconds=600))
    states["pv2"] = make_state("pv2", "unknown")
    values, _, issues = measurements(
        states, NOW, derived_templates={"pv": ("pv1", "pv2")}
    )
    assert "pv" not in values and "home" not in values
    assert Issue("derived_source_freshness_unverifiable", "pv") in issues
    assert Issue("derived_source_invalid", "pv") in issues
    assert Issue("stale_input", "pv1") in issues
    assert Issue("invalid_input", "pv2") in issues


def test_temporal_pv_warning_is_not_counted_as_a_home_rejection_cause():
    states = sum_states("pv", 400)
    values, _, issues = measurements(
        states,
        NOW,
        derived_templates={"pv": ("pv1", "pv2")},
        source_recovery_at={"grid": NOW + timedelta(microseconds=1)},
    )
    window = LiveMeasurementWindow()
    window.record(states, NOW, values, issues)
    summary = window.summary(NOW)
    assert summary["pv_rejected"] == 0 and summary["home_rejected"] == 1
    assert not summary["pv_rejection_reasons"]
    assert summary["home_rejection_reasons"] == {
        "home:home_predates_source_recovery": 1
    }


def test_independent_pv_rejection_does_not_blame_optional_stale_leaf():
    states = sum_states("pv")
    states["pv"] = make_state("pv", "unknown")
    states["pv1"] = make_state("pv1", 400, at=NOW - timedelta(seconds=600))
    values, _, issues = measurements(states, NOW)
    window = LiveMeasurementWindow()
    window.record(states, NOW, values, issues)
    summary = window.summary(NOW)
    assert summary["pv_rejection_reasons"] == {"pv:invalid_input": 1}
    assert summary["home_rejection_reasons"] == {
        "pv:invalid_input": 1,
        "home:invalid_input": 1,
    }
