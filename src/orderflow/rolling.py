"""Rolling-window helpers shared by the H1-H6 detectors.

All "trailing N-bar" reference statistics (H1 sigma, H2 med96, H3 p25_96, H6
P95_2016) are computed over the window strictly BEFORE the current bar,
i.e. bars [t-N, t-1], excluding bar t itself. This is the standard
convention for a spike/threshold detector (the current bar is compared
against an independently-established baseline, not one it contributes to);
the numerical effect of the alternative (inclusive) convention is negligible
at these window sizes (1 part in 96-8640) and does not change which signals
would pass the promotion gates, but the choice is recorded here since the
preregistration's pseudocode does not spell it out.
"""
from __future__ import annotations

import numpy as np
from sortedcontainers import SortedList


def last_true_index_strictly_before(flag: np.ndarray) -> np.ndarray:
    """For each t, the largest index s <= t-1 with flag[s] True, else -1."""
    n = len(flag)
    idx_if_true = np.where(flag, np.arange(n), -1)
    running_max = np.maximum.accumulate(idx_if_true)
    result = np.empty(n, dtype=np.int64)
    result[0] = -1
    if n > 1:
        result[1:] = running_max[:-1]
    return result


def gather_or_nan(values: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """values[indices], with -1 (sentinel: no valid index) mapped to NaN."""
    out = np.full(len(indices), np.nan)
    valid = indices >= 0
    out[valid] = values[indices[valid]]
    return out


def rolling_pooled_percentile(
    bar_index_per_row: np.ndarray,
    value_per_row: np.ndarray,
    n_bars: int,
    window: int,
    pctl: float,
) -> np.ndarray:
    """For each bar t in [0, n_bars), the `pctl` percentile (0..1) of every
    value_per_row entry whose bar_index falls in [t-window, t-1], pooled
    (not averaged per-bar). `bar_index_per_row` must be sorted ascending
    (true of the persisted bucket store, which is sorted by bar_index).
    Returns NaN for bars where the window is empty.
    """
    by_bar: dict[int, list[float]] = {}
    for b, v in zip(bar_index_per_row.tolist(), value_per_row.tolist()):
        by_bar.setdefault(b, []).append(v)

    sl: SortedList = SortedList()
    result = np.full(n_bars, np.nan)
    for t in range(n_bars):
        add_bar = t - 1
        if add_bar >= 0:
            for v in by_bar.get(add_bar, ()):
                sl.add(v)
        remove_bar = t - 1 - window
        if remove_bar >= 0:
            for v in by_bar.get(remove_bar, ()):
                sl.remove(v)
        n = len(sl)
        if n > 0:
            k = min(int(pctl * n), n - 1)
            result[t] = sl[k]
    return result
