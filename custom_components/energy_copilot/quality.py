"""Classify M2 evidence without promising a planner or discarding warnings."""

from collections import Counter

from .const import REQUIRED_ENTITY_ROLES


def quality_report(issues, forecast_coverage=None):
    temporal_sum_sources = {
        i.source for i in issues if i.code == "derived_sum_time_uncertain"
    }
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
        elif code == "derived_source_freshness_unverifiable":
            category, effect = "blocking", "configured_source_freshness_unverified"
        elif code == "derived_predates_source_recovery":
            category, effect = "blocking", "await_actual_template_report_after_recovery"
        elif code in {"derived_sum_time_uncertain", "battery_power_inconsistent"} or (
            code == "pv_sum_inconsistent" and source in temporal_sum_sources
        ):
            category, effect = (
                "uncertainty",
                "configured_sum_differs_without_atomic_frame",
            )
        elif code == "derived_source_confirmation_unavailable":
            category, effect = (
                "uncertainty",
                "fresh_report_without_complete_leaf_evidence",
            )
        elif code in {
            "measurement_time_skew",
            "home_context_lag",
            "derived_value_from_fresh_sources",
            "pv_template_time_unverified",
            "derived_home_with_unverified_pv_time",
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
    current = [i for i in classified if i["source"] != "forecast_solar"]
    current_counts = Counter(i["category"] for i in current)
    return {
        "input_state": "degraded"
        if current_counts["blocking"]
        else "uncertain"
        if current_counts["uncertainty"]
        else "valid",
        "quality_scope": "required_current_inputs",
        "forecast_state": (
            "incomplete"
            if any(
                i["source"] == "forecast_solar" and i["category"] == "blocking"
                for i in classified
            )
            else "available"
        ),
        "planning_readiness": "not_evaluated_m2",
        "load_profile_readiness": "physical_validation_required",
        "live_measurement_acceptance": "pending_day_and_night_ha_evidence",
        "categories": {
            key: counts[key]
            for key in ("blocking", "uncertainty", "historical", "informational")
        },
        "issues": classified,
        "history_slot_policy": "complete_observed_quarter_required",
        "partial_energy_is_full_slot_estimate": False,
        "night_classification_supplies_forecast_energy": False,
    }
