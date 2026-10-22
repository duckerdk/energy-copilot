"""Offline Planner Lab is a thin adapter around production optimizer modules."""

import sys
from copy import deepcopy
from pathlib import Path
from shutil import which
from subprocess import run

import pytest

from tools.planner_lab.server import _core_modules, simulate_scenario


def scenario(hours=None, soc=25, pv=0):
    if hours is None:
        hours = [{"spot": 0.3, "pv_kw": pv, "home_kw": 1} for _ in range(8)] + [
            {"spot": 2.8, "pv_kw": pv, "home_kw": 1} for _ in range(8)
        ]
    return {
        "start_utc": "2026-10-22T00:00:00Z",
        "initial_soc_pct": soc,
        "battery_capacity_kwh": 10.24,
        "battery_voltage_v": 51.2,
        "charge_limit_a": 50,
        "grid_charge_limit_a": 50,
        "discharge_limit_a": 100,
        "efficiency": 0.95,
        "pv_export_enabled": False,
        "hours": hours,
    }


def test_local_runner_loads_original_optimizer_without_ha_modules():
    planner, horizon = _core_modules()
    assert horizon.optimize_horizon.__module__.endswith(".horizon_optimizer")
    assert planner.simulate_candidate.__module__.endswith(".planner")


def test_end_to_end_price_arbitrage_and_quarter_outputs():
    result = simulate_scenario(scenario())
    summary = result["summary"]
    assert len(result["hourly"]) == 16
    assert len(result["quarters"]) == 64
    assert summary["modeled_saving_dkk"] > 0
    assert summary["grid_charge_ac_kwh"] > 0
    assert summary["battery_discharge_dc_kwh"] > 0
    assert summary["physical_dispatch_verified"] is True
    assert summary["device_commands_executed"] is False
    assert summary["deye_tou_verified"] is False
    assert sum(q["grid_charge_ac_kwh"] for q in result["quarters"]) == pytest.approx(
        summary["grid_charge_ac_kwh"], abs=0.001
    )
    assert result["hourly"][-1]["soc_end_pct"] == summary["final_soc_pct"]


def test_pv_forecast_changes_result_and_exposes_pv_charging():
    hours = [{"spot": 1, "pv_kw": 6, "home_kw": 0.5} for _ in range(8)] + [
        {"spot": 3, "pv_kw": 0, "home_kw": 1} for _ in range(8)
    ]
    result = simulate_scenario(scenario(hours, soc=20))
    assert result["summary"]["pv_charge_dc_kwh"] > 0
    assert result["summary"]["battery_discharge_dc_kwh"] > 0


def test_equal_price_no_arbitrage():
    hours = [{"spot": 1.5, "pv_kw": 0, "home_kw": 0.6}] * 6
    test_case = scenario(hours, soc=50)
    test_case["start_utc"] = "2026-10-22T07:00:00Z"  # Local 09:00–15:00, same N1 tariff
    result = simulate_scenario(test_case)
    assert result["summary"]["grid_charge_ac_kwh"] == 0
    assert result["summary"]["battery_discharge_dc_kwh"] == 0


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("initial_soc_pct", 10),
        ("initial_soc_pct", 110),
        ("battery_voltage_v", 0),
        ("charge_limit_a", 55),
        ("efficiency", 1.1),
        ("grid_charge_limit_a", 55),
        ("start_utc", "2026-10-22T00:00:00"),
        ("start_utc", "2026-10-22T00:30:00Z"),
    ],
)
def test_rejects_invalid_parameters(key, value):
    payload = scenario()
    payload[key] = value
    with pytest.raises(ValueError):
        simulate_scenario(payload)


def test_rejects_missing_hour_or_nonfinite_value():
    payload = scenario()
    payload["hours"][3].pop("pv_kw")
    with pytest.raises(ValueError, match="PV"):
        simulate_scenario(payload)
    payload = scenario()
    payload["hours"][4]["home_kw"] = float("nan")
    with pytest.raises(ValueError, match="skończona"):
        simulate_scenario(payload)


def test_export_flag_does_not_enable_battery_export():
    payload = scenario([{"spot": 5, "pv_kw": 0, "home_kw": 0.4}] * 8, soc=75)
    payload["pv_export_enabled"] = True
    r = simulate_scenario(payload)
    assert all(q["grid_export_ac_kwh"] == 0 for q in r["quarters"])


def test_no_mutation_and_accepts_local_input_without_hass():
    p = scenario()
    saved = deepcopy(p)
    result = simulate_scenario(p)
    assert result["summary"]["hours"] == len(p["hours"])
    assert p == saved


def test_hourly_limits():
    p = scenario()
    p["hours"] *= 5
    with pytest.raises(ValueError, match="72"):
        simulate_scenario(p)


def test_spot_prices_exactly_match_historical_ha_buy_sell_readings():
    # HA source dated 2026-10-20, N1; prices may differ by 0.001
    # in raw HA due to source rounding.
    hours = [{"spot": 1.567, "pv_kw": 0, "home_kw": 0.6}] * 24
    hours[6] = {"spot": 1.652, "pv_kw": 0, "home_kw": 0.6}
    hours[17] = {"spot": 1.903, "pv_kw": 0, "home_kw": 0.6}
    test_case = scenario(hours, soc=50)
    test_case["start_utc"] = "2026-10-19T22:00:00Z"  # Local 20 Oct 00:00
    result = simulate_scenario(test_case)
    assert result["hourly"][0]["sell"] == pytest.approx(1.567)
    assert result["hourly"][0]["buy"] == pytest.approx(1.831)
    assert result["hourly"][6]["buy"] == pytest.approx(2.135)
    assert result["hourly"][17]["buy"] == pytest.approx(3.045)
    assert result["summary"]["tariff_source"] == "N1_2026-10-20_HA_export_snapshot"


def test_dst_tariff_local_hour_is_resolved_across_repeated_hour():
    from datetime import UTC, datetime

    from tools.planner_lab.engine import _local_hour_copenhagen, _prices_from_spot

    summer_2am = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
    winter_2am = datetime(2026, 10, 25, 1, 0, tzinfo=UTC)
    assert _local_hour_copenhagen(summer_2am) == 2
    assert _local_hour_copenhagen(winter_2am) == 2
    assert _prices_from_spot(1, summer_2am) == pytest.approx((1.264, 1.0))
    assert _prices_from_spot(1, winter_2am) == pytest.approx((1.264, 1.0))


def test_public_sample_home_profile_has_hourly_source_not_fictitious_constant():
    import re

    root = Path(__file__).resolve().parents[1]
    page = (root / "tools/planner_lab/index.html").read_text(encoding="utf-8")
    profile = re.search(r"const OBSERVED_HOME_KW = \[([0-9.,\s]+)\];", page)
    assert profile
    samples = [float(x.strip()) for x in profile.group(1).split(",")]
    assert len(samples) == 24
    assert sum(samples) == pytest.approx(27.5156, abs=0.001)
    assert min(samples) > 0
    assert max(samples) > 3
    assert 'const keys = ["spot","pv_kw","home_kw"]' in page
    assert "spot;pv_kw;home_kw" in page



def test_continuous_dispatch_covers_small_evening_deficit_after_pv():
    """Regression: old 0.1 kWh lattice cannot cover 0.0726 kWh/quarter."""
    hours = [
        {"spot": 0.6, "pv_kw": 0.0, "home_kw": 0.5} for _ in range(24)
    ]
    hours[18] = {"spot": 4.0, "pv_kw": 0.5, "home_kw": 0.7654}
    hours[19] = {"spot": 4.0, "pv_kw": 0.0, "home_kw": 0.7710}
    case = scenario(hours, soc=92)
    case["start_utc"] = "2026-10-21T22:00:00Z"  # 00:00 Copenhagen
    result = simulate_scenario(case)
    q18 = result["quarters"][18 * 4 : 19 * 4]
    q19 = result["quarters"][19 * 4 : 20 * 4]
    assert result["summary"]["soc_step_dc_kwh"] == 0.0
    assert result["summary"]["solver"].startswith("lab_continuous_")
    assert result["hourly"][18]["grid_import_ac_kwh"] == pytest.approx(
        0.0, abs=0.0001
    )
    assert result["hourly"][19]["grid_import_ac_kwh"] == pytest.approx(
        0.0, abs=0.0001
    )
    assert [row["discharge_dc_kwh"] for row in q18] == pytest.approx(
        [0.0726 / 0.95] * 4, abs=0.00003
    )
    assert sum(row["discharge_dc_kwh"] for row in q19) == pytest.approx(
        0.7710 / 0.95, abs=0.0001
    )
    assert all(row["soc_end_pct"] >= 20 for row in result["quarters"])


def test_continuous_lab_respects_export_toggle_above_threshold():
    # Selling the PV surplus should not depend on battery cycle choices
    # once SOC=100% and the battery has no room to store that energy.
    hours = [{"spot": 1.0, "pv_kw": 5, "home_kw": 0.4}] * 4
    case = scenario(hours, soc=100)
    case["start_utc"] = "2026-10-21T22:00:00Z"
    case["pv_export_enabled"] = True
    selling = simulate_scenario(case)
    assert selling["summary"]["grid_export_ac_kwh"] > 0
    assert selling["summary"]["pv_curtailed_dc_kwh"] == pytest.approx(0.0)
    case["pv_export_enabled"] = False
    no_selling = simulate_scenario(case)
    assert no_selling["summary"]["grid_export_ac_kwh"] == pytest.approx(0.0)
    assert no_selling["summary"]["pv_curtailed_dc_kwh"] > 0


def test_lab_only_solver_does_not_change_production_0_1_kwh_optimizer():
    planner, production = _core_modules()
    assert production.SOC_STEP_DC_KWH == 0.1
    assert callable(production.optimize_horizon)
    assert planner.MIN_SOC == 20
    case = scenario()
    result = simulate_scenario(case)
    assert result["summary"]["soc_step_dc_kwh"] == 0.0
    assert list(result.keys()) == ["summary", "hourly", "quarters"]
    assert len(result["quarters"]) == 4 * len(case["hours"])

def test_browser_script_is_syntactically_valid():
    """Catch frontend typos in CI; Node is optional for users of the lab."""
    if which("node") is None:
        pytest.skip("Node.js is not installed in this test environment")
    page = (
        Path(__file__).resolve().parents[1] / "tools" / "planner_lab" / "index.html"
    ).read_text(encoding="utf-8")
    script = page.split("<script>", 1)[1].split("</script>", 1)[0]
    checked = run(["node", "--check"], input=script, text=True, capture_output=True)
    assert checked.returncode == 0, checked.stderr


def test_browser_worker_javascript_syntax():
    if which("node") is None:
        pytest.skip("Node.js unavailable")
    worker = Path(__file__).resolve().parents[1] / "tools" / "planner_lab" / "worker.js"
    checked = run(["node", "--check", str(worker)], capture_output=True, text=True)
    assert checked.returncode == 0, checked.stderr


def test_local_launcher_imports_shared_engine():
    """Shared adapter remains usable without a Home Assistant installation."""
    server = Path(__file__).resolve().parents[1] / "tools" / "planner_lab" / "server.py"
    checked = run(
        [sys.executable, str(server), "--help"], capture_output=True, text=True
    )
    assert checked.returncode == 0, checked.stderr
    assert "--port" in checked.stdout


def test_site_is_static_without_server_post_or_independent_optimizer():
    root = Path(__file__).resolve().parents[1]
    html = (root / "tools/planner_lab/index.html").read_text(encoding="utf-8")
    worker = (root / "tools/planner_lab/worker.js").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/planner-lab-pages.yml").read_text(
        encoding="utf-8"
    )
    assert "/api/simulate" not in html
    assert 'new Worker("./worker.js")' in html
    assert "engine.py" in worker and "planner.py" in worker
    assert "horizon_optimizer.py" in worker
    assert "actions/deploy-pages@v4" in workflow
    assert "custom_components/energy_copilot/planner.py" in workflow
    assert "custom_components/energy_copilot/horizon_optimizer.py" in workflow
    assert "payload:payload()" in html


def test_shared_engine_identical_to_server_results():
    from tools.planner_lab.engine import simulate_scenario as direct
    from tools.planner_lab.server import simulate_scenario as local

    assert direct is local
    assert direct(scenario()) == local(scenario())
