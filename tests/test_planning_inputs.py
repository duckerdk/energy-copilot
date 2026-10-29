"""M3 input preparation: real snapshot contract, strict coverage and provenance."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.energy_copilot.models import (
    ForecastPeriod,
    ForecastSnapshot,
    HistorySlot,
    InputSnapshot,
    Sample,
    Issue,
    PriceSlot,
)
from custom_components.energy_copilot.planning_inputs import (
    LoadProjection,
    PlanningInputError,
    build_planning_input,
    project_previous_utc_day_load,
)

NOW = datetime(2026, 10, 21, 10, 7, tzinfo=UTC)
HOUR = NOW.replace(minute=0)
QUARTER = timedelta(minutes=15)
DAY = timedelta(days=1)


def forecast_quarters(*, start=HOUR, count=4, kwh=0.2):
    return tuple(
        ForecastPeriod(
            start + index * QUARTER,
            start + (index + 1) * QUARTER,
            kwh,
        )
        for index in range(count)
    )


def history_quarters(*, start=HOUR, count=4, kwh=0.3):
    return tuple(
        HistorySlot(
            start + index * QUARTER - DAY,
            start + (index + 1) * QUARTER - DAY,
            kwh,
            observed_seconds=900,
        )
        for index in range(count)
    )


def snapshot(*, now=NOW, prices=None, periods=None, history=None):
    return InputSnapshot(
        at=now,
        prices=(
            (PriceSlot(HOUR, HOUR + timedelta(hours=1), 0.32, 0.41),)
            if prices is None
            else prices
        ),
        forecast=ForecastSnapshot(
            now - timedelta(minutes=1),
            "forecast-1",
            forecast_quarters() if periods is None else periods,
        ),
        history=history_quarters() if history is None else history,
    )


def prepare(data=None, **kwargs):
    return build_planning_input(
        data or snapshot(),
        pv_forecast_to_dc_multiplier=kwargs.pop("factor", 1.25),
        **kwargs,
    )


def test_real_snapshot_fields_make_complete_future_quarters():
    result = prepare()
    assert len(result.quarters) == 3
    assert result.quarters[0].start == HOUR + QUARTER
    assert result.quarters[-1].end == HOUR + timedelta(hours=1)
    assert result.quarters[0].pv_dc_kwh == pytest.approx(0.25)
    assert result.quarters[0].home_ac_kwh == pytest.approx(0.3)
    assert result.quarters[0].buy_dkk_per_kwh == 0.32
    assert result.quarters[0].sell_dkk_per_kwh == 0.41
    assert result.pv_forecast_version == "forecast-1"
    assert result.load_method == "previous_24h_utc_unverified"
    assert result.actionable is False


def test_exact_quarter_decision_includes_current_complete_quarter():
    result = prepare(snapshot(now=HOUR))
    assert len(result.quarters) == 4
    assert result.quarters[0].start == HOUR


def test_started_partial_quarter_is_not_prorated_or_replayed():
    result = prepare(snapshot(now=HOUR + timedelta(minutes=15, seconds=1)))
    assert result.quarters[0].start == HOUR + 2 * QUARTER


def test_previous_day_projection_rejects_partial_missing_and_future_history():
    data = snapshot()
    valid = history_quarters()
    partial = replace(valid[1], home_kwh=3.0, observed_seconds=800)
    missing = replace(valid[2], home_kwh=None)
    future = replace(valid[3], end=NOW + timedelta(days=1))
    prediction = project_previous_utc_day_load(
        replace(data, history=(valid[0], partial, missing, future))
    )
    assert len(prediction.periods) == 1
    with pytest.raises(PlanningInputError) as error:
        prepare(replace(data, history=(valid[0], partial, missing, future)))
    assert error.value.code == "load:coverage_or_resolution_gap"


def test_opt_in_short_load_gap_models_prediction_not_recorder_records():
    slots = history_quarters()
    slots = (
        replace(slots[0], home_kwh=0.2),
        replace(
            slots[1],
            home_kwh=None,
            observed_seconds=875,
            unobserved_seconds=25,
        ),
        replace(slots[2], home_kwh=0.6),
        slots[3],
    )
    data = snapshot(now=HOUR, history=slots)
    forecast = project_previous_utc_day_load(
        data, short_gap_model="linear_bracketed_unverified"
    )
    assert slots[1].home_kwh is None
    assert forecast.modeled_quarters == 1
    assert forecast.method == "previous_24h_utc_linear_bracketed_gap_model_unverified"
    assert forecast.periods[1].kwh == pytest.approx(0.4)
    result = prepare(data, load_projection=forecast)
    assert result.quarters[1].home_ac_kwh == pytest.approx(0.4)
    assert result.load_modeled_quarters == 1
    assert result.actionable is False


def test_bracketed_three_quarter_recorder_gap_models_only_future_load():
    slots = history_quarters(count=8)
    slots = tuple(
        replace(slot, home_kwh=None, observed_seconds=0, unobserved_seconds=900)
        if index in (2, 3, 4)
        else replace(slot, home_kwh=0.2 if index == 1 else 0.6)
        for index, slot in enumerate(slots)
    )
    data = snapshot(
        now=HOUR,
        prices=(
            PriceSlot(HOUR, HOUR + timedelta(hours=1), 0.4, 0.4),
            PriceSlot(
                HOUR + timedelta(hours=1), HOUR + 2 * timedelta(hours=1), 0.5, 0.4
            ),
        ),
        periods=forecast_quarters(count=8),
        history=slots,
    )
    prediction = project_previous_utc_day_load(
        data, short_gap_model="linear_bracketed_unverified"
    )
    assert prediction.modeled_quarters == 3
    assert [prediction.periods[i].kwh for i in (2, 3, 4)] == pytest.approx(
        [0.3, 0.4, 0.5]
    )
    assert len(prepare(data, load_projection=prediction).quarters) == 8


def test_long_load_gap_or_unbracketed_gap_is_never_modeled():
    slots = history_quarters(count=8)
    long_gap = tuple(
        replace(slot, home_kwh=None, observed_seconds=0, unobserved_seconds=900)
        if index in (2, 3, 4, 5)
        else slot
        for index, slot in enumerate(slots)
    )
    data = snapshot(now=HOUR, history=long_gap)
    prediction = project_previous_utc_day_load(
        data, short_gap_model="linear_bracketed_unverified"
    )
    assert prediction.modeled_quarters == 0
    projected_starts = {period.start for period in prediction.periods}
    assert all(HOUR + index * QUARTER not in projected_starts for index in (2, 3, 4, 5))
    unbracketed = snapshot(
        now=HOUR,
        history=(
            replace(
                slots[0], home_kwh=None, observed_seconds=0, unobserved_seconds=900
            ),
            *slots[1:],
        ),
    )
    projection = project_previous_utc_day_load(
        unbracketed, short_gap_model="linear_bracketed_unverified"
    )
    assert projection.modeled_quarters == 0
    assert projection.periods[0].start == HOUR + QUARTER


def test_short_gap_model_rejects_unknown_policy_and_duplicate_recorder_slots():
    data = snapshot()
    with pytest.raises(PlanningInputError, match="load:invalid_short_gap_model"):
        project_previous_utc_day_load(data, short_gap_model="invent_zero")
    with pytest.raises(PlanningInputError, match="load:duplicate_history"):
        project_previous_utc_day_load(
            snapshot(history=(*history_quarters(), history_quarters()[1])),
            short_gap_model="linear_bracketed_unverified",
        )


def test_missing_pv_at_night_is_not_invented_as_zero():
    data = snapshot(periods=forecast_quarters(count=2))
    with pytest.raises(PlanningInputError) as error:
        prepare(data)
    assert error.value.code == "pv:coverage_or_resolution_gap"
    assert error.value.at == HOUR + 2 * QUARTER


def test_hourly_forecast_energy_is_not_spread_without_intraperiod_model():
    data = snapshot(periods=(ForecastPeriod(HOUR, HOUR + timedelta(hours=1), 0.8),))
    with pytest.raises(PlanningInputError) as error:
        prepare(data)
    assert error.value.code == "pv:coverage_or_resolution_gap"


def test_uniform_pv_model_preserves_hourly_energy_and_marks_unverified():
    data = snapshot(
        now=HOUR,
        periods=(ForecastPeriod(HOUR, HOUR + timedelta(hours=1), 0.8),),
    )
    result = prepare(data, factor=1, pv_temporal_model="uniform_power_unverified")
    assert len(result.quarters) == 4
    assert [q.pv_dc_kwh for q in result.quarters] == pytest.approx([0.2] * 4)
    assert sum(q.pv_dc_kwh for q in result.quarters) == pytest.approx(0.8)
    assert result.pv_temporal_model == "uniform_power_unverified"
    assert result.pv_temporal_modeled_quarters == 4
    assert result.actionable is False


def test_uniform_pv_model_uses_only_remaining_fraction_of_started_hour():
    data = snapshot(
        now=NOW,
        periods=(ForecastPeriod(HOUR, HOUR + timedelta(hours=1), 0.8),),
    )
    result = prepare(data, factor=1, pv_temporal_model="uniform_power_unverified")
    assert len(result.quarters) == 3
    assert sum(q.pv_dc_kwh for q in result.quarters) == pytest.approx(0.6)
    assert result.quarters[0].start == HOUR + QUARTER


def test_misaligned_pv_periods_conserve_energy_across_quarter_boundary():
    data = snapshot(
        now=HOUR,
        periods=(
            ForecastPeriod(HOUR, HOUR + timedelta(minutes=20), 0.4),
            ForecastPeriod(
                HOUR + timedelta(minutes=20), HOUR + timedelta(hours=1), 0.8
            ),
        ),
    )
    result = prepare(data, factor=1, pv_temporal_model="uniform_power_unverified")
    assert [q.pv_dc_kwh for q in result.quarters] == pytest.approx([0.3, 0.3, 0.3, 0.3])
    assert sum(q.pv_dc_kwh for q in result.quarters) == pytest.approx(1.2)


def test_uniform_model_does_not_fill_real_pv_gaps_or_overlaps():
    data = snapshot(
        now=HOUR,
        periods=(
            ForecastPeriod(HOUR, HOUR + timedelta(minutes=20), 0.3),
            ForecastPeriod(
                HOUR + timedelta(minutes=21), HOUR + timedelta(hours=1), 0.7
            ),
        ),
    )
    with pytest.raises(PlanningInputError) as gap:
        prepare(data, pv_temporal_model="uniform_power_unverified")
    assert gap.value.code == "pv:coverage_or_resolution_gap"
    assert gap.value.at == HOUR + QUARTER
    overlapping = snapshot(
        now=HOUR,
        periods=(
            ForecastPeriod(HOUR, HOUR + timedelta(minutes=20), 0.3),
            ForecastPeriod(
                HOUR + timedelta(minutes=19), HOUR + timedelta(hours=1), 0.7
            ),
        ),
    )
    with pytest.raises(PlanningInputError) as overlap:
        prepare(overlapping, pv_temporal_model="uniform_power_unverified")
    assert overlap.value.code == "pv:coverage_or_resolution_gap"


def test_invalid_pv_energy_is_not_silently_normalized():
    data = snapshot(
        now=HOUR,
        periods=(ForecastPeriod(HOUR, HOUR + timedelta(hours=1), -0.8),),
    )
    with pytest.raises(PlanningInputError) as error:
        prepare(data, pv_temporal_model="uniform_power_unverified")
    assert error.value.code == "pv:invalid_number"


def test_exact_15min_pv_periods_do_not_claim_temporal_modeling():
    result = prepare(pv_temporal_model="uniform_power_unverified")
    assert result.pv_temporal_model == "exact_source_periods"
    assert result.pv_temporal_modeled_quarters == 0


def test_two_five_and_one_five_minute_periods_can_sum_to_quarter():
    start = HOUR + QUARTER
    periods = (
        ForecastPeriod(HOUR, HOUR + QUARTER, 0.1),
        ForecastPeriod(start, start + timedelta(minutes=5), 0.1),
        ForecastPeriod(
            start + timedelta(minutes=5), start + timedelta(minutes=10), 0.1
        ),
        ForecastPeriod(start + timedelta(minutes=10), start + QUARTER, 0.1),
        *forecast_quarters(start=start + QUARTER, count=2, kwh=0.2),
    )
    result = prepare(snapshot(periods=periods), factor=1)
    assert result.quarters[0].pv_dc_kwh == pytest.approx(0.3)


def test_forecast_publication_after_decision_is_blocked():
    data = snapshot()
    data.forecast = replace(data.forecast, captured_at=NOW + timedelta(seconds=1))
    with pytest.raises(PlanningInputError) as error:
        prepare(data)
    assert error.value.code == "pv:forecast_from_future"


def test_load_projection_from_future_is_blocked():
    prediction = LoadProjection(
        NOW + timedelta(minutes=1),
        forecast_quarters(),
        "future_leaking_model",
    )
    with pytest.raises(PlanningInputError) as error:
        prepare(load_projection=prediction)
    assert error.value.code == "load:forecast_from_future"


def test_explicit_load_model_replaces_naive_history_proxy():
    prediction = LoadProjection(
        NOW,
        forecast_quarters(kwh=0.6),
        "external_versioned_load_forecast",
    )
    data = snapshot(history=())
    result = prepare(data, load_projection=prediction)
    assert result.quarters[0].home_ac_kwh == pytest.approx(0.6)
    assert result.load_method == "external_versioned_load_forecast"


def test_price_gap_in_published_horizon_is_not_skipped():
    data = snapshot(
        prices=(
            PriceSlot(HOUR, HOUR + timedelta(hours=1), 0.3, 0.4),
            PriceSlot(
                HOUR + timedelta(hours=2),
                HOUR + timedelta(hours=3),
                0.6,
                0.6,
            ),
        )
    )
    with pytest.raises(PlanningInputError) as error:
        prepare(data)
    assert error.value.code == "price:published_gap"


def test_no_price_and_no_pv_forecast_have_distinct_errors():
    with pytest.raises(PlanningInputError) as error:
        prepare(snapshot(prices=()))
    assert error.value.code == "price:not_published"
    data = snapshot()
    data.forecast = None
    with pytest.raises(PlanningInputError) as error:
        prepare(data)
    assert error.value.code == "pv:forecast_missing"


def test_negative_but_published_purchase_price_is_valid():
    data = snapshot(prices=(PriceSlot(HOUR, HOUR + timedelta(hours=1), -0.2, 0.4),))
    assert prepare(data).quarters[0].buy_dkk_per_kwh == -0.2


def test_invalid_price_and_pv_factor_are_blocked():
    data = snapshot(prices=(PriceSlot(HOUR, HOUR + timedelta(hours=1), None, 0.4),))
    with pytest.raises(PlanningInputError) as error:
        prepare(data)
    assert error.value.code == "price:invalid_number"
    with pytest.raises(PlanningInputError) as error:
        prepare(factor=0)
    assert error.value.code == "pv_conversion:zero"


def test_export_not_enabled_implicitly_and_price_ambiguity_blocks_activation():
    assert not prepare().quarters[0].pv_export_enabled
    data = snapshot()
    data.issues.append(Issue("PRICE_THRESHOLD_AMBIGUOUS", "sell"))
    with pytest.raises(PlanningInputError) as error:
        prepare(data, pv_export_enabled=True)
    assert error.value.code == "pv_export:price_ambiguous"


def test_dst_hour_boundary_is_utc_and_has_no_fake_hour():
    autumn = datetime(2026, 10, 25, 0, tzinfo=UTC)
    prices = (PriceSlot(autumn, autumn + timedelta(hours=1), 0.3, 0.41),)
    forecast = tuple(
        ForecastPeriod(
            autumn + i * QUARTER,
            autumn + (i + 1) * QUARTER,
            0.1,
        )
        for i in range(4)
    )
    historical = tuple(
        HistorySlot(
            autumn + i * QUARTER - DAY,
            autumn + (i + 1) * QUARTER - DAY,
            0.1,
            observed_seconds=900,
        )
        for i in range(4)
    )
    data = InputSnapshot(
        at=autumn,
        prices=prices,
        forecast=ForecastSnapshot(autumn, "autumn", forecast),
        history=historical,
    )
    result = prepare(data)
    assert len(result.quarters) == 4
    assert result.price_horizon_end == autumn + timedelta(hours=1)


def test_live_partial_quarter_uses_observed_power_and_excludes_elapsed_energy():
    now = HOUR + timedelta(minutes=7, seconds=30)
    data = snapshot(now=now)
    data.measurements["pv"] = Sample(2500.0, now)
    data.measurements["home"] = Sample(1800.0, now)
    live = prepare(
        data,
        factor=1.0,
        pv_temporal_model="uniform_power_unverified",
        live_partial=True,
    )
    legacy = prepare(data)
    assert live.quarters[0].start == now
    assert live.quarters[0].end == HOUR + QUARTER
    assert live.quarters[1].start == HOUR + QUARTER
    assert live.live_adjusted_quarters >= 4
    assert live.quarters[0].pv_dc_kwh > 0.1
    assert live.quarters[0].home_ac_kwh < 0.3
    assert live.quarters[0].home_ac_kwh > 0.15
    # Old mode must continue selecting complete future quarters.
    assert legacy.quarters[0].start == HOUR + QUARTER


def test_live_partial_quarter_no_measurements_keeps_scaled_forecast():
    now = HOUR + timedelta(minutes=13, seconds=30)
    data = snapshot(now=now)
    live = prepare(
        data,
        factor=1.0,
        pv_temporal_model="uniform_power_unverified",
        live_partial=True,
    )
    assert live.quarters[0].start == now
    assert live.quarters[0].end - live.quarters[0].start == timedelta(seconds=90)
    assert live.quarters[0].home_ac_kwh == pytest.approx(0.03)
    assert live.quarters[0].pv_dc_kwh == pytest.approx(0.02)
    assert live.live_adjusted_quarters == 0
