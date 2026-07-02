"""Event study: forward returns, segment purging, and the promotion-gate
pipeline. preregistration/PREREGISTRATION.md sections 5, 6.

Boundary comparisons use epoch-ms integers throughout, not datetime
objects: polars' `.to_numpy()` on a tz-aware Datetime column returns bare
`numpy.datetime64` (no tzinfo concept), which raises TypeError if compared
against a tz-aware Python `datetime` - comparing plain integers sidesteps
this entirely and is also faster.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from orderflow import stats
from orderflow.config import (
    IS_END_MS,
    IS_SEGMENTS_MS,
    IS_START_MS,
    MATERIALITY_BP,
    MIN_EVENTS,
    MIN_MATERIAL_HORIZON_BARS,
    OOS_END_MS,
    OOS_START_MS,
)
from orderflow.config import HORIZONS_BARS  # noqa: F401 (re-exported for callers)


def _to_ms(bar_ts_series: pl.Series) -> np.ndarray:
    """epoch-ms int64 array from a polars Datetime column, robust to
    whatever time_unit/time_zone it's stored with."""
    return bar_ts_series.dt.epoch(time_unit="ms").to_numpy()


def segment_of_ms(ts_ms) -> str | None:
    if IS_START_MS <= ts_ms <= IS_END_MS:
        return "IS"
    if OOS_START_MS <= ts_ms <= OOS_END_MS:
        return "OOS"
    return None


def segment_of(bar_ts: "object") -> str | None:
    """Convenience wrapper for a single Python datetime (tz-aware)."""
    return segment_of_ms(int(bar_ts.timestamp() * 1000))


def add_forward_returns(events: pl.DataFrame, bars: pl.DataFrame, horizons: list[int] = HORIZONS_BARS) -> pl.DataFrame:
    """For each event at bar_index t, direction d: r(h) = d * log(open[t+1+h]
    / open[t+1]) for each horizon h, using only bars that exist (no
    wraparound/extrapolation). Also computes the segment of the event
    itself, and applies the section-5 purge rule: `purge_ok` is True only
    if bar_index + 1 + max(horizons) is within the same IS/OOS segment as
    the event. Downstream code should filter on `purge_ok` before computing
    per-segment statistics - the per-event r(h) columns are populated
    regardless, since a diagnostic caller may want the raw values.
    """
    if events.height == 0:
        out = events.clone()
        for h in horizons:
            out = out.with_columns(pl.lit(None).cast(pl.Float64).alias(f"r_{h}"))
        return out.with_columns([pl.lit(None).cast(pl.Utf8).alias("segment"), pl.lit(False).alias("purge_ok")])

    bars_sorted = bars.sort("bar_index")
    n_bars = bars_sorted.height
    open_arr = bars_sorted["open"].to_numpy()
    bar_ts_ms_arr = _to_ms(bars_sorted["bar_ts"])

    t = events["bar_index"].to_numpy()
    direction = events["direction"].to_numpy().astype(float)
    event_ts_ms = _to_ms(events["bar_ts"])

    entry_idx = t + 1
    entry_valid = entry_idx < n_bars
    entry_open = np.where(entry_valid, open_arr[np.clip(entry_idx, 0, n_bars - 1)], np.nan)

    out = events.clone()
    for h in horizons:
        target_idx = t + 1 + h
        valid = entry_valid & (target_idx < n_bars)
        target_open = np.where(valid, open_arr[np.clip(target_idx, 0, n_bars - 1)], np.nan)
        r = direction * np.log(target_open / entry_open)
        r = np.where(valid, r, np.nan)
        # NaN != null in polars: is_not_null() would NOT filter out these
        # out-of-bounds rows if left as NaN, silently corrupting downstream
        # cell_stats(). fill_nan(None) converts them to true nulls.
        out = out.with_columns(pl.Series(f"r_{h}", r).fill_nan(None))

    max_h = max(horizons)
    longest_target_idx = t + 1 + max_h
    longest_valid = entry_valid & (longest_target_idx < n_bars)

    segments = [segment_of_ms(int(ms)) for ms in event_ts_ms]
    longest_target_ms = np.where(longest_valid, bar_ts_ms_arr[np.clip(longest_target_idx, 0, n_bars - 1)], -1)
    target_segments = [segment_of_ms(int(ms)) if valid else None for ms, valid in zip(longest_target_ms, longest_valid)]

    purge_ok = [
        bool(longest_valid[i]) and segments[i] is not None and segments[i] == target_segments[i]
        for i in range(len(t))
    ]

    out = out.with_columns([pl.Series("segment", segments), pl.Series("purge_ok", purge_ok)])
    return out


def event_day_bucket(bar_ts_series: pl.Series) -> np.ndarray:
    """Calendar-day bucket per event (day resolution), for day-cluster
    bootstrap grouping - vectorized truncation via numpy's 'D' (day) unit,
    robust to the bare-datetime64 .to_numpy() representation."""
    ms = _to_ms(bar_ts_series)
    return (ms // 86_400_000).astype(np.int64)  # whole UTC calendar days since epoch


def cell_stats(
    events: pl.DataFrame, horizon: int, n_reps: int = 10_000, seed: int | None = None, ic_n_reps: int | None = None
) -> dict:
    """Event-study statistics for one (signal, horizon) cell: mean signed
    return, day-cluster bootstrap p-value + CI, Spearman IC + CI. `events`
    must already be filtered to the relevant signal + purge_ok + segment.

    `ic_n_reps` (defaults to `n_reps` if not given) lets the Spearman IC
    bootstrap use a different rep count than the primary mean-return
    bootstrap: `day_cluster_bootstrap_spearman` is an unvectorized per-rep
    Python loop (unlike the mean bootstrap, which is fully vectorized), so
    running it at the same high precision as the gating statistic would be
    needlessly slow for a value that preregistration section 6.2 states is
    "informational only - never a gating criterion".
    """
    col = f"r_{horizon}"
    sub = events.filter(pl.col(col).is_not_null())
    if sub.height == 0:
        return {"n_events": 0, "observed_mean": float("nan"), "p_value": float("nan")}
    returns = sub[col].to_numpy()
    days = event_day_bucket(sub["bar_ts"])
    boot = stats.day_cluster_bootstrap_mean(returns, days, n_reps=n_reps, seed=seed)
    ic = stats.day_cluster_bootstrap_spearman(sub["magnitude"].to_numpy(), returns, days, n_reps=ic_n_reps or n_reps, seed=seed)
    return {
        "n_events": sub.height,
        "observed_mean": boot["observed_mean"],
        "p_value": boot["p_value"],
        "ci95_lo": boot["ci95_lo"],
        "ci95_hi": boot["ci95_hi"],
        "spearman_ic": ic["ic"],
        "ic_ci95_lo": ic["ci95_lo"],
        "ic_ci95_hi": ic["ci95_hi"],
    }


def year_consistency(events: pl.DataFrame, horizon: int) -> dict:
    """Sign of mean signed return in each of the 3 IS segments (2022H2,
    2023, 2024), and whether >=2 of 3 agree in sign. `events` should already
    be filtered to purge_ok IS events for one signal.
    """
    col = f"r_{horizon}"
    ts_ms = _to_ms(events["bar_ts"])
    r = events[col].to_numpy()
    signs = {}
    for name, (start_ms, end_ms) in IS_SEGMENTS_MS.items():
        mask = (ts_ms >= start_ms) & (ts_ms <= end_ms) & ~np.isnan(r)
        if not mask.any():
            signs[name] = None
            continue
        m = r[mask].mean()
        signs[name] = 1 if m > 0 else (-1 if m < 0 else 0)
    present = [s for s in signs.values() if s is not None and s != 0]
    consistent = False
    if len(present) >= 2:
        pos = sum(1 for s in present if s == 1)
        neg = sum(1 for s in present if s == -1)
        consistent = pos >= 2 or neg >= 2
    return {"segment_signs": signs, "consistent": consistent}


def promotion_decision(signal_cells: dict[int, dict], is_events_by_horizon_ok: dict[int, pl.DataFrame]) -> dict:
    """signal_cells: {horizon: cell_stats-dict-with-'bh_significant'-added}.
    Implements preregistration section 6.5's four gates and h* selection.
    """
    n_events = max((c["n_events"] for c in signal_cells.values()), default=0)
    gate1 = n_events >= MIN_EVENTS

    sig_horizons = [h for h, c in signal_cells.items() if c.get("bh_significant")]
    gate2 = len(sig_horizons) >= 2 and any(h >= MIN_MATERIAL_HORIZON_BARS for h in sig_horizons)

    eligible = [
        h
        for h, c in signal_cells.items()
        if c.get("bh_significant")
        and h >= MIN_MATERIAL_HORIZON_BARS
        and c["observed_mean"] * 10_000 >= MATERIALITY_BP  # log-return * 1e4 ~= bp
    ]
    gate3 = len(eligible) > 0

    h_star = None
    if eligible:
        best_t = -np.inf
        for h in eligible:
            c = signal_cells[h]
            se = (c["ci95_hi"] - c["ci95_lo"]) / (2 * 1.96) if c["ci95_hi"] is not None else np.nan
            t_stat = abs(c["observed_mean"]) / se if se and se > 0 else -np.inf
            if t_stat > best_t or (t_stat == best_t and (h_star is None or h > h_star)):
                best_t = t_stat
                h_star = h

    gate4 = False
    yc = None
    if h_star is not None and h_star in is_events_by_horizon_ok:
        yc = year_consistency(is_events_by_horizon_ok[h_star], h_star)
        gate4 = yc["consistent"]

    promoted = gate1 and gate2 and gate3 and gate4
    return {
        "gate1_min_events": gate1,
        "gate2_fdr": gate2,
        "gate3_materiality": gate3,
        "gate4_year_consistency": gate4,
        "eligible_horizons": eligible,
        "h_star": h_star,
        "year_consistency_detail": yc,
        "promoted": promoted,
    }
