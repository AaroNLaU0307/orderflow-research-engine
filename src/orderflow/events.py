"""Event hygiene shared by all detectors: warm-up filter and dedup.

Per preregistration/PREREGISTRATION.md section 5.
"""
from __future__ import annotations

import polars as pl

from orderflow.config import DEDUP_GAP_BARS, WARM_UP_BARS

EVENT_SCHEMA = ["bar_index", "bar_ts", "signal", "direction", "magnitude"]
EMPTY_EVENTS_SCHEMA = {"bar_index": pl.Int64, "bar_ts": pl.Datetime, "signal": pl.Utf8, "direction": pl.Int8, "magnitude": pl.Float64}


def assemble_events(bars: pl.DataFrame, rows: list[tuple]) -> pl.DataFrame:
    """Build an events DataFrame from (bar_index, signal, direction, magnitude)
    rows, looking up bar_ts from `bars` rather than embedding it directly in
    the row tuples.

    Embedding numpy.datetime64 scalars (from bars["bar_ts"].to_numpy()) into
    Python row-tuples and constructing a DataFrame from them makes polars
    infer bar_ts as an opaque Object column, not Datetime - harmless until
    something needs real datetime ops on it (e.g. quarantine's .dt.epoch()),
    which then raises "cannot cast 'Object' type". Looking bar_ts up via a
    Series gather instead preserves the proper Datetime dtype.
    """
    if not rows:
        return pl.DataFrame(schema=EMPTY_EVENTS_SCHEMA)
    out = pl.DataFrame(
        rows, schema=["bar_index", "signal", "direction", "magnitude"], orient="row"
    ).with_columns(pl.col("direction").cast(pl.Int8))
    bar_ts_by_index = bars.sort("bar_index")["bar_ts"]
    out = out.with_columns(pl.Series("bar_ts", bar_ts_by_index.gather(out["bar_index"])))
    return out.sort("bar_index").select(["bar_index", "bar_ts", "signal", "direction", "magnitude"])


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
