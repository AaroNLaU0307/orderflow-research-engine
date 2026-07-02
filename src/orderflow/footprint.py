"""Bar and footprint-bucket construction from raw aggTrades.

Per preregistration/PREREGISTRATION.md section 4:
- 5-minute UTC epoch-aligned bars, bar_ts = bar open time.
- Absolute-grid buckets: bucket_px = floor(price/Delta)*Delta.
- Bucket delta = buy_vol - sell_vol, buy = aggressor buy = is_buyer_maker==False.
- Zero-trade bars forward-fill OHLC from the prior close, carry zero volume,
  and contribute no bucket rows.
"""
from __future__ import annotations

import datetime as dt

import polars as pl

from orderflow.config import BAR_MS, UTC


def aggregate_month(trades: pl.DataFrame, delta: float, bar_ms: int = BAR_MS) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Aggregate one month's raw trades into partial (sparse, trades-only) bar
    and bucket frames. Does not fill zero-trade bars or compute bar_index /
    cumulative_delta - that happens once per symbol in `finalize_symbol`
    after all months are concatenated, so cross-month continuity (forward
    fill, running cumulative delta) is handled correctly in one pass.
    """
    df = trades.with_columns(
        [
            (pl.col("transact_time") // bar_ms * bar_ms).alias("bar_ts_ms"),
            (pl.col("price") / delta).floor().mul(delta).alias("bucket_px"),
            pl.when(~pl.col("is_buyer_maker")).then(pl.col("quantity")).otherwise(0.0).alias("buy_vol"),
            pl.when(pl.col("is_buyer_maker")).then(pl.col("quantity")).otherwise(0.0).alias("sell_vol"),
        ]
    ).sort("transact_time")

    buckets = df.group_by(["bar_ts_ms", "bucket_px"]).agg(
        [
            pl.col("buy_vol").sum().alias("buy_vol"),
            pl.col("sell_vol").sum().alias("sell_vol"),
            pl.len().alias("trade_count"),
        ]
    )

    bars = df.group_by("bar_ts_ms").agg(
        [
            pl.col("price").first().alias("open"),
            pl.col("price").max().alias("high"),
            pl.col("price").min().alias("low"),
            pl.col("price").last().alias("close"),
            pl.col("quantity").sum().alias("volume"),
            (pl.col("buy_vol").sum() - pl.col("sell_vol").sum()).alias("delta"),
            pl.len().alias("trade_count"),
        ]
    )
    return bars, buckets


def finalize_symbol_bars(
    partial_bars: pl.DataFrame,
    series_start: dt.datetime,
    series_end: dt.datetime,
    bar_ms: int = BAR_MS,
) -> pl.DataFrame:
    """Build the continuous 5-min bar grid for the full study period, left-join
    the concatenated partial bar aggregates, forward-fill zero-trade bars,
    and add bar_index (0-based, sequential) + cumulative_delta (running sum
    over the whole continuous series).
    """
    start_ms = int(series_start.timestamp() * 1000)
    end_ms = int(series_end.timestamp() * 1000)
    n_bars = (end_ms - start_ms) // bar_ms + 1
    grid = pl.DataFrame({"bar_ts_ms": [start_ms + i * bar_ms for i in range(n_bars)]})

    merged = (
        grid.join(partial_bars, on="bar_ts_ms", how="left")
        .sort("bar_ts_ms")
        .with_columns(pl.col("close").forward_fill().alias("_ffill_close"))
    )

    merged = merged.with_columns(
        [
            pl.when(pl.col("open").is_null()).then(pl.col("_ffill_close")).otherwise(pl.col("open")).alias("open"),
            pl.when(pl.col("high").is_null()).then(pl.col("_ffill_close")).otherwise(pl.col("high")).alias("high"),
            pl.when(pl.col("low").is_null()).then(pl.col("_ffill_close")).otherwise(pl.col("low")).alias("low"),
            pl.col("_ffill_close").alias("close"),
            pl.col("volume").fill_null(0.0).alias("volume"),
            pl.col("delta").fill_null(0.0).alias("delta"),
            pl.col("trade_count").fill_null(0).alias("trade_count"),
        ]
    ).drop("_ffill_close")

    merged = merged.with_columns(
        [
            pl.arange(0, merged.height).alias("bar_index"),
            pl.from_epoch("bar_ts_ms", time_unit="ms").alias("bar_ts"),
            pl.col("delta").cum_sum().alias("cumulative_delta"),
        ]
    )
    return merged.select(
        ["bar_index", "bar_ts", "bar_ts_ms", "open", "high", "low", "close", "volume", "delta", "cumulative_delta", "trade_count"]
    )


def finalize_symbol_buckets(partial_buckets: pl.DataFrame, bars: pl.DataFrame) -> pl.DataFrame:
    """Attach bar_index to the concatenated sparse bucket rows (zero-trade
    bars naturally contribute no bucket rows - nothing to fill)."""
    idx = bars.select(["bar_index", "bar_ts", "bar_ts_ms"])
    out = partial_buckets.join(idx, on="bar_ts_ms", how="inner")
    return out.select(["bar_index", "bar_ts", "bar_ts_ms", "bucket_px", "buy_vol", "sell_vol", "trade_count"]).sort(
        ["bar_index", "bucket_px"]
    )
