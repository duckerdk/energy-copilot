"""Read-only source contract. Signs and economic policy come from REQUIREMENTS."""

from datetime import timedelta

DOMAIN = "energy_copilot"
UPDATE_INTERVAL = timedelta(seconds=30)
MAX_AGE = timedelta(minutes=5)
MAX_SKEW = timedelta(seconds=10)
DEFAULT_ENTITIES = {
    "pv": "sensor.pv_sum",
    "pv1": "sensor.sun12k_pv1_power",
    "pv2": "sensor.sun12k_pv2_power",
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
POWER_ROLES = {"pv", "pv1", "pv2", "grid", "battery", "home", "grid_alternative"}
HISTORY_ROLES = ("pv", "grid", "battery", "home")
