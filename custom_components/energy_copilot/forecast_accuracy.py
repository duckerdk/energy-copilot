"""Prospective PV and household-load error checks from real HA observations.

Forecast for a future quarter is frozen BEFORE it begins. Subsequent accepted
power samples are integrated only across nearby coordinator polls; outages
do not become zero energy. This deliberately does not claim to verify
unconstrained PV production (the inverter may curtail).
"""

from collections import deque
from datetime import UTC, timedelta

from .planner import QUARTER
from .planning_inputs import (
    PlanningInputError,
    _exact_quarter_energy,
    _modeled_quarter_pv_energy,
)


class ForecastAccuracyWindow:
    """In-memory, bounded and read-only comparison with actual measured output."""

    def __init__(self):
        self.expected = {}
        self.actual = {}
        self.previous = {}
        self.completed = deque(maxlen=192)

    @staticmethod
    def _start(at):
        at = at.astimezone(UTC)
        return at.replace(minute=at.minute // 15 * 15, second=0, microsecond=0)

    def remember(self, now, forecast, load_projection):
        if forecast is None or load_projection is None:
            return
        start = self._start(now) + QUARTER
        if start in self.expected:
            return
        end = start + QUARTER
        try:
            pv, _ = _modeled_quarter_pv_energy(forecast.periods, start, end)
            load = _exact_quarter_energy(load_projection.periods, start, end, "load")
        except PlanningInputError:
            return
        self.expected[start] = {"pv": pv, "home": load}
        # Avoid retaining private 15-minute values beyond a small rolling window.
        for old in list(self.expected):
            if old < start - timedelta(days=3):
                self.expected.pop(old, None)
                self.actual.pop(old, None)

    def observe(self, now, measurements):
        now = now.astimezone(UTC)
        for role in ("pv", "home"):
            reading = measurements.get(role)
            prev = self.previous.get(role)
            current = reading.value if reading is not None else None
            if (
                prev is not None
                and current is not None
                and 0 < (now - prev[0]).total_seconds() <= 90
            ):
                cursor = prev[0]
                while cursor < now:
                    start = self._start(cursor)
                    right = min(now, start + QUARTER)
                    if start in self.expected:
                        bucket = self.actual.setdefault(
                            start,
                            {"pv": [0.0, 0.0], "home": [0.0, 0.0]},
                        )
                        duration = (right - cursor).total_seconds()
                        bucket[role][0] += prev[1] * duration / 3_600_000
                        bucket[role][1] += duration
                    cursor = right
            self.previous[role] = (now, current) if current is not None else None
        for start in sorted(self.expected):
            if start + QUARTER > now:
                continue
            observed = self.actual.pop(start, {})
            expected = self.expected.pop(start)
            row = {}
            for role in ("pv", "home"):
                value, seconds = observed.get(role, (0.0, 0.0))
                if seconds >= 855:  # At least 95% of each quarter observed.
                    row[role] = (expected[role], value)
            if row:
                self.completed.append(row)

    @property
    def summary(self):
        result = {
            "scope": "prospective_quarters_from_live_ha_power_not_backfilled",
            "persistence": "current_ha_runtime_only",
            "pv_actual_basis": "pv_sum_measured_output_may_be_curtailed",
            "home_actual_basis": "derived_home_power_not_independent_meter",
            "physical_accuracy_verified": False,
        }
        for role in ("pv", "home"):
            rows = [entry[role] for entry in self.completed if role in entry]
            result[role] = {
                "verified_quarters": len(rows),
                "mae_kwh_per_quarter": (
                    sum(abs(predicted - actual) for predicted, actual in rows)
                    / len(rows)
                    if rows
                    else None
                ),
                "signed_bias_kwh_per_quarter": (
                    sum(predicted - actual for predicted, actual in rows) / len(rows)
                    if rows
                    else None
                ),
                "sample_complete": len(rows) >= 8,
                "positive_underprediction_p75_kwh_per_quarter": (
                    sorted(max(0.0, actual - predicted) for predicted, actual in rows)[
                        min(len(rows) - 1, int(0.75 * len(rows)))
                    ]
                    if role == "pv" and len(rows) >= 16
                    else None
                ),
                "pv_uncertainty_source": (
                    "measured_pv_sum_may_be_curtailed"
                    if role == "pv" and len(rows) >= 16
                    else "insufficient_daylight_observations"
                    if role == "pv"
                    else None
                ),
            }
        return result
