"""Classify M2 evidence without promising a planner or discarding warnings."""

from collections import Counter

from .const import REQUIRED_ENTITY_ROLES


def quality_report(issues, forecast_coverage=None):
    classified = []
    for issue in issues:
        code, source = issue.code, issue.source
        if code == "forecast_horizon_incomplete":
            night_only = (
                forecast_coverage is not None
                and forecast_coverage["unresolved_forecast_seconds"] == 0
            )
            category = "informational" if night_only else "blocking"
            effect = (
                "night_energy_policy_required"
                if night_only
                else "forecast_horizon_unresolved"
            )
        elif code in {
            "measurement_time_skew",
            "home_context_lag",
            "derived_value_from_fresh_sources",
        }:
            category, effect = "uncertainty", "as_of_values_not_atomic_measurement"
        elif code == "negative_home_normalized":
            category, effect = "informational", "user_approved_home_normalization"
        elif source == "recorder" or code in {
            "home_profile_unverified",
            "forecast_storage_failed",
            "forecast_storage_unavailable",
            "forecast_history_invalid",
        }:
            category, effect = "historical", "training_or_replay_quality_limited"
        elif code in {
            "optional_entity_unconfigured",
            "possible_curtailment",
            "forecast_observed_after_period_start",
            "forecast_night_unpublished",
        } or (
            source not in REQUIRED_ENTITY_ROLES
            and code
            in {"invalid_input", "invalid_unit", "stale_input", "missing_timestamp"}
        ):
            category, effect = "informational", "inspect_source_or_period_policy"
        else:
            # Unknown failures must not silently become harmless notices.
            category, effect = "blocking", "required_current_input_unusable"
        classified.append(
            {"code": code, "source": source, "category": category, "effect": effect}
        )
    counts = Counter(i["category"] for i in classified)
    return {
        "input_state": "degraded"
        if counts["blocking"]
        else "uncertain"
        if counts["uncertainty"]
        else "valid",
        "quality_scope": "required_current_inputs",
        "planning_readiness": "not_evaluated_m2",
        "load_profile_readiness": "physical_validation_required",
        "categories": {
            key: counts[key]
            for key in ("blocking", "uncertainty", "historical", "informational")
        },
        "issues": classified,
        "history_slot_policy": "complete_observed_quarter_required",
        "partial_energy_is_full_slot_estimate": False,
        "night_classification_supplies_forecast_energy": False,
    }
