import subprocess
import sys

import numpy as np
import pytest

from orderflow import stats


def test_stable_seed_deterministic_within_process():
    assert stats.stable_seed("H1", 6) == stats.stable_seed("H1", 6)
    assert stats.stable_seed("H1", 6) != stats.stable_seed("H1", 12)
    assert stats.stable_seed("H1", 6) != stats.stable_seed("H2", 6)


def test_stable_seed_deterministic_across_processes():
    """Regression test: hash() on a tuple is randomized per-process by
    default (PYTHONHASHSEED), which silently made bootstrap p-values
    non-reproducible run to run. Verify stable_seed is NOT affected by
    disabling hash randomization in one subprocess and comparing."""
    code = "from orderflow import stats; print(stats.stable_seed('H1', 6))"
    results = set()
    for hashseed in ["0", "1", "12345"]:
        out = subprocess.run(
            [sys.executable, "-c", code],
            cwd=__file__.rsplit("tests", 1)[0] + "src",
            env={"PYTHONHASHSEED": hashseed, "PATH": __import__("os").environ.get("PATH", "")},
            capture_output=True,
            text=True,
        )
        assert out.returncode == 0, out.stderr
        results.add(out.stdout.strip())
    assert len(results) == 1, f"stable_seed varied across PYTHONHASHSEED values: {results}"


def test_day_cluster_bootstrap_clear_positive_mean_is_significant():
    rng = np.random.default_rng(1)
    n_days = 200
    returns, days = [], []
    for d in range(n_days):
        n_events = rng.integers(1, 4)
        for _ in range(n_events):
            returns.append(rng.normal(0.01, 0.005))  # clearly positive, small noise
            days.append(d)
    result = stats.day_cluster_bootstrap_mean(np.array(returns), np.array(days), n_reps=2000, seed=2)
    assert result["observed_mean"] > 0
    assert result["p_value"] < 0.01
    assert result["ci95_lo"] > 0  # CI excludes zero


def test_day_cluster_bootstrap_zero_mean_is_not_significant():
    rng = np.random.default_rng(3)
    n_days = 200
    returns, days = [], []
    for d in range(n_days):
        n_events = rng.integers(1, 4)
        for _ in range(n_events):
            returns.append(rng.normal(0.0, 0.01))  # no true effect
            days.append(d)
    result = stats.day_cluster_bootstrap_mean(np.array(returns), np.array(days), n_reps=2000, seed=4)
    assert result["p_value"] > 0.05
    assert result["ci95_lo"] < 0 < result["ci95_hi"]  # CI straddles zero


def test_day_cluster_bootstrap_pools_within_day_not_per_event():
    """A single outlier day with many events should be weighted by its event
    count in the pooled mean, not treated as one 'day' data point equally
    with a sparse day."""
    returns = np.array([10.0] * 100 + [-10.0] * 1)  # 100 events on day 0, 1 event on day 1
    days = np.array([0] * 100 + [1])
    result = stats.day_cluster_bootstrap_mean(returns, days, n_reps=500, seed=5)
    # naive per-event mean would be dominated by the 100 events; pooled
    # per-resample-day mean should still generally reflect that (since day 0
    # alone, whenever sampled, contributes overwhelmingly positive mean)
    assert result["observed_mean"] == pytest.approx((100 * 10.0 - 10.0) / 101)


def test_day_cluster_bootstrap_mean_batching_matches_single_batch():
    """Precision amendment: day_cluster_bootstrap_mean now processes reps in
    chunks (needed to avoid a ~14GB allocation at n_reps=2,000,000). Chunking
    must be invisible: a numpy Generator seeded once and drawn from
    repeatedly in sequence is exactly as deterministic as one large draw, so
    splitting into small batches must give bit-identical output to one batch
    covering the whole n_reps."""
    rng = np.random.default_rng(11)
    n_days = 60
    returns, days = [], []
    for d in range(n_days):
        for _ in range(rng.integers(1, 4)):
            returns.append(rng.normal(0.0, 0.01))
            days.append(d)
    returns, days = np.array(returns), np.array(days)

    single_batch = stats.day_cluster_bootstrap_mean(returns, days, n_reps=200, seed=99, batch_size=200)
    multi_batch = stats.day_cluster_bootstrap_mean(returns, days, n_reps=200, seed=99, batch_size=37)
    assert np.array_equal(single_batch["boot_means"], multi_batch["boot_means"])
    assert single_batch["p_value"] == multi_batch["p_value"]
    assert single_batch["ci95_lo"] == multi_batch["ci95_lo"]


def test_day_cluster_bootstrap_mean_reps_count_correct_when_not_multiple_of_batch():
    rng = np.random.default_rng(12)
    returns = rng.normal(0, 0.01, 50)
    days = np.arange(50) % 10
    result = stats.day_cluster_bootstrap_mean(returns, days, n_reps=205, seed=1, batch_size=100)
    assert len(result["boot_means"]) == 205


def test_bh_fdr_known_case():
    # classic textbook-style example: 5 p-values, q=0.10
    p_values = [0.001, 0.008, 0.039, 0.041, 0.42]
    result = stats.bh_fdr(p_values, q=0.10)
    # BH thresholds at q=0.10, n=5: [0.02, 0.04, 0.06, 0.08, 0.10]
    # sorted p: 0.001<=0.02 T, 0.008<=0.04 T, 0.039<=0.06 T, 0.041<=0.08 T, 0.42<=0.10 F
    # largest k with p(k)<=threshold(k) is k=4 (0-indexed 3) -> first 4 significant
    assert result == [True, True, True, True, False]


def test_bh_fdr_all_significant_when_all_tiny():
    result = stats.bh_fdr([0.001, 0.002, 0.003], q=0.10)
    assert all(result)


def test_bh_fdr_none_significant_when_all_large():
    result = stats.bh_fdr([0.5, 0.6, 0.9], q=0.10)
    assert not any(result)


def test_bh_fdr_empty():
    assert stats.bh_fdr([], q=0.10) == []


def test_day_cluster_bootstrap_spearman_recovers_strong_monotonic_relationship():
    rng = np.random.default_rng(6)
    n_days = 150
    magnitude, returns, days = [], [], []
    for d in range(n_days):
        m = rng.uniform(0, 5)
        r = m * 0.01 + rng.normal(0, 0.001)  # strong monotonic relationship
        magnitude.append(m)
        returns.append(r)
        days.append(d)
    result = stats.day_cluster_bootstrap_spearman(np.array(magnitude), np.array(returns), np.array(days), n_reps=500, seed=7)
    assert result["ic"] > 0.9
    assert result["ci95_lo"] > 0.5


def test_day_cluster_bootstrap_spearman_no_relationship_ci_straddles_zero():
    rng = np.random.default_rng(8)
    n_days = 150
    magnitude, returns, days = [], [], []
    for d in range(n_days):
        magnitude.append(rng.uniform(0, 5))
        returns.append(rng.normal(0, 0.01))
        days.append(d)
    result = stats.day_cluster_bootstrap_spearman(np.array(magnitude), np.array(returns), np.array(days), n_reps=500, seed=9)
    assert result["ci95_lo"] < 0 < result["ci95_hi"]


def _flat_price_with_jumps(n_is_bars, jump_bar_indices, jump_size, horizons):
    """log-price array that is flat everywhere except a permanent +jump_size
    step starting one bar after each index in jump_bar_indices - so an event
    at bar_index b sees r(h) == jump_size for every h in horizons (the jump
    lands strictly between entry=b+1 and entry+1), while a shift landing on
    flat ground (no jump anywhere in its own forward window) sees r(h)==0."""
    logp = np.zeros(n_is_bars)
    for b in jump_bar_indices:
        logp[b + 2 :] += jump_size
    return np.exp(logp)


def test_circular_shift_placebo_deterministic():
    n_is_bars, warm_up_bars, horizons = 20_000, 1_000, [1, 5, 10]
    bar_index = np.array([3000, 6000, 9000, 12000, 15000])
    direction = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
    is_open = _flat_price_with_jumps(n_is_bars, bar_index, 0.01, horizons)
    is_bar_ts_ms = np.arange(n_is_bars, dtype=np.int64) * 300_000
    observed_means = {h: 0.01 for h in horizons}
    kwargs = dict(
        bar_index=bar_index, direction=direction, observed_means=observed_means, is_open=is_open,
        is_bar_ts_ms=is_bar_ts_ms, n_is_bars=n_is_bars, warm_up_bars=warm_up_bars, horizons=horizons,
        quarantine_windows=[], bar_ms=300_000, k=500, min_shift=2016,
    )
    a = stats.circular_shift_placebo(seed=42, **kwargs)
    b = stats.circular_shift_placebo(seed=42, **kwargs)
    c = stats.circular_shift_placebo(seed=43, **kwargs)
    for h in horizons:
        assert a[h]["placebo_p"] == b[h]["placebo_p"]
        assert a[h]["n_shifts"] == b[h]["n_shifts"]
    assert any(a[h]["placebo_p"] != c[h]["placebo_p"] for h in horizons)


def test_circular_shift_placebo_detects_engineered_alignment():
    """A deterministic, isolated +100bp jump at each event's true position
    (and nowhere else nearby) should be essentially unreproducible by random
    circular shifts - placebo_p should be tiny, demonstrating the test has
    power, not just that it runs."""
    n_is_bars, warm_up_bars, horizons = 100_000, 1_000, [1, 5, 10]
    bar_index = np.arange(2_000, 90_000, 3_000)  # 30 events, isolated, far apart
    direction = np.ones(len(bar_index))
    is_open = _flat_price_with_jumps(n_is_bars, bar_index, 0.01, horizons)
    is_bar_ts_ms = np.arange(n_is_bars, dtype=np.int64) * 300_000
    observed_means = {h: 0.01 for h in horizons}  # matches the engineered jump exactly
    result = stats.circular_shift_placebo(
        bar_index=bar_index, direction=direction, observed_means=observed_means, is_open=is_open,
        is_bar_ts_ms=is_bar_ts_ms, n_is_bars=n_is_bars, warm_up_bars=warm_up_bars, horizons=horizons,
        quarantine_windows=[], bar_ms=300_000, k=2000, seed=7, min_shift=2016,
    )
    for h in horizons:
        assert result[h]["placebo_p"] < 0.02
        assert result[h]["mean_admitted_fraction"] > 0.9


def test_circular_shift_placebo_warmup_admission_fraction_matches_expectation():
    """With no quarantine windows, the expected fraction of (shift, event)
    pairs admitted on the warm-up check alone is ~(n_is_bars - warm_up_bars)
    / n_is_bars (a shifted bar_index lands ~uniformly in [0, n_is_bars)
    circular space, minus the min_shift near-identity exclusion band around
    each event's own original position). n_is_bars is kept large relative to
    min_shift (2016) here so that exclusion-band edge effects are negligible
    and the plain ratio holds to within a tight tolerance - at the scale this
    project actually runs the placebo at (n_is_bars ~263,000), that ratio
    holds even better than the 1,000,000-bar setup tested here."""
    n_is_bars, warm_up_bars, horizons = 1_000_000, 800_000, [1]  # huge warm-up band (80%)
    rng = np.random.default_rng(5)
    bar_index = rng.integers(warm_up_bars, n_is_bars - 100, size=200)  # all real events start admitted
    direction = np.ones(len(bar_index))
    is_open = np.ones(n_is_bars)  # flat price: r is always 0, only admission fraction matters here
    is_bar_ts_ms = np.arange(n_is_bars, dtype=np.int64) * 300_000
    result = stats.circular_shift_placebo(
        bar_index=bar_index, direction=direction, observed_means={1: 0.0}, is_open=is_open,
        is_bar_ts_ms=is_bar_ts_ms, n_is_bars=n_is_bars, warm_up_bars=warm_up_bars, horizons=horizons,
        quarantine_windows=[], bar_ms=300_000, k=3000, seed=13, min_shift=2016,
    )
    expected_fraction = (n_is_bars - warm_up_bars) / n_is_bars  # 0.2
    assert result[1]["mean_admitted_fraction"] == pytest.approx(expected_fraction, abs=0.02)


def test_circular_shift_placebo_quarantine_reduces_admission():
    n_is_bars, warm_up_bars, horizons = 50_000, 1_000, [1]
    bar_index = np.arange(2_000, 48_000, 200)  # 230 events, evenly spread
    direction = np.ones(len(bar_index))
    is_open = np.ones(n_is_bars)
    bar_ms = 300_000
    is_bar_ts_ms = np.arange(n_is_bars, dtype=np.int64) * bar_ms
    # quarantine covering roughly the middle third of the IS bar range
    q_start_ms = int(is_bar_ts_ms[n_is_bars // 3])
    q_end_ms = int(is_bar_ts_ms[2 * n_is_bars // 3])
    no_quarantine = stats.circular_shift_placebo(
        bar_index=bar_index, direction=direction, observed_means={1: 0.0}, is_open=is_open,
        is_bar_ts_ms=is_bar_ts_ms, n_is_bars=n_is_bars, warm_up_bars=warm_up_bars, horizons=horizons,
        quarantine_windows=[], bar_ms=bar_ms, k=1000, seed=21, min_shift=2016,
    )
    with_quarantine = stats.circular_shift_placebo(
        bar_index=bar_index, direction=direction, observed_means={1: 0.0}, is_open=is_open,
        is_bar_ts_ms=is_bar_ts_ms, n_is_bars=n_is_bars, warm_up_bars=warm_up_bars, horizons=horizons,
        quarantine_windows=[(q_start_ms, q_end_ms)], bar_ms=bar_ms, k=1000, seed=21, min_shift=2016,
    )
    assert with_quarantine[1]["mean_admitted_fraction"] < no_quarantine[1]["mean_admitted_fraction"]
