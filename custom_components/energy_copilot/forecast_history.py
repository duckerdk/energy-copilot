"""Bounded original Forecast.Solar observations and replay without future leakage.

HA's response provides no provider generation time. captured_at is the first
completed observation, never an invented provider issuance time.
"""

import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import json as json_helper
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_FORECAST_MAX_VERSIONS,
    DEFAULT_FORECAST_RETENTION_DAYS,
    MAX_FORECAST_RETENTION_DAYS,
    MAX_FORECAST_VERSIONS,
)
from .models import ForecastPeriod, ForecastSnapshot
from .validation import forecast, number, utc

MAX_STORAGE_BYTES = 32 * 1024 * 1024
MAX_SERIES_POINTS = 4096


class ForecastHistory:
    """One Store with shared immutable payloads and bounded observation metadata."""

    def __init__(
        self,
        hass,
        entry_id: str,
        *,
        retention_days=DEFAULT_FORECAST_RETENTION_DAYS,
        max_versions=DEFAULT_FORECAST_MAX_VERSIONS,
    ):
        if (
            type(retention_days) is not int
            or not 1 <= retention_days <= MAX_FORECAST_RETENTION_DAYS
            or type(max_versions) is not int
            or not 1 <= max_versions <= MAX_FORECAST_VERSIONS
        ):
            raise ValueError("invalid_forecast_retention")
        self.hass = hass
        self.store = Store(hass, 1, f"energy_copilot.{entry_id}.forecasts")
        self.retention_days = retention_days
        self.max_versions = max_versions
        self.versions: list[dict] = []
        self.payloads: dict[str, dict] = {}
        self.evicted = 0
        self._dirty = False
        self._lock = asyncio.Lock()

    @staticmethod
    def _digest(payload: dict, source_entry: str | None) -> str:
        return hashlib.sha256(
            json.dumps(
                [source_entry, payload],
                sort_keys=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    @staticmethod
    def _validate_shape(payload: dict) -> None:
        if not isinstance(payload, dict) or set(payload) != {"watts", "wh_period"}:
            raise ValueError("invalid_forecast_response")
        for series in payload.values():
            if not isinstance(series, dict) or not 0 < len(series) <= MAX_SERIES_POINTS:
                raise ValueError("forecast_response_too_large_or_invalid")
            if any(not isinstance(key, str) for key in series):
                raise ValueError("invalid_forecast_timestamp")

    @staticmethod
    def _legacy_snapshot(payload, captured_at, version):
        at = utc(captured_at)
        periods = []
        for item in payload["legacy_periods"]:
            p = ForecastPeriod(
                utc(item["start"]), utc(item["end"]), number(item["kwh"])
            )
            if (
                p.kwh < 0
                or p.start < at
                or p.end <= p.start
                or (periods and p.start < periods[-1].end)
            ):
                raise ValueError("invalid_legacy_forecast")
            periods.append(p)
        if not periods or len(periods) > MAX_SERIES_POINTS:
            raise ValueError("invalid_legacy_forecast")
        return ForecastSnapshot(at, version, tuple(periods))

    def _load_data(self, data, now):
        """Validate persisted data in an executor before replacing live state."""
        if not isinstance(data, dict) or not isinstance(data.get("versions"), list):
            raise ValueError("invalid_forecast_storage")
        migrated = "format" not in data
        if not migrated and data.get("format") != 2:
            raise ValueError("unsupported_forecast_storage")
        if not migrated and not isinstance(data.get("payloads"), dict):
            raise ValueError("invalid_forecast_storage")
        versions, payloads = [], {}
        previous = None
        for row in data["versions"]:
            at = utc(row["captured_at"])
            if at > now or (previous is not None and at < previous):
                raise ValueError("invalid_forecast_capture_time")
            if migrated:
                payload = {"legacy_periods": deepcopy(row["periods"])}
                source = None
                version = self._digest(payload, source)
                self._legacy_snapshot(payload, at, version)
            else:
                source = row["source_entry"]
                if source is not None and (not isinstance(source, str) or not source):
                    raise ValueError("invalid_forecast_source")
                version = row["version"]
                payload = data["payloads"][version]
                if "legacy_periods" in payload:
                    if source is not None:
                        raise ValueError("invalid_legacy_source")
                    self._legacy_snapshot(payload, at, version)
                else:
                    if source is None:
                        raise ValueError("invalid_forecast_source")
                    self._validate_shape(payload)
                    forecast(payload, at)
                if self._digest(payload, source) != version:
                    raise ValueError("invalid_forecast_digest")
            previous = at
            payloads[version] = deepcopy(payload)
            versions.append(
                {
                    "captured_at": at.isoformat(),
                    "version": version,
                    "source_entry": source,
                }
            )
        cleaned = (
            migrated
            or versions != data["versions"]
            or set(payloads) != set(data.get("payloads", {}))
        )
        return versions, payloads, cleaned

    async def async_load(self, now: datetime) -> None:
        async with self._lock:
            data = await self.store.async_load()
            if data is None:
                return
            try:
                versions, payloads, migrated = await self.hass.async_add_executor_job(
                    self._load_data, data, utc(now)
                )
            except (KeyError, TypeError, ValueError, OverflowError) as err:
                raise HomeAssistantError("invalid_forecast_storage") from err
            self.versions, self.payloads = versions, payloads
            self._dirty = migrated
            self._prune_metadata(now)
            # Apply byte cap on every load, even when settings did not change.
            await self._async_save_if_dirty(check_size=True)

    def _data(self) -> dict:
        # Copy containers: executor sizing/pruning never mutates state seen by replay.
        return {
            "format": 2,
            "versions": list(self.versions),
            "payloads": dict(self.payloads),
        }

    @staticmethod
    def _collect_payloads(data):
        keep = {row["version"] for row in data["versions"]}
        data["payloads"] = {
            key: value for key, value in data["payloads"].items() if key in keep
        }

    def _serialized_size(self, data):
        # Include Store's envelope and actual HA pretty JSON encoding in the cap.
        _, serialized = json_helper.prepare_save_json(
            {
                "version": self.store.version,
                "minor_version": self.store.minor_version,
                "key": self.store.key,
                "data": data,
            }
        )
        return len(
            serialized.encode("utf-8") if isinstance(serialized, str) else serialized
        )

    def _bound_size(self, data):
        before = len(data["versions"])
        while data["versions"] and self._serialized_size(data) > MAX_STORAGE_BYTES:
            del data["versions"][: max(1, len(data["versions"]) // 10)]
            ForecastHistory._collect_payloads(data)
        return data, before - len(data["versions"])

    def _prune_metadata(self, now: datetime) -> None:
        cutoff = utc(now) - timedelta(days=self.retention_days)
        # No full serialization/rewrites for unchanged polls with no expired rows.
        if not self.versions or (
            utc(self.versions[0]["captured_at"]) >= cutoff
            and len(self.versions) <= self.max_versions
        ):
            return
        before = len(self.versions)
        self.versions = [r for r in self.versions if utc(r["captured_at"]) >= cutoff][
            -self.max_versions :
        ]
        data = self._data()
        self._collect_payloads(data)
        self.payloads = data["payloads"]
        self.evicted += before - len(self.versions)
        self._dirty = True

    async def async_prune(self, now: datetime) -> None:
        async with self._lock:
            self._prune_metadata(now)
            await self._async_save_if_dirty()

    async def _async_save_if_dirty(self, *, check_size=False) -> None:
        if not self._dirty and not check_size:
            return
        data, removed = await self.hass.async_add_executor_job(
            self._bound_size, self._data()
        )
        if removed:
            self.versions, self.payloads = data["versions"], data["payloads"]
            self.evicted += removed
            self._dirty = True
        if self._dirty:
            await self.store.async_save(data)
            self._dirty = False

    def _prepare(self, response, captured_at, source_entry):
        payload = {k: deepcopy(response[k]) for k in ("watts", "wh_period")}
        self._validate_shape(payload)
        snapshot = forecast(payload, captured_at)
        if len(json.dumps(payload, allow_nan=False).encode()) > MAX_STORAGE_BYTES // 2:
            raise ValueError("forecast_response_too_large")
        return payload, snapshot, self._digest(payload, source_entry)

    async def async_record(
        self, response: dict, captured_at: datetime, source_entry: str
    ) -> ForecastSnapshot:
        captured_at = utc(captured_at)
        if not isinstance(source_entry, str) or not source_entry:
            raise ValueError("invalid_forecast_source")
        async with self._lock:
            payload, snapshot, version = await self.hass.async_add_executor_job(
                self._prepare, response, captured_at, source_entry
            )
            if self.versions and captured_at < utc(self.versions[-1]["captured_at"]):
                raise ValueError("nonmonotonic_forecast_capture")
            self._prune_metadata(captured_at)
            if not self.versions or self.versions[-1]["version"] != version:
                self.payloads[version] = payload
                self.versions.append(
                    {
                        "captured_at": captured_at.isoformat(),
                        "version": version,
                        "source_entry": source_entry,
                    }
                )
                self._dirty = True
            self._prune_metadata(captured_at)
            await self._async_save_if_dirty()
            # Live validity is evaluated at receipt time. Stored availability is
            # the first observation, even if identical values are polled again.
            return replace(snapshot, version=version)

    def _record_at(self, decision_at, source_entry=None):
        at = utc(decision_at)
        return next(
            (
                row
                for row in reversed(self.versions)
                if utc(row["captured_at"]) <= at
                and (source_entry is None or row["source_entry"] == source_entry)
            ),
            None,
        )

    def as_of(
        self, decision_at: datetime, *, source_entry=None
    ) -> ForecastSnapshot | None:
        """Latest retained observation known then, never a future revision."""
        if (row := self._record_at(decision_at, source_entry)) is None:
            return None
        payload = self.payloads[row["version"]]
        if "legacy_periods" in payload:
            # These periods were normalized by the incorrect start-index parser.
            # Without the original end-index Wh map they cannot be repaired safely.
            return None
        return replace(
            forecast(payload, utc(row["captured_at"])), version=row["version"]
        )

    def original_at(self, decision_at: datetime, *, source_entry=None) -> dict | None:
        """Original W/Wh values/site timezone keys; legacy originals cannot be invented."""
        row = self._record_at(decision_at, source_entry)
        if row is None or "legacy_periods" in self.payloads[row["version"]]:
            return None
        return deepcopy(self.payloads[row["version"]])

    @property
    def summary(self):
        return {
            "retention_days": self.retention_days,
            "max_versions": self.max_versions,
            "max_storage_bytes": MAX_STORAGE_BYTES,
            "versions": len(self.versions),
            "distinct_payloads": len(self.payloads),
            "oldest_captured_at": self.versions[0]["captured_at"]
            if self.versions
            else None,
            "newest_captured_at": self.versions[-1]["captured_at"]
            if self.versions
            else None,
            "legacy_versions_without_originals": sum(
                row["source_entry"] is None for row in self.versions
            ),
            "evicted_this_runtime": self.evicted,
            "provider_generated_at_available": False,
            "interval_semantics": "end_timestamp",
            "legacy_replay_supported": False,
        }
