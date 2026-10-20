"""Bounded, on-demand Recorder reads without a second historical database."""

import asyncio
from collections import Counter
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from functools import partial

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import HISTORY_ROLES
from .models import HistorySlot
from .validation import history_slots, utc

CHUNK_DURATION = timedelta(days=1)
MAX_HISTORY_RANGE = timedelta(days=366)
QUARTER = timedelta(minutes=15)


class HistoryReadError(HomeAssistantError):
    """A source/lifecycle failure with a diagnostic code, without private data."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RecorderHistoryReader:
    """Stream validated UTC quarter hours; the caller owns iteration lifetime.

    Construction and coordinator updates do not trigger historical backfills.
    Each requested chunk is queried only when the caller asks for the next one.
    No raw states or multi-month slot collection is retained by this reader.
    """

    def __init__(self, hass: HomeAssistant, entities: dict[str, str]) -> None:
        self.hass = hass
        self.entities = {role: entities[role] for role in HISTORY_ROLES}
        self.last_read_summary: dict | None = None
        self.last_backfill_summary: dict | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    def _validate_range(
        self, start: datetime, end: datetime, maximum: timedelta
    ) -> tuple[datetime, datetime]:
        if self._closed:
            raise HistoryReadError("history_reader_closed")
        if not isinstance(start, datetime) or not isinstance(end, datetime):
            raise ValueError("history_datetime_required")
        start, end = utc(start), utc(end)
        if any(t.minute % 15 or t.second or t.microsecond for t in (start, end)):
            raise ValueError("history_quarter_hour_required")
        if end <= start or end - start > maximum:
            raise ValueError("history_range_out_of_bounds")
        # No forecast/learning code can accidentally ask this reader for future rows.
        if end > dt_util.utcnow():
            raise ValueError("history_future_range")
        return start, end

    @staticmethod
    def _new_summary(start: datetime, end: datetime) -> dict:
        return {
            "requested_start": start.isoformat(),
            "requested_end": end.isoformat(),
            "queried_until": start.isoformat(),
            "requested_slots": int((end - start) / QUARTER),
            "returned_slots": 0,
            "valid_slots": 0,
            "coverage_fraction": 0.0,
            "chunks_read": 0,
            "configured_retention_days": None,
            "observed_first": None,
            "observed_last": None,
            "issue_counts": {},
            "issue_sources": {},
            "status": "reading",
        }

    @staticmethod
    def _include(summary: dict, chunk: dict) -> None:
        summary["queried_until"] = chunk["requested_end"]
        summary["returned_slots"] += chunk["returned_slots"]
        summary["valid_slots"] += chunk["valid_slots"]
        summary["coverage_fraction"] = (
            summary["valid_slots"] / summary["requested_slots"]
        )
        summary["chunks_read"] += 1
        summary["configured_retention_days"] = chunk["configured_retention_days"]
        if first := chunk["observed_first"]:
            summary["observed_first"] = min(summary["observed_first"] or first, first)
        if last := chunk["observed_last"]:
            summary["observed_last"] = max(summary["observed_last"] or last, last)
        summary["issue_counts"] = dict(
            Counter(summary["issue_counts"]) + Counter(chunk["issue_counts"])
        )
        summary["issue_sources"] = dict(
            Counter(summary["issue_sources"]) + Counter(chunk["issue_sources"])
        )

    async def _async_query(
        self, start: datetime, end: datetime
    ) -> tuple[tuple[HistorySlot, ...], dict]:
        if "recorder" not in self.hass.config.components:
            raise HistoryReadError("recorder_unavailable")
        # Lazy imports keep Recorder optional and avoid requiring its packages when absent.
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import get_significant_states
        from sqlalchemy.exc import SQLAlchemyError

        async with self._lock:
            if self._closed:
                raise HistoryReadError("history_reader_closed")
            if "recorder" not in self.hass.config.components:
                raise HistoryReadError("recorder_unavailable")
            try:
                instance = get_instance(self.hass)
                rows = await instance.async_add_executor_job(
                    partial(
                        get_significant_states,
                        self.hass,
                        start,
                        end,
                        entity_ids=list(self.entities.values()),
                        include_start_time_state=True,
                        significant_changes_only=False,
                        minimal_response=False,
                        no_attributes=False,
                    )
                )
                # Decoding lazy Recorder states and integration happen off the event loop.
                slots, bounds = await self.hass.async_add_executor_job(
                    self._validate_rows, rows, start, end
                )
            except (HomeAssistantError, SQLAlchemyError, ValueError, TypeError) as err:
                raise HistoryReadError("recorder_query_failed") from err
            if self._closed:
                raise HistoryReadError("history_reader_closed")
        summary = self._new_summary(start, end)
        summary.update(
            queried_until=end.isoformat(),
            returned_slots=len(slots),
            valid_slots=sum(slot.home_kwh is not None for slot in slots),
            chunks_read=1,
            observed_first=bounds[0],
            observed_last=bounds[1],
            issue_counts=dict(Counter(i.code for slot in slots for i in slot.issues)),
            issue_sources=dict(
                Counter(f"{i.source}:{i.code}" for slot in slots for i in slot.issues)
            ),
        )
        # A setting is not proof that rows covering that duration actually exist.
        retention = getattr(instance, "keep_days", None)
        if isinstance(retention, int) and not isinstance(retention, bool):
            summary["configured_retention_days"] = retention
        summary["coverage_fraction"] = (
            summary["valid_slots"] / summary["requested_slots"]
        )
        summary["status"] = "completed"
        return slots, summary

    def _validate_rows(self, rows: dict, start: datetime, end: datetime):
        slots = history_slots(rows, self.entities, start, end)
        # Exclude carry-in states from claims about the observed retention window.
        first, last = None, None
        for entity_id in self.entities.values():
            for state in rows.get(entity_id, ()):
                at = utc(state.last_updated)
                if start <= at < end:
                    first = min(first, at) if first is not None else at
                    last = max(last, at) if last is not None else at
        bounds = (
            first.isoformat() if first else None,
            last.isoformat() if last else None,
        )
        return slots, bounds

    async def async_read_window(
        self, start: datetime, end: datetime
    ) -> tuple[HistorySlot, ...]:
        """Read at most one day for recent diagnostics; never start a backfill."""
        start, end = self._validate_range(start, end, CHUNK_DURATION)
        summary = self._new_summary(start, end)
        self.last_read_summary = summary
        try:
            slots, result = await self._async_query(start, end)
        except asyncio.CancelledError:
            summary["status"] = "cancelled"
            raise
        except HistoryReadError as err:
            summary.update(status="failed", error=err.code)
            raise
        summary.update(result)
        return slots

    async def async_iter_slots(
        self, start: datetime, end: datetime
    ) -> AsyncIterator[tuple[HistorySlot, ...]]:
        """Yield on demand in <=24h chunks, with a hard 366-day request bound.

        Consumers should close the iterator on early exit (e.g. contextlib.aclosing).
        This does not run a model, create a second database, or extend Recorder retention.
        """
        start, end = self._validate_range(start, end, MAX_HISTORY_RANGE)
        summary = self._new_summary(start, end)
        self.last_backfill_summary = summary
        cursor = start
        try:
            while cursor < end:
                stop = min(cursor + CHUNK_DURATION, end)
                slots, chunk = await self._async_query(cursor, stop)
                self._include(summary, chunk)
                cursor = stop
                if cursor == end:
                    summary["status"] = "completed"
                yield slots
        except asyncio.CancelledError:
            summary["status"] = "cancelled"
            raise
        except HistoryReadError as err:
            summary.update(status="failed", error=err.code)
            raise
        finally:
            if summary["status"] == "reading":
                summary["status"] = "incomplete"

    async def async_close(self) -> None:
        """Stop new reads/chunks after unload; no background task is owned here."""
        self._closed = True
