"""Read-only counterfactual evidence for the first planned quarter.

Re-optimize the identical published HA replay with the chosen first-quarter
action forbidden. This is a comparison between two *whole-horizon* feasible
plans, not a local price heuristic or a claim about actual inverter flow.
The normal production solution and its parameters are never modified.
"""

from .horizon_optimizer import optimize_horizon
from .planner import InfeasibleCandidate
from .replay import _inputs

_SUPPORTED_ACTIONS = {"pv_charge", "grid_charge", "battery_discharge"}


def compare_first_quarter(replay, action):
    """Return the actual cost of forbidding the first-quarter chosen action."""
    if action not in _SUPPORTED_ACTIONS:
        return {"economic_comparison_status": "not_supported"}
    plant, quarters, terminal, expected, policy, upside = _inputs(replay)
    original = expected["summary"]["objective_dkk"]
    try:
        alternative = optimize_horizon(
            plant,
            quarters,
            terminal_value_override=terminal,
            pv_underprediction_kwh=upside,
            enable_pv_headroom=policy == "risk_aware_v1",
            audit_forbid_first_action=action,
        )
    except InfeasibleCandidate as exc:
        return {
            "economic_comparison_status": "alternative_infeasible",
            "economic_alternative_reason": str(exc),
        }
    comparison = alternative.candidate
    saved = comparison.objective_dkk - original
    return {
        "economic_comparison_status": "evaluated",
        "economic_alternative": f"no_first_{action}",
        "economic_saving_dkk": saved,
        "economic_selected_cost_dkk": original,
        "economic_alternative_cost_dkk": comparison.objective_dkk,
        "economic_alternative_first_sale_dkk": comparison.quarters[0].sales_dkk,
        "economic_selected_first_sale_dkk": expected["quarters"][0]["sales_dkk"],
        "economic_alternative_first_grid_import_kwh": comparison.quarters[0].grid_import_kwh,
        "economic_selected_first_grid_import_kwh": expected["quarters"][0]["grid_import_kwh"],
        "economic_scope": "whole_horizon_same_inputs_no_first_action",
    }
