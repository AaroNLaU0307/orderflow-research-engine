"""Quarantine windows: time ranges where the raw data has a confirmed
upstream gap (present in both the monthly AND daily Binance archives, so
not repairable by re-splicing - see data/quarantine_windows.json for the
forensic detail per window). Bars overlapping a quarantine window are
excluded from event formation; any forward-return window overlapping one
is nulled. This is intentionally separate from the ordinary zero-trade-bar
forward-fill (footprint.py) - a quarantine window marks data we know is
MISSING, not a bar we've verified had zero genuine trades.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "quarantine_windows.json"


def load_quarantine_windows(path: Path = DEFAULT_PATH) -> dict[str, list[tuple[int, int]]]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        records = json.load(fh)
    out: dict[str, list[tuple[int, int]]] = {}
    for r in records:
        out.setdefault(r["symbol"], []).append((r["start_ms"], r["end_ms"]))
    return out


def bar_overlaps_any(bar_start_ms: int, bar_end_ms: int, windows: list[tuple[int, int]]) -> bool:
    return any(bar_start_ms < end and bar_end_ms > start for start, end in windows)


def filter_quarantined_events(events: pl.DataFrame, symbol: str, bar_ms: int, windows: dict[str, list[tuple[int, int]]]) -> pl.DataFrame:
    """Drop events whose trigger bar overlaps a quarantine window for this
    symbol."""
    sym_windows = windows.get(symbol, [])
    if not sym_windows or events.height == 0:
        return events
    bar_ts_ms = events["bar_ts"].dt.epoch(time_unit="ms").to_numpy()
    keep = [not bar_overlaps_any(int(ms), int(ms) + bar_ms, sym_windows) for ms in bar_ts_ms]
    return events.filter(pl.Series(keep))


def null_returns_overlapping_quarantine(
    events: pl.DataFrame, symbol: str, bars: pl.DataFrame, horizons: list[int], bar_ms: int, windows: dict[str, list[tuple[int, int]]]
) -> pl.DataFrame:
    """For events surviving filter_quarantined_events, null out any r_{h}
    whose [entry_bar, target_bar] window overlaps a quarantine window -
    the event's own trigger bar is clean, but its forward-return horizon
    may still run through a quarantined stretch.
    """
    sym_windows = windows.get(symbol, [])
    if not sym_windows or events.height == 0:
        return events
    bars_sorted = bars.sort("bar_index")
    bar_ts_ms_by_index = bars_sorted["bar_ts"].dt.epoch(time_unit="ms").to_numpy()
    n_bars = len(bar_ts_ms_by_index)
    t = events["bar_index"].to_numpy()

    out = events
    for h in horizons:
        col = f"r_{h}"
        if col not in out.columns:
            continue
        entry_idx = t + 1
        target_idx = t + 1 + h
        mask = []
        for i in range(len(t)):
            ei, ti = entry_idx[i], target_idx[i]
            if ei < 0 or ti >= n_bars:
                mask.append(False)
                continue
            window_start_ms = int(bar_ts_ms_by_index[ei])
            window_end_ms = int(bar_ts_ms_by_index[ti]) + bar_ms
            mask.append(bar_overlaps_any(window_start_ms, window_end_ms, sym_windows))
        overlap = pl.Series(mask)
        out = out.with_columns(pl.when(overlap).then(None).otherwise(pl.col(col)).alias(col))
    return out
