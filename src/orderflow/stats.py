"""Statistical primitives for the event study (preregistration section 6).

Day-cluster bootstrap: resample calendar days with replacement (restricted
to days containing >=1 event of the cell), pool all events on the resampled
days, recompute the statistic. This is the concrete implementation of the
brief's "stationary block bootstrap... to respect overlap/serial
dependence" (section 6.2).
"""
from __future__ import annotations

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
    returns: np.ndarray, event_days: np.ndarray, n_reps: int = 10_000, seed: int | None = None
) -> dict:
    """Two-sided bootstrap p-value (H0: true mean signed return = 0) plus the
    bootstrap distribution of the pooled mean, for CI construction.

    Vectorized via per-day (sum, count) aggregation: since the pooled mean of
    a set of resampled days is sum(day sums)/sum(day counts), all n_reps
    resamples can be computed as one (n_reps x n_days) gather-and-sum instead
    of a per-rep Python loop.
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

    sampled = rng.integers(0, n_days, size=(n_reps, n_days))
    boot_sum = day_sum[sampled].sum(axis=1)
    boot_count = day_count[sampled].sum(axis=1)
    boot_means = boot_sum / boot_count

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
