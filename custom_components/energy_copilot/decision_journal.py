"""Persistent, bounded, local audit of planner and executor decisions.

This is an operational audit, not a raw household measurement history.
"""

import json
import logging
from datetime import timedelta
from uuid import uuid4

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
RETENTION_DAYS = 30
MAX_EVENTS = 6000


class DecisionJournal:
    """Keep explainable decisions across HA restarts without bloating entity states."""

    def __init__(self, hass, entry_id):
        self.store = Store(hass, 1, f"{DOMAIN}.{entry_id}.decisions")
        self.entries = []
        self.available = True
        self.error = None

    async def async_load(self):
        try:
            saved = await self.store.async_load()
            if saved is not None:
                entries = saved.get("entries")
                if not isinstance(entries, list):
                    raise ValueError("invalid_decision_journal")
                self.entries = [item for item in entries if isinstance(item, dict)]
            self._trim()
        except Exception as exc:  # A corrupt archive must never stop the controller.
            # Never silently replace unreadable audit history.
            self.available = False
            self.error = f"{type(exc).__name__}:{exc}"
            _LOGGER.error("Energy Co-Pilot audit history unavailable: %s", self.error)

    def _trim(self):
        cutoff = (dt_util.utcnow() - timedelta(days=RETENTION_DAYS)).isoformat()
        self.entries = [
            item
            for item in self.entries
            if isinstance(item.get("time_utc"), str) and item["time_utc"] >= cutoff
        ][-MAX_EVENTS:]

    def record(self, event, *, reason=None, **details):
        entry = {
            "decision_id": str(uuid4()),
            "time_utc": dt_util.utcnow().isoformat(),
            "event": event,
            "reason": reason,
            **details,
        }
        # Log to the normal HA log even when the persistent store is unavailable.
        log = (
            _LOGGER.warning
            if event in {"blocked", "failure", "halted"}
            else _LOGGER.info
        )
        log("Energy Co-Pilot audit: %s", json.dumps(entry, default=str, sort_keys=True))
        if self.available:
            try:
                self.entries.append(entry)
                self._trim()
                self.store.async_delay_save(lambda: {"entries": self.entries}, 5)
            except Exception as exc:
                self.available = False
                self.error = f"{type(exc).__name__}:{exc}"
                _LOGGER.exception("Energy Co-Pilot audit storage failed")
        return entry

    def recent(self, limit=30):
        return self.entries[-limit:]

    @property
    def summary(self):
        return {
            "available": self.available,
            "error": self.error,
            "retention_days": RETENTION_DAYS,
            "max_events": MAX_EVENTS,
            "retained_events": len(self.entries),
            "oldest_utc": self.entries[0]["time_utc"] if self.entries else None,
            "newest_utc": self.entries[-1]["time_utc"] if self.entries else None,
        }

    async def async_close(self):
        if self.available:
            try:
                await self.store.async_save({"entries": self.entries})
            except Exception:
                _LOGGER.exception("Energy Co-Pilot could not persist audit at unload")
