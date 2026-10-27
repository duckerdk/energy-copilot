"""TOU compiler must refuse plans that six daily slots cannot express."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.energy_copilot.tou_compiler import (
    TOUCompilationError,
    compile_tou,
)


def day():
    start = datetime(2026, 10, 27, tzinfo=ZoneInfo("Europe/Copenhagen"))
    rows = []
    for i in range(96):
        hour = i // 4
        # Exactly six constant four-hour groups.
        target = 20 + 10 * (hour // 4)
        rows.append(
            {
                "start": (start + timedelta(minutes=15 * i)).isoformat(),
                "soc_end_pct": target,
                "grid_charge_kwh": 0.0,
                "battery_discharge_dc_kwh": 0.0,
            }
        )
    return rows


def test_valid_six_windows_cover_whole_day():
    program = compile_tou(tuple(day()))
    assert [w.start_minute for w in program.windows] == [
        0, 240, 480, 720, 960, 1200
    ]
    assert [w.minimum_soc_pct for w in program.windows] == [
        20, 30, 40, 50, 60, 70
    ]


def test_rejects_incomplete_replay_prefix():
    with pytest.raises(TOUCompilationError, match="complete_24h"):
        compile_tou(tuple(day()[:50]))


def test_rejects_more_than_six_windows():
    rows = day()
    for i, row in enumerate(rows):
        row["soc_end_pct"] = 20 + 10 * ((i // 4) % 7)
    with pytest.raises(TOUCompilationError, match="exactly_six"):
        compile_tou(tuple(rows))


def test_rejects_quarterly_soc_changes():
    rows = day()
    rows[2]["soc_end_pct"] = 25
    with pytest.raises(TOUCompilationError, match="intra_hour"):
        compile_tou(tuple(rows))


def test_rejects_simultaneous_flows():
    rows = day()
    rows[1]["grid_charge_kwh"] = 0.1
    rows[1]["battery_discharge_dc_kwh"] = 0.1
    with pytest.raises(TOUCompilationError, match="simultaneous"):
        compile_tou(tuple(rows))


def test_rejects_dst_25_hour_day():
    start = datetime(2026, 10, 25, tzinfo=ZoneInfo("Europe/Copenhagen"))
    rows = day()
    for i, row in enumerate(rows):
        row["start"] = (start + timedelta(minutes=15 * i)).isoformat()
    with pytest.raises(TOUCompilationError):
        compile_tou(tuple(rows))
