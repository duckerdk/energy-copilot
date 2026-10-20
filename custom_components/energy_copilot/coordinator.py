"""Read-only HA adapters. Forecast retrieval is the only service invocation."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_ENTITIES,
    DEFAULT_FORECAST_MAX_VERSIONS,
    DEFAULT_FORECAST_RETENTION_DAYS,
    DOMAIN,
    HISTORY_ROLES,
    OPTIONAL_ENTITY_ROLES,
    UPDATE_INTERVAL,
)
from .forecast_history import ForecastHistory
from .forecast_quality import forecast_coverage
from .history import HistoryReadError, RecorderHistoryReader
from .models import InputSnapshot, Issue
from .validation import forecast, measurements, prices

_LOGGER = logging.getLogger(__name__)


class EnergyCoordinator(DataUpdateCoordinator[InputSnapshot]):
    def __init__(self, hass: HomeAssistant, entry):
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=UPDATE_INTERVAL,
        )
        self.settings = {**entry.data, **entry.options}
        self.entities = {
            role: self.settings.get(role, default)
            for role, default in DEFAULT_ENTITIES.items()
        }
        self.forecast_history = ForecastHistory(
            hass,
            entry.entry_id,
            retention_days=self.settings.get(
                "forecast_retention_days", DEFAULT_FORECAST_RETENTION_DAYS
            ),
            max_versions=self.settings.get(
                "forecast_max_versions", DEFAULT_FORECAST_MAX_VERSIONS
            ),
        )
        self.history_reader = RecorderHistoryReader(hass, self.entities)
        self._archive_available = True
        self._forecast = None
        self._history = ()
        self._external_issues = []
        self._last_external = None
        self.forecast_coverage = None
        self.measurement_source_timing = {}

    async def _async_setup(self):
        try:
            await self.forecast_history.async_load(dt_util.utcnow())
        except HomeAssistantError:
            # Preserve an unreadable/unknown store; do not overwrite it.
            self._archive_available = False

    async def _async_update_data(self):
        now = dt_util.utcnow()
        snapshot = InputSnapshot(now)
        states = {
            role: self.hass.states.get(entity_id) if entity_id else None
            for role, entity_id in self.entities.items()
        }
        self.measurement_source_timing = {}
        for role in HISTORY_ROLES:
            state = states[role]
            reported = getattr(state, "last_reported", None)
            updated = getattr(state, "last_updated", None)
            self.measurement_source_timing[role] = {
                "backend": "python_state",
                "freshness_time_basis": "last_reported",
                "last_reported_utc": reported.isoformat()
                if reported is not None
                else None,
                "last_updated_utc": updated.isoformat()
                if updated is not None
                else None,
                "report_age_seconds": (now - reported).total_seconds()
                if reported is not None
                else None,
                "available": state is not None
                and state.state not in {"unknown", "unavailable"},
            }
        snapshot.measurements, snapshot.flows_kw, snapshot.issues = measurements(
            states, now
        )
        for role in OPTIONAL_ENTITY_ROLES:
            if not self.entities[role]:
                snapshot.issues.append(Issue("optional_entity_unconfigured", role))
        snapshot.prices, issues = prices(states["buy"], states["sell"], now)
        snapshot.issues.extend(issues)
        solar_sell_id = self.settings.get("solar_sell", "switch.sun12k_solar_sell")
        solar_sell = self.hass.states.get(solar_sell_id) if solar_sell_id else None
        if not solar_sell_id:
            snapshot.issues.append(Issue("optional_entity_unconfigured", "solar_sell"))
        soc = snapshot.measurements.get("soc")
        if solar_sell is None or solar_sell.state not in {"on", "off"}:
            snapshot.issues.append(Issue("invalid_input", "solar_sell"))
        elif soc and soc.value >= 99 and solar_sell.state == "off":
            snapshot.issues.append(Issue("possible_curtailment", "pv"))
        # Recorder and forecast are slower sources; no repeated database scans on sensor polls.
        if self._last_external is None or now - self._last_external >= timedelta(
            minutes=15
        ):
            self._external_issues = []
            if self._archive_available:
                try:
                    await self.forecast_history.async_prune(now)
                except HomeAssistantError:
                    self._external_issues.append(
                        Issue("forecast_storage_failed", "forecast_solar")
                    )
            else:
                self._external_issues.append(
                    Issue("forecast_storage_unavailable", "forecast_solar")
                )
            await self._async_forecast(now)
            await self._async_history(now)
            self._last_external = now
        snapshot.forecast = self._forecast
        snapshot.history = self._history
        snapshot.issues.extend(self._external_issues)
        if self._forecast and max(p.end for p in self._forecast.periods) <= now:
            snapshot.forecast = None
            snapshot.issues.append(Issue("stale_forecast", "forecast_solar"))
        self.forecast_coverage = None
        if snapshot.forecast:
            self.forecast_coverage = forecast_coverage(
                snapshot.forecast, snapshot.prices, now
            )
            if self.forecast_coverage["missing_intervals"]:
                snapshot.issues.append(
                    Issue("forecast_horizon_incomplete", "forecast_solar")
                )
            if self.forecast_coverage["partially_elapsed_periods"]:
                snapshot.issues.append(
                    Issue("forecast_observed_after_period_start", "forecast_solar")
                )
            if snapshot.forecast.unbounded_energy_at:
                snapshot.issues.append(
                    Issue("forecast_energy_boundary_unverifiable", "forecast_solar")
                )
            if snapshot.forecast.missing_energy_at:
                snapshot.issues.append(
                    Issue("forecast_energy_period_missing", "forecast_solar")
                )
        return snapshot

    async def _async_forecast(self, now):
        self._forecast = None
        entry_id = self.settings.get("forecast_entry")
        entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        if entry is None or entry.domain != "forecast_solar":
            self._external_issues.append(
                Issue("forecast_entry_missing", "forecast_solar")
            )
            return
        try:
            async with asyncio.timeout(30):
                response = await self.hass.services.async_call(
                    "forecast_solar",
                    "get_forecast",
                    {"config_entry": entry_id, "resolution": "raw"},
                    blocking=True,
                    return_response=True,
                )
            # Availability is the response time, not the request start time.
            now = dt_util.utcnow()
            self._forecast = forecast(response, now)
        except HomeAssistantError, ValueError, TypeError, OverflowError, TimeoutError:
            self._external_issues.append(
                Issue("forecast_unavailable_or_invalid", "forecast_solar")
            )
            return
        if self._archive_available:
            try:
                self._forecast = await self.forecast_history.async_record(
                    response, now, entry_id
                )
            except HomeAssistantError:
                self._external_issues.append(
                    Issue("forecast_storage_failed", "forecast_solar")
                )
            except ValueError, TypeError, OverflowError:
                self._external_issues.append(
                    Issue("forecast_history_invalid", "forecast_solar")
                )

    @property
    def versions(self):
        """Retained observation metadata, without duplicating original payloads."""
        return self.forecast_history.versions

    async def _async_history(self, now):
        self._history = ()
        end = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
        start = end - timedelta(days=1)
        try:
            self._history = await self.history_reader.async_read_window(start, end)
        except HistoryReadError as err:
            self._external_issues.append(Issue(err.code, "recorder"))
            return
        # RecorderRuns show process boundaries, not a durable history of recorder.disable.
        # Reconstructed state coverage must not be presented as proven continuous recording.
        if not self.history_reader.last_read_summary.get(
            "recording_pause_history_verified", False
        ):
            self._external_issues.append(
                Issue("recorder_pause_history_unverifiable", "recorder")
            )
        if any(s.home_kwh is None for s in self._history):
            self._external_issues.append(
                Issue("historical_quality_unverifiable", "recorder")
            )
