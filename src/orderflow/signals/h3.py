"""H3 - Stacked imbalance. preregistration/PREREGISTRATION.md section 2, H3."""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import polars as pl

from orderflow.config import H3_IMBALANCE_RATIO, H3_MIN_STACK, H3_VOLUME_WINDOW
from orderflow.rolling import rolling_pooled_percentile


def _group_by_bar_level(buckets: pl.DataFrame, delta: float) -> dict[int, dict[int, tuple[float, float]]]:
    by_bar: dict[int, dict[int, tuple[float, float]]] = defaultdict(dict)
    for bar_index, bucket_px, buy_vol, sell_vol in zip(
        buckets["bar_index"].to_list(),
        buckets["bucket_px"].to_list(),
        buckets["buy_vol"].to_list(),
        buckets["sell_vol"].to_list(),
    ):
        level = round(bucket_px / delta)
        by_bar[bar_index][level] = (buy_vol, sell_vol)
    return by_bar


def _longest_run(flags: list[bool], ratios: list[float]) -> tuple[int, int, float] | None:
    """Return (start_idx, length, mean_ratio) of the longest True run of
    length >= H3_MIN_STACK; ties broken by higher mean ratio."""
    best = None
    i = 0
    n = len(flags)
    while i < n:
        if not flags[i]:
            i += 1
            continue
        j = i
        while j < n and flags[j]:
            j += 1
        length = j - i
        if length >= H3_MIN_STACK:
            mean_ratio = float(np.mean(ratios[i:j]))
            if best is None or length > best[1] or (length == best[1] and mean_ratio > best[2]):
                best = (i, length, mean_ratio)
        i = j
    return best


def detect(bars: pl.DataFrame, buckets: pl.DataFrame, delta: float) -> pl.DataFrame:
    bars = bars.sort("bar_index")
    n_bars = bars.height

    total_vol = (buckets["buy_vol"] + buckets["sell_vol"]).to_numpy()
    p25_96 = rolling_pooled_percentile(buckets["bar_index"].to_numpy(), total_vol, n_bars, H3_VOLUME_WINDOW, 0.25)

    by_bar = _group_by_bar_level(buckets, delta)

    bar_index_arr = bars["bar_index"].to_numpy()
    bar_ts_arr = bars["bar_ts"].to_numpy()
    low_arr = bars["low"].to_numpy()
    high_arr = bars["high"].to_numpy()

    rows = []
    for i in range(n_bars):
        floor_p = p25_96[i]
        if np.isnan(floor_p) or floor_p <= 0:
            continue
        levels_map = by_bar.get(bar_index_arr[i])
        if not levels_map:
            continue
        low_level = int(np.floor(low_arr[i] / delta))
        high_level = int(np.floor(high_arr[i] / delta))
        if high_level <= low_level:
            continue
        levels = list(range(low_level, high_level + 1))

        def vol(level: int, side: int) -> float:
            bv, sv = levels_map.get(level, (0.0, 0.0))
            return bv if side == 0 else sv

        # "up" imbalance at level p (index k, k>=1): sell_vol(p-Delta) floor + buy_vol(p)/sell_vol(p-Delta) >= 3.0
        up_flags, up_ratios = [], []
        down_flags, down_ratios = [], []
        for k in range(len(levels)):
            if k == 0:
                up_flags.append(False)
                up_ratios.append(0.0)
                down_flags.append(False)
                down_ratios.append(0.0)
                continue
            p = levels[k]
            p_below = levels[k - 1]
            sell_below = vol(p_below, 1)
            buy_here = vol(p, 0)
            if sell_below >= floor_p and sell_below > 0 and buy_here / sell_below >= H3_IMBALANCE_RATIO:
                up_flags.append(True)
                up_ratios.append(buy_here / sell_below)
            else:
                up_flags.append(False)
                up_ratios.append(0.0)

        for k in range(len(levels)):
            if k == len(levels) - 1:
                down_flags.append(False)
                down_ratios.append(0.0)
                continue
            p = levels[k]
            p_above = levels[k + 1]
            buy_above = vol(p_above, 0)
            sell_here = vol(p, 1)
            if buy_above >= floor_p and buy_above > 0 and sell_here / buy_above >= H3_IMBALANCE_RATIO:
                down_flags.append(True)
                down_ratios.append(sell_here / buy_above)
            else:
                down_flags.append(False)
                down_ratios.append(0.0)

        up_run = _longest_run(up_flags, up_ratios)
        down_run = _longest_run(down_flags, down_ratios)

        if up_run is not None:
            _, length, mean_ratio = up_run
            rows.append((int(bar_index_arr[i]), bar_ts_arr[i], "H3", 1, float(length * mean_ratio)))
        if down_run is not None:
            _, length, mean_ratio = down_run
            rows.append((int(bar_index_arr[i]), bar_ts_arr[i], "H3", -1, float(length * mean_ratio)))

    if not rows:
        return pl.DataFrame(
            schema={"bar_index": pl.Int64, "bar_ts": pl.Datetime, "signal": pl.Utf8, "direction": pl.Int8, "magnitude": pl.Float64}
        )
    out = pl.DataFrame(
        rows, schema=["bar_index", "bar_ts", "signal", "direction", "magnitude"], orient="row"
    ).with_columns(pl.col("direction").cast(pl.Int8))
    return out.sort("bar_index")
