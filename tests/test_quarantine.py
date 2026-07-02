import datetime as dt
import json

import polars as pl
import pytest

from orderflow import quarantine

UTC = dt.timezone.utc


def _events(rows):
    return pl.DataFrame(
        rows, schema=["bar_index", "bar_ts", "signal", "direction", "magnitude"], orient="row"
    ).with_columns(pl.col("direction").cast(pl.Int8))


def test_bar_overlaps_any():
    windows = [(1000, 2000)]
    assert quarantine.bar_overlaps_any(1500, 1600, windows) is True  # fully inside
    assert quarantine.bar_overlaps_any(900, 1100, windows) is True  # overlaps start
    assert quarantine.bar_overlaps_any(1900, 2100, windows) is True  # overlaps end
    assert quarantine.bar_overlaps_any(0, 999, windows) is False  # entirely before
    assert quarantine.bar_overlaps_any(2001, 3000, windows) is False  # entirely after (boundary exclusive)


def test_load_quarantine_windows(tmp_path):
    path = tmp_path / "q.json"
    path.write_text(
        json.dumps(
            [
                {"symbol": "BTCUSDT", "start_ms": 100, "end_ms": 200},
                {"symbol": "BTCUSDT", "start_ms": 500, "end_ms": 600},
                {"symbol": "ETHUSDT", "start_ms": 1, "end_ms": 2},
            ]
        )
    )
    windows = quarantine.load_quarantine_windows(path)
    assert windows["BTCUSDT"] == [(100, 200), (500, 600)]
    assert windows["ETHUSDT"] == [(1, 2)]


def test_load_quarantine_windows_missing_file(tmp_path):
    assert quarantine.load_quarantine_windows(tmp_path / "nope.json") == {}


def test_filter_quarantined_events_drops_overlapping_bar():
    bar_ms = 5 * 60_000
    base = dt.datetime(2022, 9, 6, 17, 10, tzinfo=UTC)
    events = _events(
        [
            (100, base, "H1", 1, 1.0),  # inside quarantine window
            (101, base + dt.timedelta(minutes=5), "H1", 1, 1.0),  # also inside
            (200, base + dt.timedelta(hours=2), "H1", 1, 1.0),  # well outside
        ]
    )
    start_ms = int(base.timestamp() * 1000)
    windows = {"BTCUSDT": [(start_ms - 1000, start_ms + 2 * bar_ms)]}
    out = quarantine.filter_quarantined_events(events, "BTCUSDT", bar_ms, windows)
    assert out["bar_index"].to_list() == [200]


def test_filter_quarantined_events_noop_for_other_symbol():
    base = dt.datetime(2022, 9, 6, 17, 10, tzinfo=UTC)
    events = _events([(100, base, "H1", 1, 1.0)])
    windows = {"BTCUSDT": [(0, 10**15)]}  # huge window, but for BTC only
    out = quarantine.filter_quarantined_events(events, "ETHUSDT", 5 * 60_000, windows)
    assert out.height == 1


def test_null_returns_overlapping_quarantine():
    bar_ms = 5 * 60_000
    n = 20
    start = dt.datetime(2024, 1, 1, tzinfo=UTC)
    bars = pl.DataFrame(
        {
            "bar_index": list(range(n)),
            "bar_ts": [start + dt.timedelta(minutes=5 * i) for i in range(n)],
        }
    )
    # event at bar 2 (entry_idx = 3): h=1 -> target bar 4 (window [3,4]); h=6 -> target bar 9 (window [3,9])
    events = _events([(2, bars["bar_ts"][2], "H1", 1, 1.0)])
    events = events.with_columns([pl.Series("r_1", [0.01]), pl.Series("r_6", [0.02])])

    # quarantine window covering bar 5 (outside h=1's [3,4] span, inside h=6's [3,9] span)
    window_start_ms = int(bars["bar_ts"][5].timestamp() * 1000)
    windows = {"BTCUSDT": [(window_start_ms, window_start_ms + bar_ms)]}

    out = quarantine.null_returns_overlapping_quarantine(events, "BTCUSDT", bars, [1, 6], bar_ms, windows)
    row = out.row(0, named=True)
    assert row["r_1"] is not None  # h=1 window (entry=bar3..target=bar4) doesn't reach bar 5
    assert row["r_6"] is None  # h=6 window (entry=bar3..target=bar9) overlaps quarantined bar 5
