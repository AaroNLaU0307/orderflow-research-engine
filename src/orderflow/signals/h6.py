"""H6 - Exhaustion. preregistration/PREREGISTRATION.md section 2, H6."""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import polars as pl

from orderflow.config import H24_HIGH_WINDOW, H6_VOLUME_PCTL, H6_VOLUME_WINDOW


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


def detect(bars: pl.DataFrame, buckets: pl.DataFrame) -> pl.DataFrame:
    b = bars.sort("bar_index").with_columns(
        [
            pl.col("volume").shift(1).rolling_quantile(quantile=H6_VOLUME_PCTL, window_size=H6_VOLUME_WINDOW).alias("p95_2016"),
            pl.col("close").rolling_max(window_size=H24_HIGH_WINDOW).alias("roll_max24"),
            pl.col("close").rolling_min(window_size=H24_HIGH_WINDOW).alias("roll_min24"),
        ]
    )
    b = b.with_columns(
        [
            (pl.col("close") == pl.col("roll_max24")).alias("is_24h_high"),
            (pl.col("close") == pl.col("roll_min24")).alias("is_24h_low"),
        ]
    )

    bar_index_arr = b["bar_index"].to_numpy()
    bar_ts_arr = b["bar_ts"].to_numpy()
    volume_arr = b["volume"].to_numpy()
    p95_arr = b["p95_2016"].to_numpy()
    is_high = b["is_24h_high"].fill_null(False).to_numpy()
    is_low = b["is_24h_low"].fill_null(False).to_numpy()

    vol_gate = ~np.isnan(p95_arr) & (p95_arr > 0) & (volume_arr >= p95_arr)
    bear_candidates = np.nonzero(vol_gate & is_high)[0]
    bull_candidates = np.nonzero(vol_gate & is_low)[0]

    if len(bear_candidates) == 0 and len(bull_candidates) == 0:
        return pl.DataFrame(
            schema={"bar_index": pl.Int64, "bar_ts": pl.Datetime, "signal": pl.Utf8, "direction": pl.Int8, "magnitude": pl.Float64}
        )

    needed = set(bear_candidates.tolist()) | set(bull_candidates.tolist())
    by_bar = _group_buckets_by_bar(buckets.filter(pl.col("bar_index").is_in(list(needed))))

    rows = []
    for i in bear_candidates:
        bi = int(bar_index_arr[i])
        rows_here = by_bar.get(bi)
        if not rows_here:
            continue
        rows_here_sorted = sorted(rows_here, key=lambda r: r[0])
        top2 = rows_here_sorted[-2:]
        combined_delta = sum(bv - sv for _, bv, sv in top2)
        if combined_delta < 0:
            magnitude = (volume_arr[i] / p95_arr[i]) * abs(combined_delta)
            rows.append((bi, bar_ts_arr[i], "H6", -1, float(magnitude)))

    for i in bull_candidates:
        bi = int(bar_index_arr[i])
        rows_here = by_bar.get(bi)
        if not rows_here:
            continue
        rows_here_sorted = sorted(rows_here, key=lambda r: r[0])
        bottom2 = rows_here_sorted[:2]
        combined_delta = sum(bv - sv for _, bv, sv in bottom2)
        if combined_delta > 0:
            magnitude = (volume_arr[i] / p95_arr[i]) * abs(combined_delta)
            rows.append((bi, bar_ts_arr[i], "H6", 1, float(magnitude)))

    if not rows:
        return pl.DataFrame(
            schema={"bar_index": pl.Int64, "bar_ts": pl.Datetime, "signal": pl.Utf8, "direction": pl.Int8, "magnitude": pl.Float64}
        )
    out = pl.DataFrame(
        rows, schema=["bar_index", "bar_ts", "signal", "direction", "magnitude"], orient="row"
    ).with_columns(pl.col("direction").cast(pl.Int8))
    return out.sort("bar_index")
