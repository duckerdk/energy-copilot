"""Check representability of a rolling 15-minute plan in six Deye TOU slots.

This proves only that the intended setpoints can be produced by rewriting the
currently active, fixed four-hour slot every quarter. It does NOT prove that
the physical Deye actually charges the requested amount, that HA writes
complete on time, or that installation-specific TOU start values are correct.
"""

from math import ceil, isfinite
from zoneinfo import ZoneInfo

from .planner import MIN_SOC


def validate_tou_projection(plant, quarters, dispatches, candidate):
    if len(quarters) != len(dispatches) or len(quarters) != len(candidate.quarters):
        return {"status": "not_representable", "reason": "length_mismatch"}
    local = ZoneInfo("Europe/Copenhagen")
    slot_counts = [0] * 6
    expected_commands = 0
    last_setting = None
    for q, d, actual in zip(quarters, dispatches, candidate.quarters, strict=True):
        start = q.start.astimezone(local)
        slot = start.hour // 4
        if slot < 0 or slot > 5:
            return {"status": "not_representable", "reason": "invalid_slot"}
        slot_counts[slot] += 1
        grid = d.grid_to_battery_ac_kwh > 1e-7
        discharge = d.battery_to_home_dc_kwh > 1e-7
        if grid and discharge:
            return {"status": "not_representable", "reason": "opposite_battery_flows"}
        if not isfinite(actual.soc_start_pct) or not isfinite(actual.soc_end_pct):
            return {"status": "not_representable", "reason": "soc_nonfinite"}
        if not MIN_SOC - 1e-6 <= actual.soc_end_pct <= 100 + 1e-6:
            return {"status": "not_representable", "reason": "soc_outside_limits"}
        if grid:
            # Actual executor rounds to 1% and may not realize the exact
            # optimization energy; 1 pp quantization is modeled explicitly.
            requested_dc = d.grid_to_battery_ac_kwh * plant.eta_grid_to_battery
            target = min(
                100,
                max(
                    ceil(actual.soc_start_pct),
                    ceil(
                        actual.soc_start_pct
                        + requested_dc * 100 / plant.battery_capacity_dc_kwh
                    ),
                ),
            )
        elif discharge:
            target = int(MIN_SOC)
        else:
            target = min(100, max(int(MIN_SOC), ceil(actual.soc_start_pct)))
        if grid and target <= actual.soc_start_pct + 1e-6:
            return {
                "status": "not_representable",
                "reason": "grid_target_not_above_soc",
            }
        command = (slot + 1, target, grid)
        if command != last_setting:
            expected_commands += 1
            last_setting = command
    return {
        "status": "modeled_quarterly_rewrites_only",
        "slots": 6,
        "fixed_local_slot_starts_hhmm": [0, 400, 800, 1200, 1600, 2000],
        "quarters_checked": len(quarters),
        "per_slot_quarter_counts": slot_counts,
        "expected_tou_setpoint_updates": expected_commands,
        "soc_quantization_percent": 1,
        "hardware_execution_verified": False,
        "independent_proof_of_realisable_grid_kwh": False,
        "note": "Physical ramp and service-write timing require live HA validation",
    }
