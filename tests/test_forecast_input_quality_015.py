"""Regression: forecast availability must not degrade current measurements."""

from custom_components.energy_copilot.models import Issue
from custom_components.energy_copilot.quality import quality_report


def test_missing_twilight_forecast_does_not_degrade_live_inputs():
    coverage = {"unresolved_forecast_seconds": 2320.351672}
    result = quality_report([Issue("forecast_horizon_incomplete", "forecast_solar")], coverage)
    assert result["input_state"] == "valid"
    assert result["forecast_state"] == "incomplete"
    assert result["categories"]["blocking"] == 1


def test_live_uncertainty_with_forecast_gap():
    coverage = {"unresolved_forecast_seconds": 2320.351672}
    result = quality_report([
        Issue("measurement_time_skew", "home"),
        Issue("forecast_horizon_incomplete", "forecast_solar"),
    ], coverage)
    assert result["input_state"] == "uncertain"
    assert result["forecast_state"] == "incomplete"


def test_live_failure_still_degrades():
    result = quality_report([Issue("invalid_input", "pv")])
    assert result["input_state"] == "degraded"
