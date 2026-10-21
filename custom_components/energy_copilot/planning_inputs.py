"""M3 read-only adapter: published prices, PV intervals and auditable load proxy.

No interpolation, assumed-zero data, device writes or TOU executability claims.
A previous-UTC-day load projection is an unverified model, not a measurement.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

from .models import ForecastPeriod, InputSnapshot
from .planner import QUARTER, Quarter

DAY = timedelta(days=1)
SECONDS_PER_QUARTER = QUARTER.total_seconds()


class PlanningInputError(ValueError):
    """Missing or unverifiable input, with the first affected quarter."""

    def __init__(self, code: str, at: datetime | None = None):
        self.code = code
        self.at = at
        super().__init__(f"{code}:{at.isoformat()}" if at else code)


@dataclass(frozen=True)
class LoadProjection:
    captured_at: datetime
    periods: tuple[ForecastPeriod, ...]
    method: str
    physical_accuracy_verified: bool = False


@dataclass(frozen=True)
class PlanningInput:
    quarters: tuple[Quarter, ...]
    price_horizon_end: datetime
    pv_forecast_version: str
    pv_forecast_to_dc_multiplier: float
    load_method: str
    # Incomplete physical calibration and Deye's six TOUs forbid execution.
    actionable: bool = False


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise PlanningInputError(f"{label}:timezone_missing")
    if value.utcoffset() is None:
        raise PlanningInputError(f"{label}:timezone_missing")
    return value.astimezone(UTC)


def _amount(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanningInputError(f"{label}:invalid_number")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise PlanningInputError(f"{label}:invalid_number")
    return number


def project_previous_utc_day_load(snapshot: InputSnapshot) -> LoadProjection:
    """Project complete, validated Recorder quarters exactly 24h forward.

    UTC repeat deliberately does not claim local-time DST or weather correction.
    Gaps remain gaps, and this fallback is not approved for device control.
    """
    now = _utc(snapshot.at, "decision")
    periods = []
    seen = set()
    for slot in snapshot.history:
        start = _utc(slot.start, "history")
        end = _utc(slot.end, "history")
        if end > now or end - start != QUARTER:
            continue
        if slot.home_kwh is None:
            continue
        if (
            slot.observed_seconds < SECONDS_PER_QUARTER - 1e-6
            or slot.unobserved_seconds > 1e-6
        ):
            continue
        if start in seen:
            raise PlanningInputError("load:duplicate_history", start)
        energy = _amount(slot.home_kwh, "load")
        periods.append(ForecastPeriod(start + DAY, end + DAY, energy))
        seen.add(start)
    return LoadProjection(
        now,
        tuple(sorted(periods, key=lambda period: period.start)),
        method="previous_24h_utc_unverified",
    )


def _exact_quarter_energy(
    periods: tuple[ForecastPeriod, ...],
    start: datetime,
    end: datetime,
    source: str,
) -> float:
    """Integrate only whole, adjacent source periods inside a future quarter."""
    cursor = start
    total = 0.0
    for p in periods:
        left = _utc(p.start, source)
        right = _utc(p.end, source)
        if right <= start:
            continue
        if left >= end:
            break
        if left != cursor or right > end or right <= left:
            raise PlanningInputError(f"{source}:coverage_or_resolution_gap", start)
        total += _amount(p.kwh, source)
        cursor = right
    if cursor != end:
        raise PlanningInputError(f"{source}:coverage_or_resolution_gap", start)
    return total


def build_planning_input(
    snapshot: InputSnapshot,
    *,
    pv_forecast_to_dc_multiplier: float,
    load_projection: LoadProjection | None = None,
    pv_export_enabled: bool = False,
) -> PlanningInput:
    """Prepare all complete future 15-minute quarters up to published price end.

    The PV conversion factor is required because Forecast.Solar production basis
    is not independently confirmed as the PV DC measurement basis. No assumed
    conversion efficiency or zero-filled forecast is introduced.
    """
    now = _utc(snapshot.at, "decision")
    multiplier = _amount(pv_forecast_to_dc_multiplier, "pv_conversion")
    if multiplier <= 0:
        raise PlanningInputError("pv_conversion:zero")
    if not isinstance(pv_export_enabled, bool):
        raise PlanningInputError("pv_export:invalid_flag")
    if pv_export_enabled and any(
        issue.code == "PRICE_THRESHOLD_AMBIGUOUS" for issue in snapshot.issues
    ):
        raise PlanningInputError("pv_export:price_ambiguous")
    if snapshot.forecast is None:
        raise PlanningInputError("pv:forecast_missing")
    if _utc(snapshot.forecast.captured_at, "pv_forecast") > now:
        raise PlanningInputError("pv:forecast_from_future")
    if not snapshot.prices:
        raise PlanningInputError("price:not_published")
    prices = sorted(snapshot.prices, key=lambda price: _utc(price.start, "price"))
    first = _utc(prices[0].start, "price")
    last = _utc(prices[-1].end, "price")
    for index, price in enumerate(prices):
        left = _utc(price.start, "price")
        right = _utc(price.end, "price")
        if right - left != timedelta(hours=1):
            raise PlanningInputError("price:invalid_hour", left)
        if index and left != _utc(prices[index - 1].end, "price"):
            raise PlanningInputError("price:published_gap", left)
        _amount(price.buy, "buy_price") if price.buy >= 0 else _finite_price(price.buy)
        _finite_price(price.sell)
    start = now.replace(second=0, microsecond=0)
    if start < now or start.minute % 15:
        start += timedelta(minutes=(15 - start.minute % 15))
    if not first <= start < last:
        raise PlanningInputError("price:missing_current_future_quarter", start)
    projection = load_projection or project_previous_utc_day_load(snapshot)
    if _utc(projection.captured_at, "load_forecast") > now:
        raise PlanningInputError("load:forecast_from_future")
    if not projection.method:
        raise PlanningInputError("load:model_missing")
    pv_periods = tuple(
        sorted(snapshot.forecast.periods, key=lambda period: _utc(period.start, "pv"))
    )
    load_periods = tuple(
        sorted(projection.periods, key=lambda period: _utc(period.start, "load"))
    )
    quarters = []
    price_index = 0
    cursor = start
    while cursor < last:
        right = cursor + QUARTER
        while price_index < len(prices) and _utc(prices[price_index].end, "price") <= cursor:
            price_index += 1
        if (
            price_index == len(prices)
            or _utc(prices[price_index].start, "price") > cursor
            or _utc(prices[price_index].end, "price") < right
        ):
            raise PlanningInputError("price:coverage_gap", cursor)
        price = prices[price_index]
        pv_energy = _exact_quarter_energy(pv_periods, cursor, right, "pv")
        load_energy = _exact_quarter_energy(load_periods, cursor, right, "load")
        quarters.append(
            Quarter(
                cursor,
                right,
                _finite_price(price.buy),
                _finite_price(price.sell),
                pv_energy * multiplier,
                load_energy,
                pv_export_enabled,
            )
        )
        cursor = right
    if not quarters:
        raise PlanningInputError("price:no_complete_future_quarters")
    return PlanningInput(
        tuple(quarters),
        last,
        snapshot.forecast.version,
        multiplier,
        projection.method,
    )


def _finite_price(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanningInputError("price:invalid_number")
    number = float(value)
    if not isfinite(number):
        raise PlanningInputError("price:invalid_number")
    return number
