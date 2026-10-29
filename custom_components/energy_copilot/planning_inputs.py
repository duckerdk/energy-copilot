"""M3 read-only adapter: published prices, PV intervals and auditable load proxy.

No historical samples are changed or zero-filled; no device writes.
The optional short-gap interpolation affects future load predictions only.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite

from .models import ForecastPeriod, InputSnapshot
from .planner import QUARTER, Quarter

DAY = timedelta(days=1)
SECONDS_PER_QUARTER = QUARTER.total_seconds()
MAX_MODELED_LOAD_GAP_QUARTERS = 3


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
    modeled_quarters: int = 0


@dataclass(frozen=True)
class PlanningInput:
    quarters: tuple[Quarter, ...]
    price_horizon_end: datetime
    pv_forecast_version: str
    pv_forecast_to_dc_multiplier: float
    load_method: str
    pv_temporal_model: str = "exact_source_periods"
    pv_temporal_modeled_quarters: int = 0
    load_modeled_quarters: int = 0
    live_adjusted_quarters: int = 0
    # Incomplete physical calibration and Deye's six TOUs forbid execution.
    actionable: bool = False
    coverage_status: str = "complete"
    first_missing_code: str | None = None
    first_missing_at: datetime | None = None


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


def project_previous_utc_day_load(
    snapshot: InputSnapshot, *, short_gap_model: str | None = None
) -> LoadProjection:
    """Repeat the previous UTC day's verified load as an unverified forecast.

    In opt-in dry-run mode, short runs of missing Recorder quarters may be
    linearly modeled in the *future projection* using both adjacent fully
    observed quarters. Original Recorder records remain missing. Long gaps,
    absent boundaries and source uncertainty never become assumed zero.
    """
    if short_gap_model not in (None, "linear_bracketed_unverified"):
        raise PlanningInputError("load:invalid_short_gap_model")
    now = _utc(snapshot.at, "decision")
    available_starts: set[datetime] = set()
    recorded: dict[datetime, float] = {}
    for slot in snapshot.history:
        start = _utc(slot.start, "history")
        end = _utc(slot.end, "history")
        if end > now or end - start != QUARTER:
            continue
        if start in available_starts:
            raise PlanningInputError("load:duplicate_history", start)
        available_starts.add(start)
        if slot.home_kwh is None:
            continue
        if (
            slot.observed_seconds < SECONDS_PER_QUARTER - 1e-6
            or slot.unobserved_seconds > 1e-6
        ):
            continue
        recorded[start] = _amount(slot.home_kwh, "load")

    modeled: dict[datetime, float] = {}
    if short_gap_model == "linear_bracketed_unverified":
        processed: set[datetime] = set()
        for start in sorted(available_starts):
            if start in recorded or start in processed:
                continue
            missing = []
            cursor = start
            while cursor in available_starts and cursor not in recorded:
                missing.append(cursor)
                processed.add(cursor)
                cursor += QUARTER
            left = start - QUARTER
            if (
                len(missing) > MAX_MODELED_LOAD_GAP_QUARTERS
                or left not in recorded
                or cursor not in recorded
            ):
                continue
            before, after = recorded[left], recorded[cursor]
            for index, target in enumerate(missing, start=1):
                modeled[target] = before + (after - before) * (
                    index / (len(missing) + 1)
                )
    forecast = {**recorded, **modeled}
    periods = tuple(
        ForecastPeriod(start + DAY, start + DAY + QUARTER, energy)
        for start, energy in sorted(forecast.items())
    )
    return LoadProjection(
        now,
        periods,
        method=(
            "previous_24h_utc_linear_bracketed_gap_model_unverified"
            if modeled
            else "previous_24h_utc_unverified"
        ),
        modeled_quarters=len(modeled),
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


def _modeled_quarter_pv_energy(
    periods: tuple[ForecastPeriod, ...], start: datetime, end: datetime
) -> tuple[float, bool]:
    """Integrate published PV energy with a declared constant-power model.

    The source period's kWh is preserved, not copied to every quarter.
    Partial intersections are estimates, never verified intraperiod forecasts.
    A missing interval or overlapping source periods still fail closed.
    """
    cursor = start
    total = 0.0
    modeled = False
    for period in periods:
        left = _utc(period.start, "pv")
        right = _utc(period.end, "pv")
        if right <= start:
            continue
        if left >= end:
            break
        if right <= left:
            raise PlanningInputError("pv:invalid_period", start)
        overlap_start = max(left, start)
        overlap_end = min(right, end)
        if overlap_start != cursor or overlap_end <= overlap_start:
            raise PlanningInputError("pv:coverage_or_resolution_gap", start)
        total += _amount(period.kwh, "pv") * (
            (overlap_end - overlap_start).total_seconds()
            / (right - left).total_seconds()
        )
        modeled |= overlap_start != left or overlap_end != right
        cursor = overlap_end
    if cursor != end:
        raise PlanningInputError("pv:coverage_or_resolution_gap", start)
    return total, modeled


def build_planning_input(
    snapshot: InputSnapshot,
    *,
    pv_forecast_to_dc_multiplier: float,
    load_projection: LoadProjection | None = None,
    pv_export_enabled: bool = False,
    allow_prefix: bool = False,
    pv_temporal_model: str | None = None,
    live_partial: bool = False,
) -> PlanningInput:
    """Prepare all complete future 15-minute quarters up to published price end.

    The PV conversion factor is required because Forecast.Solar production basis
    is not independently confirmed as the PV DC measurement basis. No assumed
    conversion efficiency or zero-filled forecast is introduced.
    """
    now = _utc(snapshot.at, "decision")
    if pv_temporal_model not in (None, "uniform_power_unverified"):
        raise PlanningInputError("pv:invalid_temporal_model")
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
        _finite_price(price.buy)
        _finite_price(price.sell)
    aligned = now.replace(
        minute=now.minute // 15 * 15, second=0, microsecond=0
    )
    start = now if live_partial else aligned
    if not live_partial and start < now:
        start += QUARTER
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
    modeled_pv_quarters = 0
    live_adjusted_quarters = 0
    first_gap = None
    price_index = 0
    cursor = start
    while cursor < last:
        base_start = cursor.replace(
            minute=cursor.minute // 15 * 15, second=0, microsecond=0
        )
        right = base_start + QUARTER
        fraction = (right - cursor).total_seconds() / QUARTER.total_seconds()
        while (
            price_index < len(prices)
            and _utc(prices[price_index].end, "price") <= cursor
        ):
            price_index += 1
        if (
            price_index == len(prices)
            or _utc(prices[price_index].start, "price") > cursor
            or _utc(prices[price_index].end, "price") < right
        ):
            raise PlanningInputError("price:coverage_gap", cursor)
        price = prices[price_index]
        try:
            if pv_temporal_model == "uniform_power_unverified":
                pv_energy, modeled_pv = _modeled_quarter_pv_energy(
                    pv_periods, cursor, right
                )
            else:
                pv_energy = _exact_quarter_energy(pv_periods, cursor, right, "pv")
                modeled_pv = False
            if fraction < 1.0 - 1e-10:
                # Only the remaining energy of the current quarter is
                # controllable: elapsed household consumption is excluded.
                load_energy = (
                    _exact_quarter_energy(load_periods, base_start, right, "load")
                    * fraction
                )
            else:
                load_energy = _exact_quarter_energy(load_periods, cursor, right, "load")
        except PlanningInputError as error:
            if not allow_prefix or not quarters:
                raise
            first_gap = error
            break
        modeled_pv_quarters += int(modeled_pv)
        forecast_pv_dc_kwh = pv_energy * multiplier
        if live_partial:
            # Bounded live power nowcast; use real PV and house demand in
            # the remaining active quarter, then fade the correction.
            index = len(quarters)
            weight = (0.65, 0.30, 0.15)[index] if index < 3 else 0.0
            if weight:
                hours = (right - cursor).total_seconds() / 3600.0
                measured_pv = snapshot.measurements.get("pv")
                measured_home = snapshot.measurements.get("home")
                if measured_pv is not None:
                    forecast_rate = forecast_pv_dc_kwh / hours
                    live_rate = max(0.0, measured_pv.value / 1000.0)
                    adjusted_rate = forecast_rate + weight * max(
                        -3.0, min(3.0, live_rate - forecast_rate)
                    )
                    forecast_pv_dc_kwh = max(0.0, adjusted_rate * hours)
                    live_adjusted_quarters += 1
                if measured_home is not None:
                    forecast_rate = load_energy / hours
                    live_rate = max(0.0, measured_home.value / 1000.0)
                    adjusted_rate = forecast_rate + weight * max(
                        -3.0, min(3.0, live_rate - forecast_rate)
                    )
                    load_energy = max(0.0, adjusted_rate * hours)
                    live_adjusted_quarters += 1
        quarters.append(
            Quarter(
                cursor,
                right,
                _finite_price(price.buy),
                _finite_price(price.sell),
                forecast_pv_dc_kwh,
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
        pv_temporal_model=(
            "uniform_power_unverified"
            if modeled_pv_quarters
            else "exact_source_periods"
        ),
        pv_temporal_modeled_quarters=modeled_pv_quarters,
        load_modeled_quarters=projection.modeled_quarters,
        live_adjusted_quarters=live_adjusted_quarters,
        coverage_status="partial" if first_gap is not None else "complete",
        first_missing_code=first_gap.code if first_gap is not None else None,
        first_missing_at=first_gap.at if first_gap is not None else None,
    )


def _finite_price(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PlanningInputError("price:invalid_number")
    number = float(value)
    if not isfinite(number):
        raise PlanningInputError("price:invalid_number")
    return number
