"""H2 - Absorption. preregistration/PREREGISTRATION.md section 2, H2."""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import polars as pl

from orderflow.config import H2_AGGRESSION_FRACTION, H2_VOLUME_MULTIPLE, H2_VOLUME_WINDOW, H2_ZONE_FRACTION
from orderflow.events import assemble_events
from orderflow.rolling import rolling_pooled_percentile


def _group_buckets_by_bar(buckets: pl.DataFrame) -> dict[int, list[tuple[float, float, float]]]:
    by_bar: dict[int, list[tuple[float, float, float]]] = defaultdict(list)
    for bar_index, bucket_px, buy_vol, sell_vol in zip(
        buckets["bar_index"].to_list(),
        buckets["bucket_px"].to_list(),
        buckets["buy_vol"].to_list(),
        buckets["sell_vol"].to_list(),
    ):
        by_bar[bar_index].append((bucket_px, buy_vol, sell_vol))
    return by_bar


def detect(bars: pl.DataFrame, buckets: pl.DataFrame, delta: float) -> pl.DataFrame:
    bars = bars.sort("bar_index")
    n_bars = bars.height

    total_vol = (buckets["buy_vol"] + buckets["sell_vol"]).to_numpy()
    med96 = rolling_pooled_percentile(
        buckets["bar_index"].to_numpy(), total_vol, n_bars, H2_VOLUME_WINDOW, 0.5
    )

    by_bar = _group_buckets_by_bar(buckets)

    bar_index_arr = bars["bar_index"].to_numpy()
    low_arr = bars["low"].to_numpy()
    high_arr = bars["high"].to_numpy()
    close_arr = bars["close"].to_numpy()

    rows = []
    for i in range(n_bars):
        m = med96[i]
        if np.isnan(m) or m <= 0:
            continue
        rows_here = by_bar.get(bar_index_arr[i])
        if not rows_here:
            continue
        low, high, close = low_arr[i], high_arr[i], close_arr[i]
        rng = high - low
        bull_zone_max = low + H2_ZONE_FRACTION * rng
        bear_zone_min = high - H2_ZONE_FRACTION * rng

        best_bull = None  # (multiple, magnitude)
        best_bear = None
        for bucket_px, buy_vol, sell_vol in rows_here:
            bucket_vol = buy_vol + sell_vol
            if bucket_vol < H2_VOLUME_MULTIPLE * m:
                continue
            multiple = bucket_vol / m
            if bucket_px <= bull_zone_max:
                if sell_vol >= H2_AGGRESSION_FRACTION * bucket_vol and close >= bucket_px + delta:
                    if best_bull is None or multiple > best_bull:
                        best_bull = multiple
            if bucket_px >= bear_zone_min:
                if buy_vol >= H2_AGGRESSION_FRACTION * bucket_vol and close <= bucket_px - delta:
                    if best_bear is None or multiple > best_bear:
                        best_bear = multiple

        if best_bull is not None:
            rows.append((int(bar_index_arr[i]), "H2", 1, float(best_bull)))
        if best_bear is not None:
            rows.append((int(bar_index_arr[i]), "H2", -1, float(best_bear)))

    return assemble_events(bars, rows)
