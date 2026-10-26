"""Forecast evaluation never reuses outcomes as training or forecasts."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.energy_copilot.forecast_accuracy import ForecastAccuracyWindow
from custom_components.energy_copilot.load_forecast import (
    HourlyLoad,
    backtest_recent_load,
    train_load_model,
)
from custom_components.energy_copilot.models import (
    ForecastPeriod,
    ForecastSnapshot,
    Sample,
)
from custom_components.energy_copilot.planning_inputs import LoadProjection


def test_prospective_quarter_error_uses_only_previously_recorded_forecast():
    tracker = ForecastAccuracyWindow()
    start = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)
    pv = ForecastSnapshot(
        start - timedelta(minutes=20),
        "observed-before",
        (ForecastPeriod(start, start + timedelta(minutes=15), 0.5),),
    )
    load = LoadProjection(
        start - timedelta(minutes=20),
        (ForecastPeriod(start, start + timedelta(minutes=15), 0.25),),
        "test_projection",
    )
    tracker.remember(start - timedelta(seconds=10), pv, load)
    for i in range(32):
        when = start - timedelta(seconds=10) + timedelta(seconds=30 * i)
        tracker.observe(
            when,
            {
                "pv": Sample(2000.0, when),
                "home": Sample(1000.0, when),
            },
        )
    observed = tracker.summary
    assert observed["pv"]["verified_quarters"] == 1
    assert observed["home"]["verified_quarters"] == 1
    assert observed["pv"]["mae_kwh_per_quarter"] == pytest.approx(0.0, abs=1e-5)
    assert observed["home"]["mae_kwh_per_quarter"] == pytest.approx(0.0, abs=1e-5)
    assert observed["physical_accuracy_verified"] is False


def test_outage_does_not_invent_zero_pv_energy():
    tracker = ForecastAccuracyWindow()
    start = datetime(2026, 10, 23, 10, tzinfo=UTC)
    pv = ForecastSnapshot(
        start - timedelta(minutes=1),
        "test",
        (ForecastPeriod(start, start + timedelta(minutes=15), 0.5),),
    )
    load = LoadProjection(
        start - timedelta(minutes=1),
        (ForecastPeriod(start, start + timedelta(minutes=15), 0.25),),
        "test",
    )
    tracker.remember(start - timedelta(seconds=10), pv, load)
    tracker.observe(start - timedelta(seconds=10), {"pv": Sample(2, start)})
    tracker.observe(start + timedelta(minutes=20), {"pv": Sample(2, start)})
    assert tracker.summary["pv"]["verified_quarters"] == 0


def test_holdout_load_model_is_frozen_before_evaluation_week():
    now = datetime(2026, 10, 23, 12, tzinfo=UTC)
    rows = tuple(
        HourlyLoad(now - timedelta(hours=24 * 60 - i), 0.7) for i in range(24 * 60)
    )
    model = train_load_model(rows, now, "historical_hourly")
    report = backtest_recent_load(model)
    assert report["hours_evaluated"] >= 160
    assert report["mae_kwh_per_hour"] == pytest.approx(0.0, abs=1e-8)
    assert report["bias_kwh_per_hour"] == pytest.approx(0.0, abs=1e-8)
    assert report["physical_consumption_verified"] is False


def test_quarter_watts_to_kwh_and_signed_underprediction():
    tracker = ForecastAccuracyWindow()
    first = datetime(2026, 10, 23, 10, tzinfo=UTC)
    pv = ForecastSnapshot(
        first - timedelta(minutes=30),
        "pv-forecast",
        (
            ForecastPeriod(first, first + timedelta(minutes=15), 0.25),
            ForecastPeriod(
                first + timedelta(minutes=15), first + timedelta(minutes=30), 0.75
            ),
        ),
    )
    projection = LoadProjection(
        first - timedelta(minutes=30),
        (
            ForecastPeriod(first, first + timedelta(minutes=15), 0.50),
            ForecastPeriod(
                first + timedelta(minutes=15), first + timedelta(minutes=30), 0.20
            ),
        ),
        "load-forecast",
    )
    tracker.remember(first - timedelta(seconds=15), pv, projection)
    for k in range(62):
        at = first - timedelta(seconds=15) + timedelta(seconds=k * 30)
        if k == 30:
            tracker.remember(at, pv, projection)
        tracker.observe(
            at,
            {
                "pv": Sample(2000.0, at),
                "home": Sample(1000.0, at),
            },
        )
    result = tracker.summary
    assert result["pv"]["verified_quarters"] == 2
    assert result["home"]["verified_quarters"] == 2
    # 2000 W * 0.25 h = 0.5 kWh: +0.25 over first, -0.25 under second.
    assert result["pv"]["mae_kwh_per_quarter"] == pytest.approx(0.25, abs=0.01)
    assert result["pv"]["signed_bias_kwh_per_quarter"] == pytest.approx(0.0, abs=0.01)
    # 1000 W * 0.25 h = 0.25 kWh; expected .5 then .2.
    assert result["home"]["mae_kwh_per_quarter"] == pytest.approx(0.15, abs=0.01)
    assert result["home"]["signed_bias_kwh_per_quarter"] == pytest.approx(
        0.10, abs=0.01
    )
    assert result["pv"]["positive_underprediction_p75_kwh_per_quarter"] is None


def test_pv_empirical_upside_available_only_after_sufficient_observed_quarters():
    tracker = ForecastAccuracyWindow()
    for i in range(16):
        tracker.completed.append({"pv": (0.3, 0.5)})
    assert tracker.summary["pv"][
        "positive_underprediction_p75_kwh_per_quarter"
    ] == pytest.approx(0.2)
    assert (
        tracker.summary["pv"]["pv_uncertainty_source"]
        == "measured_pv_sum_may_be_curtailed"
    )
    tracker.completed.clear()
    for i in range(15):
        tracker.completed.append({"pv": (0.3, 0.5)})
    assert tracker.summary["pv"]["positive_underprediction_p75_kwh_per_quarter"] is None
