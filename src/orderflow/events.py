"""Event hygiene shared by all detectors: warm-up filter and dedup.

Per preregistration/PREREGISTRATION.md section 5.
"""
from __future__ import annotations

import polars as pl

from orderflow.config import DEDUP_GAP_BARS, WARM_UP_BARS

EVENT_SCHEMA = ["bar_index", "bar_ts", "signal", "direction", "magnitude"]


def apply_warmup(events: pl.DataFrame, warm_up_bars: int = WARM_UP_BARS) -> pl.DataFrame:
    return events.filter(pl.col("bar_index") >= warm_up_bars)


def dedup(events: pl.DataFrame, gap_bars: int = DEDUP_GAP_BARS) -> pl.DataFrame:
    """Same signal, same direction, events within `gap_bars` of a prior KEPT
    event are dropped (greedy, keep-first scan). Different signals/directions
    never suppress each other.
    """
    if events.height == 0:
        return events
    kept_rows = []
    for (_signal, _direction), grp in events.sort("bar_index").group_by(["signal", "direction"], maintain_order=True):
        last_kept = None
        for row in grp.iter_rows(named=True):
            if last_kept is None or row["bar_index"] - last_kept > gap_bars:
                kept_rows.append(row)
                last_kept = row["bar_index"]
    if not kept_rows:
        return events.clear()
    return pl.DataFrame(kept_rows, schema=events.schema).sort("bar_index")


def hygiene(events: pl.DataFrame, warm_up_bars: int = WARM_UP_BARS, gap_bars: int = DEDUP_GAP_BARS) -> pl.DataFrame:
    return dedup(apply_warmup(events, warm_up_bars), gap_bars)
