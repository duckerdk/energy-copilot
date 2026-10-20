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
from .home_quality import negative_home_audit
from .models import HistorySlot
from .recorder_reconstruction import RecordingRun, reconstruct_history
from .validation import number, utc

CHUNK_DURATION = timedelta(days=1)
MAX_HISTORY_RANGE = timedelta(days=366)
QUARTER = timedelta(minutes=15)
MAX_AUDIT_INTERVALS = 96


def rejection_audit(slots, runs=()):
    """Bounded interval evidence without values or private household time series.

    Reason counts overlap: one quarter can contain both a negative home sample
    and a run gap. Only the union equals the number of rejected quarters.
    """
    rejected = [slot for slot in slots if slot.home_kwh is None]
    by_reason = Counter(
        code for slot in rejected for code in {i.code for i in slot.issues}
    )
    negative = {
        slot.start
        for slot in rejected
        if any(i.code == "negative_home_power" for i in slot.issues)
    }
    gaps = {
        slot.start
        for slot in rejected
        if any(i.code == "recorder_recording_gap" for i in slot.issues)
    }
    return {
        "rejected_slots": len(rejected),
        "rejected_intervals": [
            {
                "start_utc": slot.start.isoformat(),
                "end_utc": slot.end.isoformat(),
                "observed_seconds": slot.observed_seconds,
                "unobserved_seconds": slot.unobserved_seconds,
                "unobserved_reason_seconds": dict(slot.unobserved_reason_seconds),
                "unobserved_intervals": [
                    {
                        "start_utc": gap.start.isoformat(),
                        "end_utc": gap.end.isoformat(),
                        "issues": [
                            {"code": i.code, "source": i.source} for i in gap.issues
                        ],
                    }
                    for gap in slot.unobserved_intervals
                ],
                "unobserved_intervals_truncated": slot.unobserved_intervals_truncated,
                "issues": [
                    {"code": issue.code, "source": issue.source}
                    for issue in slot.issues
                ],
            }
            for slot in rejected[:MAX_AUDIT_INTERVALS]
        ],
        "rejected_intervals_truncated": len(rejected) > MAX_AUDIT_INTERVALS,
        "rejection_reason_slots": dict(sorted(by_reason.items())),
        "negative_home_and_recording_gap_slots": len(negative & gaps),
        "negative_home_or_recording_gap_slots": len(negative | gaps),
        "recording_runs": [
            {
                "start_utc": run.start.isoformat(),
                "recorded_end_utc": run.recorded_end.isoformat()
                if run.recorded_end is not None
                else None,
                "effective_end_utc": run.end.isoformat(),
                "closed_incorrect": not run.reliable,
            }
            for run in runs[:MAX_AUDIT_INTERVALS]
        ],
        "recording_runs_truncated": len(runs) > MAX_AUDIT_INTERVALS,
    }


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
            "source_rows": {},
            "status": "reading",
            "reconstruction_method": "piecewise_constant_recorder_states",
            "device_freshness_verified": False,
            "recording_pause_history_verified": False,
            "historical_filter_changes_verified": False,
            "history_source_format": "ha_backend_state",
            "negative_home_records_in_window": 0,
            "negative_home_audit": None,
            "rejected_slots": 0,
            "rejected_intervals": [],
            "rejected_intervals_truncated": False,
            "rejection_reason_slots": {},
            "negative_home_and_recording_gap_slots": 0,
            "negative_home_or_recording_gap_slots": 0,
            "recording_runs": [],
            "recording_runs_truncated": False,
            "whole_slot_policy": "complete_observed_quarter_required",
            "partial_energy_extrapolated": False,
            "physical_consumption_verified": False,
            "observed_seconds": 0.0,
            "unobserved_seconds": 0.0,
            "unobserved_reason_seconds": {},
            "observed_time_fraction": 0.0,
            "partial_slots": 0,
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
        for key in ("observed_seconds", "unobserved_seconds", "partial_slots"):
            summary[key] += chunk[key]
        summary["observed_time_fraction"] = summary["observed_seconds"] / (
            summary["requested_slots"] * QUARTER.total_seconds()
        )
        summary["unobserved_reason_seconds"] = dict(
            Counter(summary["unobserved_reason_seconds"])
            + Counter(chunk["unobserved_reason_seconds"])
        )
        summary["negative_home_audit_last_chunk"] = chunk["negative_home_audit"]
        summary["configured_retention_days"] = chunk["configured_retention_days"]
        summary["source_rows_last_chunk"] = chunk["source_rows"]
        summary["negative_home_records_in_window"] += chunk[
            "negative_home_records_in_window"
        ]
        summary["rejected_slots"] += chunk["rejected_slots"]
        summary["rejection_reason_slots"] = dict(
            Counter(summary["rejection_reason_slots"])
            + Counter(chunk["rejection_reason_slots"])
        )
        for key in (
            "negative_home_and_recording_gap_slots",
            "negative_home_or_recording_gap_slots",
        ):
            summary[key] += chunk[key]
        # Multi-month backfills retain only the latest chunk's bounded interval audit.
        summary["rejected_intervals_last_chunk"] = chunk["rejected_intervals"]
        summary["rejected_intervals_last_chunk_truncated"] = chunk[
            "rejected_intervals_truncated"
        ]
        summary["recording_runs_last_chunk"] = chunk["recording_runs"]
        summary["recording_runs_last_chunk_truncated"] = chunk[
            "recording_runs_truncated"
        ]
        summary["recording_intervals_read"] = (
            summary.get("recording_intervals_read", 0)
            + chunk["recording_intervals_read"]
        )
        summary["uncertain_recording_intervals"] = (
            summary.get("uncertain_recording_intervals", 0)
            + chunk["uncertain_recording_intervals"]
        )
        summary["excluded_sources"] = sorted(
            set(summary.get("excluded_sources", ())) | set(chunk["excluded_sources"])
        )
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
        from sqlalchemy.exc import SQLAlchemyError

        async with self._lock:
            if self._closed:
                raise HistoryReadError("history_reader_closed")
            if "recorder" not in self.hass.config.components:
                raise HistoryReadError("recorder_unavailable")
            try:
                instance = get_instance(self.hass)
                if getattr(instance, "enabled", True) is False:
                    raise HistoryReadError("recorder_disabled")
                rows, runs, excluded_roles = await instance.async_add_executor_job(
                    partial(self._query_recorded_states, start, end)
                )
                # Decoding rows and interval reconstruction happen off the HA loop.
                (
                    slots,
                    bounds,
                    source_rows,
                    home_audit,
                ) = await self.hass.async_add_executor_job(
                    self._validate_rows, rows, start, end, runs, excluded_roles
                )
            except HistoryReadError:
                raise
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
            source_rows=source_rows,
            recording_intervals_read=len(runs),
            uncertain_recording_intervals=sum(not run.reliable for run in runs),
            excluded_sources=list(excluded_roles),
            issue_counts=dict(Counter(i.code for slot in slots for i in slot.issues)),
            issue_sources=dict(
                Counter(f"{i.source}:{i.code}" for slot in slots for i in slot.issues)
            ),
        )
        summary.update(rejection_audit(slots, runs))
        summary["negative_home_audit"] = home_audit
        summary["observed_seconds"] = sum(s.observed_seconds for s in slots)
        summary["unobserved_seconds"] = sum(s.unobserved_seconds for s in slots)
        reason_seconds = Counter()
        for slot in slots:
            reason_seconds.update(dict(slot.unobserved_reason_seconds))
        summary["unobserved_reason_seconds"] = dict(sorted(reason_seconds.items()))
        summary["observed_time_fraction"] = (
            summary["observed_seconds"] / (end - start).total_seconds()
        )
        summary["partial_slots"] = sum(
            s.observed_seconds > 0 and s.unobserved_seconds > 0 for s in slots
        )
        summary["negative_home_records_in_window"] = source_rows.get("home", {}).get(
            "negative_power_records_in_window", 0
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

    def _query_recorded_states(self, start, end):
        """Read changes, real carry-in timestamps and run coverage in one DB job."""
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import get_significant_states

        if getattr(get_instance(self.hass), "enabled", True) is False:
            raise HistoryReadError("recorder_disabled")
        rows = get_significant_states(
            self.hass,
            start,
            end,
            entity_ids=list(self.entities.values()),
            include_start_time_state=False,
            significant_changes_only=False,
            minimal_response=False,
            no_attributes=False,
        )
        return self._read_recording_context(rows, start, end)

    def _read_recording_context(self, rows, start, end):
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.db_schema import (
            SHARED_ATTR_OR_LEGACY_ATTRIBUTES,
            RecorderRuns,
            StateAttributes,
            States,
            StatesMeta,
        )
        from homeassistant.components.recorder.models import (
            LazyState,
            process_timestamp,
        )
        from homeassistant.components.recorder.util import session_scope
        from sqlalchemy import or_, select

        # Native include_start_time_state replaces the original timestamp with
        # query start. Fetch at most one indexed boundary row per source instead.
        with session_scope(hass=self.hass, read_only=True) as session:
            for entity_id in self.entities.values():
                row = session.execute(
                    select(
                        States.state,
                        States.last_updated_ts,
                        States.last_changed_ts,
                        SHARED_ATTR_OR_LEGACY_ATTRIBUTES,
                    )
                    .join(StatesMeta, States.metadata_id == StatesMeta.metadata_id)
                    .outerjoin(
                        StateAttributes,
                        States.attributes_id == StateAttributes.attributes_id,
                    )
                    .where(
                        StatesMeta.entity_id == entity_id,
                        States.last_updated_ts <= start.timestamp(),
                    )
                    .order_by(States.last_updated_ts.desc())
                    .limit(1)
                ).first()
                if row is not None:
                    carry = LazyState(
                        {}, None, entity_id, row[0], row[1], row[3], row[2]
                    )
                    rows.setdefault(entity_id, []).insert(0, carry)
            raw_runs = session.execute(
                select(
                    RecorderRuns.start, RecorderRuns.end, RecorderRuns.closed_incorrect
                )
                .where(
                    RecorderRuns.start < end,
                    or_(RecorderRuns.end.is_(None), RecorderRuns.end > start),
                )
                .order_by(RecorderRuns.start)
            ).all()
            runs = tuple(
                RecordingRun(
                    process_timestamp(row[0]),
                    min(process_timestamp(row[1]) or end, end),
                    not row[2],
                    process_timestamp(row[1]),
                )
                for row in raw_runs
            )
        instance = get_instance(self.hass)
        entity_filter = getattr(instance, "entity_filter", None)
        excluded = tuple(
            role
            for role, entity_id in self.entities.items()
            if entity_filter is not None and not entity_filter(entity_id)
        )
        return rows, runs, excluded

    def _validate_rows(
        self, rows: dict, start: datetime, end: datetime, runs=(), excluded_roles=()
    ):
        slots = reconstruct_history(
            rows, self.entities, start, end, runs, excluded_roles
        )
        # Exclude carry-in states from claims about the observed retention window.
        first, last = None, None
        source_rows = {}
        for role, entity_id in self.entities.items():
            timestamps = [utc(state.last_updated) for state in rows.get(entity_id, ())]
            changes = [at for at in timestamps if start <= at < end]
            carry = [at for at in timestamps if at < start]
            source_rows[role] = {
                "changes_in_window": len(changes),
                "carry_in_at": max(carry).isoformat() if carry else None,
                "first_change_at": min(changes).isoformat() if changes else None,
                "last_change_at": max(changes).isoformat() if changes else None,
            }
            if role == "home":
                negative = 0
                for state in rows.get(entity_id, ()):
                    if not start <= utc(state.last_updated) < end:
                        continue
                    if state.attributes.get("unit_of_measurement") != "W":
                        continue
                    try:
                        negative += number(state.state) < 0
                    except TypeError, ValueError, OverflowError:
                        pass
                source_rows[role]["negative_power_records_in_window"] = negative
            if changes:
                first = min(first, min(changes)) if first is not None else min(changes)
                last = max(last, max(changes)) if last is not None else max(changes)
        bounds = (
            first.isoformat() if first else None,
            last.isoformat() if last else None,
        )
        return (
            slots,
            bounds,
            source_rows,
            negative_home_audit(rows, self.entities, start, end, runs, excluded_roles),
        )

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
