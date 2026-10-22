"""Read native HA hourly long-term statistics for a household load model.

Stats are read at most on the coordinator's slow refresh; no raw-history backfill.
"""
from datetime import UTC, datetime, timedelta
from math import isfinite

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.exceptions import HomeAssistantError

from .load_forecast import LOOKBACK_DAYS, HourlyLoad, train_load_model

HOUR = timedelta(hours=1)


class LoadStatisticsError(HomeAssistantError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _positive_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    num = float(value)
    return num if isfinite(num) else None


def _convert_hour(stat, unit):
    """Extract energy for one hour, never substitute missing stats with zero."""
    if unit in {"W", "kW"}:
        value = _positive_number(stat.get("mean"))
        if value is None:
            return None
        return max(0.0, value * (1 if unit == "kW" else 0.001))
    if unit in {"Wh", "kWh", "MWh"}:
        value = _positive_number(stat.get("change"))
        if value is None or value < 0:
            return None
        return value * {"Wh": 0.001, "kWh": 1.0, "MWh": 1000.0}[unit]
    return None


def _read_single(stats, sensor, unit, end):
    output = {}
    for row in stats.get(sensor, ()):
        try:
            at = datetime.fromtimestamp(row["start"], UTC)
            last = datetime.fromtimestamp(row["end"], UTC)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if last - at != HOUR or last > end:
            continue
        energy = _convert_hour(row, unit)
        if energy is not None:
            output[at] = energy
    return output


def _read_power_means(stats, sensor, unit, end):
    if unit not in {"W", "kW"}:
        return {}
    values = {}
    for row in stats.get(sensor, ()):
        try:
            at = datetime.fromtimestamp(row["start"], UTC)
            last = datetime.fromtimestamp(row["end"], UTC)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        value = _positive_number(row.get("mean"))
        if value is not None and last - at == HOUR and last <= end:
            values[at] = value * (1000 if unit == "kW" else 1)
    return values


class LoadStatisticsReader:
    def __init__(self, hass, entities, statistic_sensor=None):
        self.hass = hass
        self.entities = entities
        self.statistic_sensor = statistic_sensor

    async def async_train(self, now):
        """Prefer a direct house sensor; fallback mirrors the existing HA template.

        A fallback PV + grid + battery profile is a modeled DC/AC approximation,
        not an independently verified AC household meter.
        """
        if "recorder" not in self.hass.config.components:
            raise LoadStatisticsError("load:recorder_unavailable")
        instance = get_instance(self.hass)
        if getattr(instance, "enabled", True) is False:
            raise LoadStatisticsError("load:recorder_disabled")
        end = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=LOOKBACK_DAYS)
        preferred = self.statistic_sensor or self.entities["home"]
        ids = sorted({preferred, *(self.entities[r] for r in ("pv", "grid", "battery"))})
        ids = [i for i in ids if i]
        units = {}
        for entity_id in ids:
            state = self.hass.states.get(entity_id)
            units[entity_id] = state.attributes.get("unit_of_measurement") if state else None
        try:
            raw = await instance.async_add_executor_job(
                statistics_during_period,
                self.hass,
                start,
                end,
                ids,
                "hour",
                None,
                {"mean", "change"},
            )
        except (HomeAssistantError, ValueError, TypeError) as err:
            raise LoadStatisticsError("load:statistics_read_failed") from err
        direct = _read_single(raw, preferred, units[preferred], end)
        if self.statistic_sensor:
            try:
                return train_load_model(
                    tuple(HourlyLoad(k, v) for k, v in direct.items()), end, preferred
                )
            except ValueError as err:
                raise LoadStatisticsError("load:selected_statistic_unusable") from err
        try:
            return train_load_model(
                tuple(HourlyLoad(k, v) for k, v in direct.items()), end, preferred
            )
        except ValueError:
            pass
        components = [
            _read_power_means(raw, self.entities[role], units[self.entities[role]], end)
            for role in ("pv", "grid", "battery")
        ]
        valid_times = set(components[0])
        for component in components[1:]:
            valid_times &= component.keys()
        modeled = [
            HourlyLoad(hour, max(0.0, sum(component[hour] for component in components)) / 1000)
            for hour in sorted(valid_times)
        ]
        try:
            return train_load_model(
                tuple(modeled), end, "derived_pv_grid_battery_hourly_means_unverified"
            )
        except ValueError as err:
            raise LoadStatisticsError("load:insufficient_hourly_statistics") from err
