"""Read-only source contract. Signs and economic policy come from REQUIREMENTS."""

from datetime import timedelta

DOMAIN = "energy_copilot"
UPDATE_INTERVAL = timedelta(seconds=30)
MAX_AGE = timedelta(minutes=5)
# Precision warning for independent as-of reports, not a hard rejection limit.
MAX_SKEW = timedelta(seconds=10)
MAX_FUTURE_OFFSET = timedelta(seconds=10)
DEFAULT_ENTITIES = {
    "pv": "sensor.pv_sum",
    "grid": "sensor.sun12k_total_grid_power",
    "battery": "sensor.sun12k_battery_output_power",
    "voltage": "sensor.sun12k_battery_voltage",
    "current": "sensor.sun12k_battery_output_current",
    "soc": "sensor.sun12k_battery_capacity",
    "home": "sensor.home_energy_consumption",
    "grid_alternative": "sensor.sun12k_out_of_grid_total_power_2",
    "daily_pv": "sensor.sun12k_daily_production",
    "daily_charge": "sensor.sun12k_today_charge_of_the_battery",
    "daily_discharge": "sensor.sun12k_today_discharge_of_the_battery",
    "buy": "sensor.energi_data_service",
    "sell": "sensor.energi_data_spotpris",
}
POWER_ROLES = {"pv", "grid", "battery", "home", "grid_alternative"}
HISTORY_ROLES = ("pv", "grid", "battery", "home")

# Core sources needed for measurements, SOC and the published price horizon.
# Other sources corroborate the core measurements without blocking configuration.
REQUIRED_ENTITY_ROLES = frozenset(
    {"pv", "grid", "battery", "soc", "home", "buy", "sell"}
)
OPTIONAL_ENTITY_ROLES = frozenset(DEFAULT_ENTITIES) - REQUIRED_ENTITY_ROLES
DEFAULT_FORECAST_RETENTION_DAYS = 90
MAX_FORECAST_RETENTION_DAYS = 366
DEFAULT_FORECAST_MAX_VERSIONS = 10_000
MAX_FORECAST_VERSIONS = 50_000
