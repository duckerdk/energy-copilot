"""Portable, read-only exact HA optimizer replay artifact.

Only already-normalized 15-minute planner inputs and one matching solution are
exported via user-downloaded diagnostics. No Recorder history or live controls.
The same schema is executed by the production optimizer and browser Pyodide.
"""

from dataclasses import asdict
from datetime import datetime, timedelta
from math import isfinite

from .horizon_optimizer import optimize_horizon
from .planner import Plant, Quarter

SCHEMA = "energy-copilot/ha-replay/v1"
MAX_QUARTERS = 672
TOLERANCES = {
    "soc_start_pct": 0.00001,
    "soc_end_pct": 0.00001,
    "grid_to_battery_ac_kwh": 0.000001,
    "pv_to_battery_dc_kwh": 0.000001,
    "battery_to_home_dc_kwh": 0.000001,
    "pv_to_export_dc_kwh": 0.000001,
    "pv_curtailed_dc_kwh": 0.000001,
    "grid_import_kwh": 0.000001,
    "grid_export_kwh": 0.000001,
    "purchase_dkk": 0.000001,
    "sales_dkk": 0.000001,
    "degradation_dkk": 0.000001,
    "charge_current_a": 0.00001,
    "grid_charge_current_a": 0.00001,
}


def _quarter_output(dispatch, outcome):
    return {
        **{
            field: getattr(outcome, field)
            for field in (
                "soc_start_pct",
                "soc_end_pct",
                "grid_import_kwh",
                "grid_export_kwh",
                "purchase_dkk",
                "sales_dkk",
                "degradation_dkk",
                "charge_current_a",
                "grid_charge_current_a",
            )
        },
        **{
            field: getattr(dispatch, field)
            for field in (
                "grid_to_battery_ac_kwh",
                "pv_to_battery_dc_kwh",
                "battery_to_home_dc_kwh",
                "pv_to_export_dc_kwh",
                "pv_curtailed_dc_kwh",
            )
        },
    }


def _result_output(result):
    candidate = result.candidate
    return {
        "summary": {
            "final_soc_pct": candidate.final_soc_pct,
            "objective_dkk": candidate.objective_dkk,
            "reference_objective_dkk": result.reference.objective_dkk,
            "purchase_cost_dkk": sum(q.purchase_dkk for q in candidate.quarters),
            "sales_revenue_dkk": sum(q.sales_dkk for q in candidate.quarters),
            "grid_charge_ac_kwh": sum(
                q.grid_to_battery_ac_kwh for q in result.dispatches
            ),
            "pv_charge_dc_kwh": sum(q.pv_to_battery_dc_kwh for q in result.dispatches),
            "battery_discharge_dc_kwh": sum(
                q.battery_to_home_dc_kwh for q in result.dispatches
            ),
            "pv_curtailed_dc_kwh": sum(
                q.pv_curtailed_dc_kwh for q in result.dispatches
            ),
        },
        "quarters": [
            {
                "start": q.start.isoformat(),
                **_quarter_output(dispatch, actual),
            }
            for q, dispatch, actual in zip(
                result.candidate.quarters,
                result.dispatches,
                result.candidate.quarters,
                strict=True,
            )
        ],
    }


def build_replay(plant, quarters, result, *, metadata=None):
    """Freeze all actual inputs, terminal override and output in one artifact."""
    if not 1 <= len(quarters) <= MAX_QUARTERS:
        raise ValueError("replay:invalid_horizon")
    return {
        "schema": SCHEMA,
        "source": "energy_copilot_ha_dry_run",
        "metadata": metadata or {},
        "plant": asdict(plant),
        "terminal_value_override_dkk_per_kwh_dc": (
            result.terminal_value_dkk_per_kwh_dc
        ),
        "quarters": [
            asdict(q)
            | {
                "start": q.start.isoformat(),
                "end": q.end.isoformat(),
            }
            for q in quarters
        ],
        "pv_headroom_policy": (
            "risk_aware_v1" if result.pv_headroom_enabled else "disabled"
        ),
        "pv_underprediction_kwh": result.pv_underprediction_kwh,
        "expected": _result_output(result),
        "executable": False,
    }


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"replay:{label}:numeric_required")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"replay:{label}:non_finite")
    return number


def _timestamp(raw, label):
    if not isinstance(raw, str):
        raise ValueError(f"replay:{label}:invalid_timestamp")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"replay:{label}:invalid_timestamp") from exc
    if value.tzinfo is None:
        raise ValueError(f"replay:{label}:timezone_required")
    return value


def _inputs(payload):
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise ValueError("replay:unsupported_format_or_missing_diagnostic_snapshot")
    if payload.get("executable") is not False:
        raise ValueError("replay:must_be_read_only")
    plant_data = payload.get("plant")
    if not isinstance(plant_data, dict):
        raise ValueError("replay:missing_plant")
    plant = Plant(
        **{key: _finite(plant_data[key], key) for key in Plant.__dataclass_fields__}
    )
    raw_quarters = payload.get("quarters")
    if not isinstance(raw_quarters, list) or not 1 <= len(raw_quarters) <= MAX_QUARTERS:
        raise ValueError("replay:invalid_quarter_count")
    quarters = []
    last_end = None
    for index, raw in enumerate(raw_quarters):
        if not isinstance(raw, dict):
            raise ValueError(f"replay:quarter_{index}:invalid")
        start = _timestamp(raw.get("start"), "start")
        end = _timestamp(raw.get("end"), "end")
        if end - start != timedelta(minutes=15) or (
            last_end is not None and start != last_end
        ):
            raise ValueError(f"replay:quarter_{index}:non_contiguous")
        if not isinstance(raw.get("pv_export_enabled"), bool):
            raise ValueError("replay:pv_export_enabled_must_be_boolean")
        quarters.append(
            Quarter(
                start,
                end,
                _finite(raw["buy_dkk_per_kwh"], "buy"),
                _finite(raw["sell_dkk_per_kwh"], "sell"),
                _finite(raw["pv_dc_kwh"], "pv"),
                _finite(raw["home_ac_kwh"], "home"),
                raw["pv_export_enabled"],
            )
        )
        last_end = end
    terminal = _finite(
        payload.get("terminal_value_override_dkk_per_kwh_dc"),
        "terminal_value",
    )
    expected = payload.get("expected")
    if (
        not isinstance(expected, dict)
        or not isinstance(expected.get("summary"), dict)
        or not isinstance(expected.get("quarters"), list)
        or len(expected["quarters"]) != len(quarters)
    ):
        raise ValueError("replay:missing_expected_result")
    policy = payload.get("pv_headroom_policy", "disabled")
    if policy not in ("risk_aware_v1", "disabled"):
        raise ValueError("replay:unsupported_headroom_policy")
    upside_raw = payload.get("pv_underprediction_kwh")
    upside = None if upside_raw is None else _finite(upside_raw, "pv_upside")
    return plant, tuple(quarters), terminal, expected, policy, upside


def simulate_replay(payload):
    """Execute unchanged HA solver and compare against frozen matching result."""
    plant, quarters, terminal, expected, policy, upside = _inputs(payload)
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict) or not isinstance(
        metadata.get("grid_charge_already_active", False), bool
    ):
        raise ValueError("replay:invalid_grid_charge_active")
    result = optimize_horizon(
        plant,
        quarters,
        grid_charge_already_active=metadata.get("grid_charge_already_active", False),
        terminal_value_override=terminal,
        pv_underprediction_kwh=upside,
        enable_pv_headroom=policy == "risk_aware_v1",
    )
    actual = _result_output(result)
    errors = []
    maximum_by_field = {}
    comparison = []

    for index, (ref, got) in enumerate(
        zip(expected["quarters"], actual["quarters"], strict=True)
    ):
        if ref.get("start") != got["start"]:
            raise ValueError(f"replay:quarter_{index}:start_mismatch")
        differences = {}
        for field, tolerance in TOLERANCES.items():
            delta = _finite(got[field], field) - _finite(ref.get(field), field)
            differences[field] = delta
            maximum_by_field[field] = max(maximum_by_field.get(field, 0.0), abs(delta))
            if abs(delta) > tolerance:
                errors.append(
                    {
                        "quarter": index,
                        "start": got["start"],
                        "field": field,
                        "difference": delta,
                    }
                )
        comparison.append(
            {
                "start": got["start"],
                "input": {
                    "buy_dkk_per_kwh": quarters[index].buy_dkk_per_kwh,
                    "sell_dkk_per_kwh": quarters[index].sell_dkk_per_kwh,
                    "pv_dc_kwh": quarters[index].pv_dc_kwh,
                    "home_ac_kwh": quarters[index].home_ac_kwh,
                },
                "ha": ref,
                "lab": got,
                "difference": differences,
            }
        )

    summary_delta = {}
    for field, got in actual["summary"].items():
        delta = _finite(got, field) - _finite(expected["summary"].get(field), field)
        summary_delta[field] = delta
        if abs(delta) > (0.00001 if field == "final_soc_pct" else 0.000001):
            errors.append({"quarter": None, "field": field, "difference": delta})

    return {
        "schema": SCHEMA,
        "start": quarters[0].start.isoformat(),
        "end": quarters[-1].end.isoformat(),
        "quarter_count": len(quarters),
        "identical": not errors,
        "mismatch_count": len(errors),
        "mismatches": errors[:100],
        "max_absolute_difference_by_field": maximum_by_field,
        "summary_ha": expected["summary"],
        "summary_lab": actual["summary"],
        "summary_difference": summary_delta,
        "quarters": comparison,
        "metadata": payload.get("metadata", {}),
        "read_only": True,
    }
