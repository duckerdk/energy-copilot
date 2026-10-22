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
        hours = [
            {"buy": 0.5, "sell": 0.3, "pv_kw": pv, "home_kw": 1} for _ in range(8)
        ] + [{"buy": 2.8, "sell": 0.3, "pv_kw": pv, "home_kw": 1} for _ in range(8)]
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
    hours = [{"buy": 1, "sell": 0, "pv_kw": 6, "home_kw": 0.5} for _ in range(8)] + [
        {"buy": 3, "sell": 0, "pv_kw": 0, "home_kw": 1} for _ in range(8)
    ]
    result = simulate_scenario(scenario(hours, soc=20))
    assert result["summary"]["pv_charge_dc_kwh"] > 0
    assert result["summary"]["battery_discharge_dc_kwh"] > 0


def test_equal_price_no_arbitrage():
    hours = [{"buy": 1.5, "sell": 0.0, "pv_kw": 0, "home_kw": 0.6}] * 24
    result = simulate_scenario(scenario(hours, soc=50))
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
    payload = scenario(
        [{"buy": 0.4, "sell": 5, "pv_kw": 0, "home_kw": 0.4}] * 8, soc=75
    )
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
