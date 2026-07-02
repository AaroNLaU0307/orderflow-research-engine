"""H1 - Delta divergence. preregistration/PREREGISTRATION.md section 2, H1."""
from __future__ import annotations

import numpy as np
import polars as pl

from orderflow.config import H1_CUMDELTA_WINDOW, H1_SIGMA_WINDOW, H24_HIGH_WINDOW
from orderflow.events import assemble_events
from orderflow.rolling import gather_or_nan, last_true_index_strictly_before


def detect(
    bars: pl.DataFrame,
    cumdelta_window: int = H1_CUMDELTA_WINDOW,
    sigma_window: int = H1_SIGMA_WINDOW,
    high_window: int = H24_HIGH_WINDOW,
) -> pl.DataFrame:
    """Window sizes default to the preregistered 5-minute-bar convention;
    override to run the section-8 sensitivity grid at a different bar
    duration with wall-clock-preserving rescaled windows."""
    b = bars.sort("bar_index").with_columns(
        [
            pl.col("delta").rolling_sum(window_size=cumdelta_window).alias("cumD24"),
            pl.col("close").rolling_max(window_size=high_window).alias("roll_max24"),
            pl.col("close").rolling_min(window_size=high_window).alias("roll_min24"),
        ]
    )
    b = b.with_columns(
        [
            (pl.col("close") == pl.col("roll_max24")).alias("is_24h_high"),
            (pl.col("close") == pl.col("roll_min24")).alias("is_24h_low"),
        ]
    )
    b = b.with_columns(pl.col("cumD24").shift(1).rolling_std(window_size=sigma_window).alias("sigma"))

    bar_index = b["bar_index"].to_numpy()
    cumD24 = b["cumD24"].to_numpy()
    sigma = b["sigma"].to_numpy()
    is_high = b["is_24h_high"].fill_null(False).to_numpy()
    is_low = b["is_24h_low"].fill_null(False).to_numpy()

    s_high = last_true_index_strictly_before(is_high)
    s_low = last_true_index_strictly_before(is_low)
    cumD24_at_s_high = gather_or_nan(cumD24, s_high)
    cumD24_at_s_low = gather_or_nan(cumD24, s_low)

    valid = ~np.isnan(sigma)

    bear_mask = is_high & valid & (s_high >= 0) & ~np.isnan(cumD24_at_s_high) & (cumD24 < cumD24_at_s_high - 0.5 * sigma)
    bull_mask = is_low & valid & (s_low >= 0) & ~np.isnan(cumD24_at_s_low) & (cumD24 > cumD24_at_s_low + 0.5 * sigma)

    bear_mag = np.abs(cumD24 - cumD24_at_s_high) / sigma
    bull_mag = np.abs(cumD24 - cumD24_at_s_low) / sigma

    rows = []
    for i in np.nonzero(bear_mask)[0]:
        rows.append((int(bar_index[i]), "H1", -1, float(bear_mag[i])))
    for i in np.nonzero(bull_mask)[0]:
        rows.append((int(bar_index[i]), "H1", 1, float(bull_mag[i])))

    return assemble_events(b, rows)
