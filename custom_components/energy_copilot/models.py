"""Immutable, UTC input records; no executor or physical actions."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Issue:
    code: str
    source: str


@dataclass(frozen=True)
class Sample:
    value: float
    at: datetime
    # Local provenance only; standard diagnostics never serialize samples.
    raw_value: float | None = None
    # Oldest supporting source report; never replaces this entity's own report.
    context_at: datetime | None = None


@dataclass(frozen=True)
class PriceSlot:
    start: datetime
    end: datetime
    buy: float
    sell: float


@dataclass(frozen=True)
class ForecastPeriod:
    start: datetime
    end: datetime
    kwh: float


@dataclass(frozen=True)
class ForecastSnapshot:
    captured_at: datetime
    version: str
    periods: tuple[ForecastPeriod, ...]
    source_start: datetime | None = None
    source_end: datetime | None = None
    # Kept for persisted/public snapshot compatibility; end-indexed raw values
    # never imply unbounded future energy at the last timestamp.
    unbounded_energy_at: tuple[datetime, ...] = ()
    unbounded_prior_energy_at: tuple[datetime, ...] = ()
    missing_energy_at: tuple[datetime, ...] = ()
    # Raw forecast edge markers; never inferred from missing provider energy.
    first_watts_zero: bool = False
    last_watts_zero: bool = False
    # Edge-only zero extensions applied to the live planning copy, not archive.
    night_zero_filled_seconds: float = 0.0


@dataclass(frozen=True)
class HistoryGap:
    start: datetime
    end: datetime
    issues: tuple[Issue, ...]


@dataclass(frozen=True)
class HistorySlot:
    start: datetime
    end: datetime
    home_kwh: float | None
    issues: tuple[Issue, ...] = ()
    # Partial energy is only the integral over validated recorded subintervals.
    # It is never a complete-quarter estimate or a verified physical AC load.
    observed_home_kwh: float | None = None
    observed_seconds: float = 0
    unobserved_seconds: float = 0
    unobserved_reason_seconds: tuple[tuple[str, float], ...] = ()
    unobserved_intervals: tuple[HistoryGap, ...] = ()
    unobserved_intervals_truncated: bool = False
    observed_raw_home_kwh: float | None = None
    home_correction_seconds: float = 0
    home_correction_records: int = 0
    home_correction_segments: int = 0
    home_correction_kwh: float = 0


@dataclass
class InputSnapshot:
    at: datetime
    measurements: dict[str, Sample] = field(default_factory=dict)
    flows_kw: dict[str, float] = field(default_factory=dict)
    prices: tuple[PriceSlot, ...] = ()
    forecast: ForecastSnapshot | None = None
    history: tuple[HistorySlot, ...] = ()
    issues: list[Issue] = field(default_factory=list)
