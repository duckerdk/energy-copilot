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


@dataclass(frozen=True)
class HistorySlot:
    start: datetime
    end: datetime
    home_kwh: float | None
    issues: tuple[Issue, ...] = ()


@dataclass
class InputSnapshot:
    at: datetime
    measurements: dict[str, Sample] = field(default_factory=dict)
    flows_kw: dict[str, float] = field(default_factory=dict)
    prices: tuple[PriceSlot, ...] = ()
    forecast: ForecastSnapshot | None = None
    history: tuple[HistorySlot, ...] = ()
    issues: list[Issue] = field(default_factory=list)
