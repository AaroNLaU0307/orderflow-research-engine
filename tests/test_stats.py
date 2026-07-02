import numpy as np
import pytest

from orderflow import stats


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
