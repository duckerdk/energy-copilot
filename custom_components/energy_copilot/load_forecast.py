"""Seven-day household load model built from validated hourly HA statistics.

Forecasts and historical profiles are estimates; no inverter writes or new database.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import exp, isfinite
from zoneinfo import ZoneInfo

from .models import ForecastPeriod
from .planner import QUARTER
from .planning_inputs import LoadProjection, PlanningInputError

LOCAL = ZoneInfo("Europe/Copenhagen")
LOOKBACK_DAYS = 45
HORIZON_DAYS = 7
MIN_TRAINING_HOURS = 96
MIN_TRAINING_DATES = 7
MODEL_NAME = "historical_45d_recency_14d_workday_hybrid_v2_unverified"


@dataclass(frozen=True)
class HourlyLoad:
    start: datetime
    kwh: float


@dataclass(frozen=True)
class LoadModel:
    trained_at: datetime
    samples: tuple[HourlyLoad, ...]
    source: str
    distinct_days: int
    by_local_hour: tuple[tuple[HourlyLoad, ...], ...]


@dataclass(frozen=True)
class SevenDayForecast:
    projection: LoadProjection
    hourly: tuple[HourlyLoad, ...]
    source: str
    training_hours: int
    training_days: int
    status: str = "ready"

    @property
    def total_kwh(self) -> float:
        return sum(period.kwh for period in self.projection.periods)


def _easter(year: int) -> date:
    """Gregorian computus; no service, internet or external calendar dependency."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    weekday_offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday_offset) // 451
    month = (h + weekday_offset - 7 * m + 114) // 31
    day = ((h + weekday_offset - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def danish_public_holidays(year: int) -> frozenset[date]:
    """National DK holidays; personal holidays / leave cannot be inferred."""
    easter = _easter(year)
    return frozenset(
        {date(year, 1, 1), date(year, 12, 25), date(year, 12, 26)}
        | {easter + timedelta(days=offset) for offset in (-3, -2, 0, 1, 39, 49, 50)}
    )


def _day_type(day: date, overrides: dict[date, bool] | None = None) -> str:
    if overrides is not None and day in overrides:
        return "workday" if overrides[day] else "free"
    if day.weekday() >= 5 or day in danish_public_holidays(day.year):
        return "free"
    return "workday"


def train_load_model(
    rows: tuple[HourlyLoad, ...],
    now: datetime,
    source: str,
) -> LoadModel:
    """Ignore missing/invalid hours; require independent calendar days."""
    if now.tzinfo is None:
        raise PlanningInputError("load:timezone_missing")
    now = now.astimezone(UTC)
    history_start = now - timedelta(days=LOOKBACK_DAYS)
    accepted: dict[datetime, HourlyLoad] = {}
    for row in rows:
        at = row.start
        if at.tzinfo is None:
            continue
        at = at.astimezone(UTC)
        if at < history_start or at + timedelta(hours=1) > now:
            continue
        if at.minute or at.second or at.microsecond:
            continue
        if not isinstance(row.kwh, (float, int)) or isinstance(row.kwh, bool):
            continue
        if not isfinite(row.kwh) or row.kwh < 0:
            continue
        if at in accepted:
            raise PlanningInputError("load:duplicate_hour", at)
        accepted[at] = HourlyLoad(at, float(row.kwh))
    ordered = tuple(accepted[t] for t in sorted(accepted))
    days = {row.start.astimezone(LOCAL).date() for row in ordered}
    if len(ordered) < MIN_TRAINING_HOURS or len(days) < MIN_TRAINING_DATES:
        raise PlanningInputError("load:insufficient_hourly_statistics")
    hour_buckets = tuple(
        tuple(row for row in ordered if row.start.astimezone(LOCAL).hour == hour)
        for hour in range(24)
    )
    return LoadModel(now, ordered, source, len(days), hour_buckets)


def _weighted_median(samples: list[tuple[float, float]]) -> float:
    sorted_values = sorted(samples, key=lambda item: item[0])
    halfway = sum(weight for _, weight in sorted_values) / 2
    cumulative = 0.0
    for value, weight in sorted_values:
        cumulative += weight
        if cumulative >= halfway:
            return value
    return sorted_values[-1][0]


def _weighted_mean(samples: list[tuple[float, float]]) -> float:
    total = sum(weight for _, weight in samples)
    if total <= 0:
        raise ValueError("load:invalid_weights")
    return sum(value * weight for value, weight in samples) / total


def _predict_hour(
    model: LoadModel,
    at: datetime,
    overrides: dict[date, bool] | None,
) -> float:
    local = at.astimezone(LOCAL)
    target_type = _day_type(local.date(), overrides)
    same_weekday = []
    same_type = []
    any_day = []
    recent_type = []
    for sample in model.by_local_hour[local.hour]:
        historic = sample.start.astimezone(LOCAL)
        age_days = max(0.0, (model.trained_at - sample.start).total_seconds() / 86400)
        # Distinct recency bands make a real change in the last week
        # visible in the forecast; all samples still belong to the last 45 d.
        band = 6.0 if age_days <= 7 else 3.0 if age_days <= 14 else 1.0
        weight = band * exp(-age_days / 30)
        element = (sample.kwh, weight)
        any_day.append(element)
        if _day_type(historic.date(), overrides) == target_type:
            same_type.append(element)
            if age_days <= 14:
                recent_type.append(element)
            if historic.weekday() == local.weekday():
                same_weekday.append(element)
    if len(same_weekday) >= 3 and len(same_type) >= 6:
        baseline = 0.35 * _weighted_median(same_weekday) + 0.65 * _weighted_median(
            same_type
        )
    elif len(same_type) >= 4:
        baseline = _weighted_median(same_type)
    elif len(any_day) >= 4:
        baseline = _weighted_median(any_day)
    else:
        raise PlanningInputError("load:hour_profile_missing", at)
    # Median-only estimators can ignore a new week-long usage pattern.
    # Blend recent same-day-type hourly energy into the robust baseline.
    if len(recent_type) >= 3:
        return max(0.0, 0.7 * _weighted_mean(recent_type) + 0.3 * baseline)
    return baseline


def forecast_seven_days(
    model: LoadModel,
    now: datetime,
    *,
    workday_overrides: dict[date, bool] | None = None,
) -> SevenDayForecast:
    """Return a UTC quarter-hour series plus an hourly chart series.

    7 * 24 hours from the next complete 15-minute boundary. Local classification
    uses Europe/Copenhagen, including spring/autumn clock changes.
    """
    if now.tzinfo is None:
        raise PlanningInputError("load:timezone_missing")
    now = now.astimezone(UTC)
    start = now.replace(second=0, microsecond=0)
    if start < now or start.minute % 15:
        start += timedelta(minutes=(15 - start.minute % 15))
    end = start + timedelta(days=HORIZON_DAYS)
    quarter_rows = []
    grouped: dict[datetime, float] = defaultdict(float)
    cache: dict[datetime, float] = {}
    cursor = start
    while cursor < end:
        hour = cursor.replace(minute=0)
        if hour not in cache:
            cache[hour] = _predict_hour(model, hour, workday_overrides)
        energy = cache[hour] / 4.0
        quarter_rows.append(ForecastPeriod(cursor, cursor + QUARTER, energy))
        grouped[hour] += energy
        cursor += QUARTER
    return SevenDayForecast(
        projection=LoadProjection(
            captured_at=now,
            periods=tuple(quarter_rows),
            method=MODEL_NAME,
        ),
        hourly=tuple(HourlyLoad(hour, grouped[hour]) for hour in sorted(grouped)),
        source=model.source,
        training_hours=len(model.samples),
        training_days=model.distinct_days,
    )


def backtest_recent_load(model: LoadModel, days: int = 7) -> dict:
    """Out-of-sample hourly walk-forward check with no future training leakage.

    Train as of the holdout start, then predict the held-out historical hours
    using that frozen model. This is statistical accuracy, not independent
    physical confirmation of the original home-energy measurement.
    """
    cutoff = model.trained_at - timedelta(days=days)
    train = tuple(
        row for row in model.samples if row.start + timedelta(hours=1) <= cutoff
    )
    test = tuple(row for row in model.samples if cutoff <= row.start < model.trained_at)
    result = {
        "method": "holdout_previous_7_days_train_only_older_data",
        "source": model.source,
        "physical_consumption_verified": False,
        "hours_evaluated": 0,
        "mae_kwh_per_hour": None,
        "bias_kwh_per_hour": None,
        "positive_underprediction_p75_kwh_per_hour": None,
        "peak_positive_underprediction_p75_kwh_per_hour": None,
        "peak_bias_kwh_per_hour": None,
        "peak_hours_evaluated": 0,
        "mape_percent_nonzero_hours": None,
    }
    if not test:
        return result
    try:
        frozen = train_load_model(train, cutoff, model.source)
    except PlanningInputError:
        return result
    residuals = []
    peak_residuals = []
    relative = []
    for row in test:
        try:
            predicted = _predict_hour(frozen, row.start, None)
        except PlanningInputError:
            continue
        error = predicted - row.kwh
        residuals.append(error)
        # Daylight and nighttime must not dilute the evening-risk signal.
        if 16 <= row.start.astimezone(LOCAL).hour < 22:
            peak_residuals.append(error)
        if row.kwh >= 0.05:
            relative.append(abs(predicted - row.kwh) / row.kwh)
    if residuals:

        def positive_p75(errors):
            values = sorted(max(0.0, -err) for err in errors)
            return values[min(len(values) - 1, int(0.75 * len(values)))]

        result.update(
            hours_evaluated=len(residuals),
            mae_kwh_per_hour=sum(abs(v) for v in residuals) / len(residuals),
            bias_kwh_per_hour=sum(residuals) / len(residuals),
            positive_underprediction_p75_kwh_per_hour=positive_p75(residuals),
            peak_positive_underprediction_p75_kwh_per_hour=(
                positive_p75(peak_residuals) if len(peak_residuals) >= 16 else None
            ),
            peak_bias_kwh_per_hour=(
                sum(peak_residuals) / len(peak_residuals)
                if len(peak_residuals) >= 16
                else None
            ),
            peak_hours_evaluated=len(peak_residuals),
            mape_percent_nonzero_hours=(
                100 * sum(relative) / len(relative) if relative else None
            ),
        )
    return result
