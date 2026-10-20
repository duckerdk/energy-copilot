"""Read-only HA adapters. Forecast retrieval is the only service invocation."""

import asyncio
import logging
from datetime import timedelta
from functools import partial

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DEFAULT_ENTITIES, DOMAIN, HISTORY_ROLES, UPDATE_INTERVAL
from .models import InputSnapshot, Issue
from .validation import forecast, history_slots, measurements, prices

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
        self.forecast_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.forecasts")
        self.versions: list[dict] = []
        self._forecast = None
        self._history = ()
        self._external_issues = []
        self._last_external = None

    async def _async_setup(self):
        stored = await self.forecast_store.async_load()
        if isinstance(stored, dict) and isinstance(stored.get("versions"), list):
            self.versions = stored["versions"][-48:]

    async def _async_update_data(self):
        now = dt_util.utcnow()
        snapshot = InputSnapshot(now)
        states = {
            role: self.hass.states.get(entity_id)
            for role, entity_id in self.entities.items()
        }
        snapshot.measurements, snapshot.flows_kw, snapshot.issues = measurements(
            states, now
        )
        snapshot.prices, issues = prices(states["buy"], states["sell"], now)
        snapshot.issues.extend(issues)
        solar_sell = self.hass.states.get(
            self.settings.get("solar_sell", "switch.sun12k_solar_sell")
        )
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
            await self._async_forecast(now)
            await self._async_history(now)
            self._last_external = now
        snapshot.forecast = self._forecast
        snapshot.history = self._history
        snapshot.issues.extend(self._external_issues)
        if self._forecast and max(p.end for p in self._forecast.periods) <= now:
            snapshot.forecast = None
            snapshot.issues.append(Issue("stale_forecast", "forecast_solar"))
        if snapshot.forecast and snapshot.prices:
            for slot in snapshot.prices:
                covered = sum(
                    max(
                        0,
                        (
                            min(p.end, slot.end) - max(p.start, slot.start)
                        ).total_seconds(),
                    )
                    for p in snapshot.forecast.periods
                )
                if covered < (slot.end - slot.start).total_seconds():
                    snapshot.issues.append(
                        Issue("forecast_horizon_incomplete", "forecast_solar")
                    )
                    break
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
        self.versions.append(
            {
                "captured_at": now.isoformat(),
                "version": self._forecast.version,
                "periods": [
                    {
                        "start": p.start.isoformat(),
                        "end": p.end.isoformat(),
                        "kwh": p.kwh,
                    }
                    for p in self._forecast.periods
                ],
            }
        )
        self.versions = self.versions[-48:]
        try:
            await self.forecast_store.async_save({"versions": self.versions})
        except HomeAssistantError:
            self._external_issues.append(
                Issue("forecast_storage_failed", "forecast_solar")
            )

    async def _async_history(self, now):
        self._history = ()
        if "recorder" not in self.hass.config.components:
            self._external_issues.append(Issue("recorder_unavailable", "recorder"))
            return
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.history import get_significant_states
        from sqlalchemy.exc import SQLAlchemyError

        # Only complete UTC quarter hours, bounded to 24h; full attributes required for units.
        end = now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)
        start = end - timedelta(days=1)
        try:
            rows = await get_instance(self.hass).async_add_executor_job(
                partial(
                    get_significant_states,
                    self.hass,
                    start,
                    end,
                    entity_ids=[self.entities[r] for r in HISTORY_ROLES],
                    include_start_time_state=True,
                    significant_changes_only=False,
                    minimal_response=False,
                    no_attributes=False,
                )
            )
            self._history = await self.hass.async_add_executor_job(
                history_slots,
                rows,
                self.entities,
                start,
                end,
            )
        except HomeAssistantError, SQLAlchemyError, ValueError, TypeError:
            self._external_issues.append(Issue("recorder_query_failed", "recorder"))
            return
        if any(s.home_kwh is None for s in self._history):
            self._external_issues.append(
                Issue("historical_quality_unverifiable", "recorder")
            )
