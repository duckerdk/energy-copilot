"""Bounded live timing evidence and protection of a derived home after outages."""

import math
from collections import Counter, deque
from datetime import timedelta

from homeassistant.components.template.sensor import StateSensorEntity
from homeassistant.helpers.entity_component import DATA_INSTANCES

from .validation import DERIVED_SOURCES, live_timing, measurement, utc

SOURCE_ROLES = ("pv", "grid", "battery")
WATCHED_ROLES = SOURCE_ROLES
WINDOW = timedelta(minutes=30)
MAX_POLLS = 120
UNCERTAINTY_CODES = {
    "measurement_time_skew",
    "home_context_lag",
    "derived_value_from_fresh_sources",
    "derived_sum_time_uncertain",
    "derived_source_confirmation_unavailable",
    "pv_template_time_unverified",
    "derived_home_with_unverified_pv_time",
}


def derived_templates(hass, entities):
    """Recognize loaded native state-based templates, including YAML without IDs.

    Never infer template provenance from a friendly name, zero or entity ID.
    Registry-only, unloaded, trigger-based and non-native sources fail closed.
    """
    component = hass.data.get(DATA_INSTANCES, {}).get("sensor")
    if component is None:
        return {}
    templates = {
        role: tuple(r for r in required if entities.get(r))
        for role, required in DERIVED_SOURCES.items()
        if isinstance(component.get_entity(entities[role]), StateSensorEntity)
    }
    if isinstance(component.get_entity(entities["pv"]), StateSensorEntity):
        templates["pv"] = ()
    return templates


class LiveSourceContext:
    """Remember observed failures even when the source recovers between polls.

    A numeric float(0) template is untrusted until reported after recovery. This
    memory starts at setup; it cannot establish source health before HA startup.
    """

    def __init__(self):
        self.recovery_at = {}

    def observe(self, role, state, now, *, derived=False):
        try:
            measurement(role, state, now, allow_old_report=derived)
        except ValueError:
            self.recovery_at[role] = None
        else:
            if role in self.recovery_at and self.recovery_at[role] is None:
                self.recovery_at[role] = utc(state.last_reported)

    def accept_home(self, home):
        if home is not None:
            self.recovery_at = {
                role: at
                for role, at in self.recovery_at.items()
                if at is None or home.at < at
            }


def _distribution(values):
    """Linear percentiles of coordinator observations, not device report cadence."""
    ordered = sorted(values)
    if not ordered:
        return {"samples": 0, "p50": None, "p95": None, "max": None}

    def percentile(fraction):
        position = (len(ordered) - 1) * fraction
        lower = math.floor(position)
        upper = math.ceil(position)
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    return {
        "samples": len(ordered),
        "p50": percentile(0.5),
        "p95": percentile(0.95),
        "max": ordered[-1],
    }


class LiveMeasurementWindow:
    """Keep only timing scalars and quality counters, never power/time series."""

    def __init__(self):
        self._polls = deque()
        self.capacity_evictions = 0
        self.clock_resets = 0

    def _expire(self, now):
        if self._polls and now < self._polls[-1]["at"]:
            self._polls.clear()
            self.clock_resets += 1
        while self._polls and self._polls[0]["at"] < now - WINDOW:
            self._polls.popleft()

    def record(self, states, now, values, issues):
        self._expire(now)
        timing = live_timing(states, values)
        metrics = {key: value for key, value in timing.items() if value is not None}
        source_changed = False
        previous = self._polls[-1]["at"] if self._polls else None
        for role in (*WATCHED_ROLES, "home"):
            state = states.get(role)
            try:
                reported, changed = utc(state.last_reported), utc(state.last_updated)
            except AttributeError, TypeError, ValueError, OverflowError:
                continue
            metrics[f"{role}_report_age_seconds"] = (now - reported).total_seconds()
            metrics[f"{role}_change_age_seconds"] = (now - changed).total_seconds()
            if role in SOURCE_ROLES and previous is not None and changed > previous:
                source_changed = True
        uncertain = any(i.code in UNCERTAINTY_CODES for i in issues)
        rejected = "home" not in values
        reasons = {
            f"{i.source}:{i.code}"
            for i in issues
            if i.source in (*WATCHED_ROLES, "home")
            and i.code not in UNCERTAINTY_CODES | {"negative_home_normalized"}
            and not (
                i.code == "pv_sum_inconsistent"
                and any(
                    j.code == "derived_sum_time_uncertain" and j.source == i.source
                    for j in issues
                )
            )
        }
        if len(self._polls) >= MAX_POLLS:
            self._polls.popleft()
            self.capacity_evictions += 1
        self._polls.append(
            {
                "at": now,
                "metrics": metrics,
                "rejected": rejected,
                "uncertain": uncertain,
                "changed_with_uncertainty": source_changed and uncertain,
                "reasons": reasons if rejected else set(),
                "pv_rejected": "pv" not in values,
                "pv_reasons": {
                    reason
                    for reason in reasons
                    if reason.split(":", 1)[0] == "pv"
                }
                if "pv" not in values
                else set(),
            }
        )

    def summary(self, now):
        self._expire(now)
        keys = {key for poll in self._polls for key in poll["metrics"]}
        rejected = sum(p["rejected"] for p in self._polls)
        return {
            "window_seconds": WINDOW.total_seconds(),
            "max_observations": MAX_POLLS,
            "observations": len(self._polls),
            "first_observation_utc": self._polls[0]["at"].isoformat()
            if self._polls
            else None,
            "last_observation_utc": self._polls[-1]["at"].isoformat()
            if self._polls
            else None,
            "home_retained": len(self._polls) - rejected,
            "home_rejected": rejected,
            "pv_retained": sum(not p["pv_rejected"] for p in self._polls),
            "pv_rejected": sum(p["pv_rejected"] for p in self._polls),
            "pv_rejection_reasons": dict(
                Counter(reason for p in self._polls for reason in p["pv_reasons"])
            ),
            "home_retained_with_uncertainty": sum(
                p["uncertain"] and not p["rejected"] for p in self._polls
            ),
            "source_change_with_uncertainty": sum(
                p["changed_with_uncertainty"] for p in self._polls
            ),
            "home_rejection_reasons": dict(
                Counter(reason for p in self._polls for reason in p["reasons"])
            ),
            "timing_seconds": {
                key: _distribution(
                    p["metrics"][key] for p in self._polls if key in p["metrics"]
                )
                for key in sorted(keys)
            },
            "capacity_evictions_this_runtime": self.capacity_evictions,
            "clock_resets_this_runtime": self.clock_resets,
            "scope": "coordinator_polls_not_device_report_intervals",
            "device_freshness_verified": False,
            "physical_home_consumption_verified": False,
            "between_poll_transients_verified": False,
        }
