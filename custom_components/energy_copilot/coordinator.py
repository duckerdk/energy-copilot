"""Read-only HA adapters. Forecast retrieval is the only service invocation."""

import asyncio
import logging
from datetime import timedelta
from functools import partial

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
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
from .live_measurements import (
    WATCHED_ROLES,
    LiveMeasurementWindow,
    LiveSourceContext,
    derived_templates,
)
from .load_forecast import forecast_seven_days
from .load_statistics import LoadStatisticsError, LoadStatisticsReader
from .models import InputSnapshot, Issue
from .planning_inputs import PlanningInputError
from .planning_preview import Preview, evaluate_preview
from .quality import quality_report
from .solar import complete_night_forecast_edges, solar_evidence
from .validation import forecast, measurement, measurements, prices

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
        self.load_statistics_reader = LoadStatisticsReader(
            hass, self.entities, self.settings.get("load_statistic")
        )
        self.load_model = None
        self.load_forecast = None
        self.load_forecast_error = "load:awaiting_statistics"
        self._last_load_training = None
        self._external_issues = []
        self._last_external = None
        self.forecast_coverage = None
        self.measurement_source_timing = {}
        self.quality = None
        self.planning_preview = None
        self.live_context = LiveSourceContext()
        self.live_window = LiveMeasurementWindow()

    async def _async_setup(self):
        # State-change events preserve short outages between the 30-second polls.
        @callback
        def source_changed(event):
            for role in WATCHED_ROLES:
                if self.entities[role] == event.data["entity_id"]:
                    self.live_context.observe(
                        role,
                        event.data["new_state"],
                        dt_util.utcnow(),
                    )

        self.config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass,
                [self.entities[role] for role in WATCHED_ROLES if self.entities[role]],
                source_changed,
            )
        )
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
        templates = derived_templates(self.hass, self.entities)
        self.measurement_source_timing = {}
        timing_roles = HISTORY_ROLES
        for role in timing_roles:
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
        for role in WATCHED_ROLES:
            if self.entities[role]:
                self.live_context.observe(role, states[role], now)
        snapshot.measurements, snapshot.flows_kw, snapshot.issues = measurements(
            states,
            now,
            source_recovery_at=self.live_context.recovery_at,
            derived_templates=templates,
        )
        for role, timing in self.measurement_source_timing.items():
            sample = snapshot.measurements.get(role)
            try:
                measurement(role, states[role], now)
            except ValueError:
                self_report_valid = False
            else:
                self_report_valid = True
            timing.update(
                {
                    "self_report_valid": self_report_valid,
                    "accepted": sample is not None,
                    "issue_codes": sorted(
                        {i.code for i in snapshot.issues if i.source == role}
                    ),
                    "native_state_template": role in templates,
                    "context_oldest_report_utc": sample.context_at.isoformat()
                    if sample and sample.context_at
                    else None,
                    "configured_sources": list(templates.get(role, ())),
                    "configured_source_issues": {
                        r: sorted({i.code for i in snapshot.issues if i.source == r})
                        for r in templates.get(role, ())
                        if r not in snapshot.measurements
                    },
                    "recovery_pending_sources": sorted(
                        r
                        for r in templates.get(role, ())
                        if r in self.live_context.recovery_at
                        and (
                            sample is None
                            or self.live_context.recovery_at[r] is None
                            or sample.at < self.live_context.recovery_at[r]
                        )
                    ),
                    "template_dependency_graph_verified": False,
                }
            )
            if sample and sample.context_at:
                timing["freshness_time_basis"] = "validated_configured_sources"
        self.live_context.accept_home(snapshot.measurements.get("home"))
        self.live_window.record(states, now, snapshot.measurements, snapshot.issues)
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
            if (
                self._last_load_training is None
                or now - self._last_load_training >= timedelta(hours=12)
            ):
                await self._async_train_load(now)
            self._last_external = now
        snapshot.forecast = self._forecast
        snapshot.history = self._history
        snapshot.issues.extend(self._external_issues)
        if self._forecast and max(p.end for p in self._forecast.periods) <= now:
            snapshot.forecast = None
            snapshot.issues.append(Issue("stale_forecast", "forecast_solar"))
        self.forecast_coverage = None
        if snapshot.forecast:
            # Use the selected PV location, never an unrelated default HA location.
            solar_entry = self.hass.config_entries.async_get_entry(
                self.settings.get("forecast_entry", "")
            )
            solar = None
            if snapshot.prices:
                solar = solar_evidence(
                    solar_entry.data if solar_entry else {},
                    min(
                        max(now, snapshot.prices[0].start),
                        snapshot.forecast.source_start or now,
                    ),
                    snapshot.prices[-1].end,
                    dt_util.utcnow(),
                )
                # Only the live planning copy gains solar-confirmed zero-energy
                # night edges. Stored provider payload and replay stay pristine.
                snapshot.forecast = complete_night_forecast_edges(
                    snapshot.forecast,
                    solar,
                    max(now, snapshot.prices[0].start),
                    snapshot.prices[-1].end,
                )
                solar["zero_energy_inserted"] = (
                    snapshot.forecast.night_zero_filled_seconds > 0
                )
            self.forecast_coverage = forecast_coverage(
                snapshot.forecast, snapshot.prices, now, solar=solar
            )
            if self.forecast_coverage["missing_intervals"]:
                snapshot.issues.append(
                    Issue("forecast_horizon_incomplete", "forecast_solar")
                )
            if self.forecast_coverage["unpublished_night_seconds"]:
                snapshot.issues.append(
                    Issue("forecast_night_unpublished", "forecast_solar")
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
        # Forecast.Solar may have completed after the initial coordinator tick.
        # Evaluate a snapshot only when its observation is already available.
        snapshot.at = dt_util.utcnow()
        self.load_forecast = None
        if self.load_model is not None:
            try:
                self.load_forecast = forecast_seven_days(self.load_model, snapshot.at)
                self.load_forecast_error = None
            except PlanningInputError as err:
                self.load_forecast_error = err.code
        try:
            if (
                self.settings.get("mode", "monitor") == "dry_run"
                and self.load_forecast is None
                and snapshot.forecast is not None
            ):
                self.planning_preview = Preview(
                    "blocked", self.load_forecast_error or "load:forecast_missing"
                )
            else:
                self.planning_preview = await self.hass.async_add_executor_job(
                    partial(
                        evaluate_preview,
                        snapshot,
                        mode=self.settings.get("mode", "monitor"),
                        pv_export_enabled=solar_sell is not None
                        and solar_sell.state == "on",
                        load_projection=(
                            self.load_forecast.projection
                            if self.load_forecast
                            else None
                        ),
                    )
                )
        except Exception:  # Preview must never interrupt reliable M1/M2 polling.
            _LOGGER.exception("M3 read-only preview failed")
            self.planning_preview = Preview("blocked", "planner:internal_error")
        self.quality = quality_report(snapshot.issues, self.forecast_coverage)
        if self.planning_preview.status == "preview":
            readiness = "experimental_m3_preview_only"
        elif self.planning_preview.status == "blocked":
            readiness = "m3_preview_blocked"
        else:
            readiness = "not_evaluated_m2"
        self.quality["planning_readiness"] = readiness
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
        # A configured template/measurement has not established physical AC demand.
        self._external_issues.append(Issue("home_profile_unverified", "home"))
        if self.history_reader.last_read_summary.get("home_normalization", {}).get(
            "corrected_seconds", 0
        ):
            self._external_issues.append(Issue("negative_home_normalized", "recorder"))

    async def _async_train_load(self, now):
        """Refresh long-term statistics periodically, never on each 30s poll."""
        self._last_load_training = now
        try:
            self.load_model = await self.load_statistics_reader.async_train(now)
            self.load_forecast_error = None
        except LoadStatisticsError as err:
            self.load_model = None
            self.load_forecast_error = err.code
        except Exception:
            _LOGGER.exception("Seven-day historical load training failed")
            self.load_model = None
            self.load_forecast_error = "load:statistics_internal_error"
