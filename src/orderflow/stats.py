"""Statistical primitives for the event study (preregistration section 6).

Day-cluster bootstrap: resample calendar days with replacement (restricted
to days containing >=1 event of the cell), pool all events on the resampled
days, recompute the statistic. This is the concrete implementation of the
brief's "stationary block bootstrap... to respect overlap/serial
dependence" (section 6.2).
"""
from __future__ import annotations

import warnings
import zlib

import numpy as np
from scipy import stats as scipy_stats


def stable_seed(*parts: object) -> int:
    """Deterministic RNG seed from arbitrary parts (e.g. signal name,
    horizon, config label) - stable across Python processes and runs.

    Python's built-in hash() is randomized per-process by default (PEP 456
    hash randomization, PYTHONHASHSEED) for str/bytes/tuples-of-those; using
    it for a bootstrap seed makes every reported p-value/CI silently
    non-reproducible run to run. zlib.crc32 over a fixed string encoding has
    no such randomization.
    """
    key = "|".join(str(p) for p in parts).encode("utf-8")
    return zlib.crc32(key) % (2**31)


def day_cluster_bootstrap_mean(
    returns: np.ndarray, event_days: np.ndarray, n_reps: int = 10_000, seed: int | None = None, batch_size: int = 50_000
) -> dict:
    """Two-sided bootstrap p-value (H0: true mean signed return = 0) plus the
    bootstrap distribution of the pooled mean, for CI construction.

    Vectorized via per-day (sum, count) aggregation: since the pooled mean of
    a set of resampled days is sum(day sums)/sum(day counts), each batch of
    reps can be computed as one (batch x n_days) gather-and-sum instead of a
    per-rep Python loop. Processed in batches of `batch_size` reps rather than
    materializing all n_reps at once: at n_reps=2,000,000 and n_days~900
    (H1's IS event-day count), a single (n_reps x n_days) int64 array would be
    ~14GB. Batching bounds peak memory regardless of n_reps while leaving
    results for n_reps<=batch_size (all pre-existing call sites) bit-for-bit
    identical to the original unbatched single-call behavior, since a single
    rng seeded once and drawn from repeatedly in sequence is exactly as
    deterministic/reproducible as one large draw.
    """
    returns = np.asarray(returns, dtype=float)
    rng = np.random.default_rng(seed)
    unique_days, day_idx = np.unique(event_days, return_inverse=True)
    n_days = len(unique_days)

    day_sum = np.zeros(n_days)
    day_count = np.zeros(n_days)
    np.add.at(day_sum, day_idx, returns)
    np.add.at(day_count, day_idx, 1)

    observed_mean = float(returns.mean())

    boot_means = np.empty(n_reps, dtype=np.float64)
    done = 0
    while done < n_reps:
        this_batch = min(batch_size, n_reps - done)
        sampled = rng.integers(0, n_days, size=(this_batch, n_days))
        boot_sum = day_sum[sampled].sum(axis=1)
        boot_count = day_count[sampled].sum(axis=1)
        boot_means[done : done + this_batch] = boot_sum / boot_count
        done += this_batch

    p_le = float(np.mean(boot_means <= 0))
    p_ge = float(np.mean(boot_means >= 0))
    p_value = min(1.0, 2 * min(p_le, p_ge))

    ci_lo, ci_hi = np.percentile(boot_means, [2.5, 97.5])

    return {
        "observed_mean": observed_mean,
        "p_value": p_value,
        "ci95_lo": float(ci_lo),
        "ci95_hi": float(ci_hi),
        "n_events": len(returns),
        "n_days": n_days,
        "boot_means": boot_means,
    }


def day_cluster_bootstrap_spearman(
    magnitude: np.ndarray, returns: np.ndarray, event_days: np.ndarray, n_reps: int = 10_000, seed: int | None = None
) -> dict:
    """Spearman IC between event magnitude and forward signed return, with a
    day-cluster bootstrap 95% CI. Informational only (never a gating
    criterion, preregistration section 6.2).
    """
    magnitude = np.asarray(magnitude, dtype=float)
    returns = np.asarray(returns, dtype=float)
    event_days = np.asarray(event_days)
    rng = np.random.default_rng(seed)

    unique_days = np.unique(event_days)
    n_days = len(unique_days)
    day_to_positions = {d: np.where(event_days == d)[0] for d in unique_days}

    if len(magnitude) < 2 or np.all(magnitude == magnitude[0]) or np.all(returns == returns[0]):
        observed_ic = float("nan")
    else:
        observed_ic = float(scipy_stats.spearmanr(magnitude, returns).statistic)

    boot_ics = np.empty(n_reps)
    for i in range(n_reps):
        sampled_days = unique_days[rng.integers(0, n_days, size=n_days)]
        idx = np.concatenate([day_to_positions[d] for d in sampled_days])
        m, r = magnitude[idx], returns[idx]
        if len(m) < 2 or np.all(m == m[0]) or np.all(r == r[0]):
            boot_ics[i] = np.nan
        else:
            boot_ics[i] = scipy_stats.spearmanr(m, r).statistic

    valid = boot_ics[~np.isnan(boot_ics)]
    if len(valid) == 0:
        ci_lo, ci_hi = float("nan"), float("nan")
    else:
        ci_lo, ci_hi = np.percentile(valid, [2.5, 97.5])

    return {"ic": observed_ic, "ci95_lo": float(ci_lo), "ci95_hi": float(ci_hi), "n_valid_reps": len(valid)}


def circular_shift_placebo(
    bar_index: np.ndarray,
    direction: np.ndarray,
    observed_means: dict[int, float],
    is_open: np.ndarray,
    is_bar_ts_ms: np.ndarray,
    n_is_bars: int,
    warm_up_bars: int,
    horizons: list[int],
    quarantine_windows: list[tuple[int, int]],
    bar_ms: int,
    k: int = 10_000,
    seed: int | None = None,
    batch_size: int = 500,
    min_shift: int = 2016,
) -> dict[int, dict]:
    """Circular-shift placebo test (supplementary, non-gating - see
    preregistration/DEVIATIONS.md entry 2). For one signal's deduplicated
    BTC in-sample event set, draws `k` circular shifts; each shift applies
    ONE random offset to ALL of the signal's event bar-indices simultaneously
    (preserving intra-signal clustering exactly), wrapping within the IS bar
    range [0, n_is_bars) - valid here because bar_index 0 coincides with
    IS_START (config.STUDY_START == config.IS_START), so bar_index IS the
    IS-relative index directly, no offset needed. Direction labels travel
    with their events.

    Admission (per event, per shift) mirrors the real pipeline's two-stage
    hygiene - drop for that replicate if either check fails:
      1. the shifted trigger bar itself falls in warm-up (bar_index <
         warm_up_bars) or overlaps a quarantine window (real-space
         equivalent: events.apply_warmup + quarantine.filter_quarantined_events).
      2. its longest-horizon (max(horizons)) forward window, evaluated once
         per event and shared across all horizons - exactly like
         eventstudy.add_forward_returns's purge_ok - overlaps a quarantine
         window. A window that would need to wrap past the end of the IS
         range is handled by the same check without a separate branch: the
         wrapped remainder is at most max(horizons) bars long, far short of
         warm_up_bars, so it always re-enters the warm-up region and is
         already excluded by requiring the window's end index to stay
         within [0, n_is_bars).

    Rationale: circular shifting preserves the entire return series, so
    unconditional drift sits inside the null - this tests event-return
    *alignment* net of market beta (bull-market beta masquerading as
    signal), the one failure channel the day-cluster bootstrap alone does
    not isolate.

    Returns {horizon: {"placebo_p": float, "n_shifts": int,
    "mean_admitted_fraction": float}}. placebo_p is two-sided: the fraction
    of shifts whose |mean signed forward return| >= |observed|.
    """
    bar_index = np.asarray(bar_index, dtype=np.int64)
    direction = np.asarray(direction, dtype=np.float64)
    max_h = max(horizons)
    rng = np.random.default_rng(seed)

    per_h_means = {h: np.empty(k, dtype=np.float64) for h in horizons}
    admitted_fracs = np.empty(k, dtype=np.float64)

    done = 0
    while done < k:
        this_batch = min(batch_size, k - done)
        deltas = rng.integers(min_shift, n_is_bars - min_shift + 1, size=this_batch)
        new_bar_index = (bar_index[None, :] + deltas[:, None]) % n_is_bars  # (batch, n_events)
        entry_idx = new_bar_index + 1
        target48 = entry_idx + max_h

        admitted = new_bar_index >= warm_up_bars
        admitted &= target48 < n_is_bars

        trigger_ts = is_bar_ts_ms[new_bar_index]
        entry_ts = is_bar_ts_ms[np.clip(entry_idx, 0, n_is_bars - 1)]
        target48_ts = is_bar_ts_ms[np.clip(target48, 0, n_is_bars - 1)]
        for qs, qe in quarantine_windows:
            admitted &= ~((trigger_ts < qe) & (trigger_ts + bar_ms > qs))
            admitted &= ~((entry_ts < qe) & (target48_ts + bar_ms > qs))

        entry_open = is_open[np.clip(entry_idx, 0, n_is_bars - 1)]
        for h in horizons:
            target_h = np.clip(entry_idx + h, 0, n_is_bars - 1)
            target_open = is_open[target_h]
            r = direction[None, :] * np.log(target_open / entry_open)
            r = np.where(admitted, r, np.nan)
            # a shift landing every event of a (small/heavily-clustered)
            # signal in warm-up/quarantine simultaneously would leave an
            # all-NaN row; nanmean's "Mean of empty slice" RuntimeWarning is
            # raised via warnings.warn (not the floating-point error state
            # np.errstate controls), so it must be silenced explicitly - the
            # resulting NaN is already handled downstream via `valid`.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=RuntimeWarning)
                per_h_means[h][done : done + this_batch] = np.nanmean(r, axis=1)

        admitted_fracs[done : done + this_batch] = admitted.mean(axis=1)
        done += this_batch

    out = {}
    for h in horizons:
        means = per_h_means[h]
        valid = ~np.isnan(means)
        observed_abs = abs(observed_means[h])
        placebo_p = float(np.mean(np.abs(means[valid]) >= observed_abs)) if valid.any() else float("nan")
        out[h] = {
            "placebo_p": placebo_p,
            "n_shifts": int(valid.sum()),
            "mean_admitted_fraction": float(admitted_fracs.mean()),
        }
    return out


def bh_fdr(p_values: list[float], q: float = 0.10) -> list[bool]:
    """Benjamini-Hochberg step-up procedure. Returns a boolean per input
    p-value (same order), True iff significant at FDR level q."""
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    if n == 0:
        return []
    order = np.argsort(p)
    ranked = p[order]
    thresholds = (np.arange(1, n + 1) / n) * q
    below = ranked <= thresholds
    result_sorted = np.zeros(n, dtype=bool)
    if below.any():
        max_k = int(np.max(np.where(below)[0]))
        result_sorted[: max_k + 1] = True
    result = np.zeros(n, dtype=bool)
    result[order] = result_sorted
    return result.tolist()
