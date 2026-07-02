"""Focused correctness tests for each detector's core logic, using a large
synthetic fixture with deliberately engineered trigger bars (see
tests/fixtures.py). Each injected bar's expected outcome was cross-checked
by hand against the preregistration's pseudocode before being locked in here
(see the H2/H3 magnitude assertions, which reproduce the formula by hand).
"""
import numpy as np
import pytest

from orderflow.signals import h1, h2, h3, h6

from fixtures import FixtureBuilder

N_BARS = 9100
T1 = 8700  # H1 bearish
T2 = 8750  # H2 bullish (absorption at lows)
T3 = 8800  # H3 up-run (bullish stacked imbalance)
T4 = 8900  # H6 bearish (exhaustion at highs)


@pytest.fixture(scope="module")
def fixture():
    fb = FixtureBuilder(N_BARS, seed=42)

    # H1 bearish: anchor high at T1-24 with huge positive cumD24, fresh higher
    # high at T1 with ~zero cumD24 -> clears the 0.5*sigma divergence gate by
    # a wide margin regardless of the exact sigma estimate.
    fb.inject_clean_new_high(T1, jump=200.0, anchor_offset=500.0)
    fb.set_delta_run(T1 - 24 - 23, 24, delta_value=100.0, volume_value=100.0)
    fb.set_delta_run(T1 - 23, 24, delta_value=0.0, volume_value=20.0)

    # H2 bullish: heavy sell (85%) into a bottom-of-range bucket, 10x median
    # bucket volume, price refuses to break below it.
    fb.override_buckets(
        T2,
        [(50_000.0, 30.0, 170.0), (50_025.0, 20.0, 20.0), (50_050.0, 15.0, 10.0)],
    )
    fb.low[T2] = 50_000.0
    fb.high[T2] = 50_100.0
    fb.close[T2] = 50_040.0  # >= p(50000) + Delta(25)
    fb.open[T2] = 50_010.0

    # H3 up-run: 5 levels, buy/sell engineered so k=1,2,3 are all imbalanced_up
    # (ratios 4.0, 5.0, 5.714286) and k=4 is blocked (sell floor fails).
    base_level = 2000
    levels_px = [(base_level + k) * 25.0 for k in range(5)]
    fb.override_buckets(
        T3,
        [
            (levels_px[0], 10.0, 50.0),
            (levels_px[1], 200.0, 60.0),
            (levels_px[2], 300.0, 70.0),
            (levels_px[3], 400.0, 0.0),
            (levels_px[4], 5.0, 5.0),
        ],
    )
    fb.low[T3] = levels_px[0]
    fb.high[T3] = levels_px[4] + 25.0
    fb.close[T3] = levels_px[2]

    # H6 bearish: fresh high + 25x volume spike + negative top-2-bucket delta.
    fb.inject_clean_new_high(T4, jump=200.0, anchor_offset=500.0)
    top_level = int(np.floor(fb.high[T4] / 25.0))
    fb.override_buckets(
        T4,
        [
            ((top_level - 3) * 25.0, 10.0, 10.0),
            ((top_level - 2) * 25.0, 10.0, 10.0),
            ((top_level - 1) * 25.0, 20.0, 300.0),
            (top_level * 25.0, 20.0, 300.0),
        ],
    )
    fb.volume[T4] = 5000.0

    return fb.build()


def test_h1_bearish_divergence_fires(fixture):
    bars, _buckets = fixture
    events = h1.detect(bars)
    row = events.filter(events["bar_index"] == T1)
    assert row.height == 1
    r = row.row(0, named=True)
    assert r["direction"] == -1
    assert r["magnitude"] > 5.0  # clears the margin by a wide amount; exact
    # sigma value isn't hand-reproduced here, only the qualitative gate.


def test_h2_bullish_absorption_fires_with_exact_magnitude(fixture):
    bars, buckets = fixture
    events = h2.detect(bars, buckets, delta=25.0)
    row = events.filter(events["bar_index"] == T2)
    assert row.height == 1
    r = row.row(0, named=True)
    assert r["direction"] == 1
    # bucket_volume(200) / med96 ; med96 measured at 20.0 in calibration
    assert r["magnitude"] == pytest.approx(10.0, rel=0.05)


def test_h3_up_run_fires_with_exact_magnitude(fixture):
    bars, buckets = fixture
    events = h3.detect(bars, buckets, delta=25.0)
    row = events.filter(events["bar_index"] == T3)
    assert row.height == 1
    r = row.row(0, named=True)
    assert r["direction"] == 1
    # stack_length(3) * mean(ratio) where ratios = 200/50, 300/60, 400/70
    expected = 3 * np.mean([200 / 50, 300 / 60, 400 / 70])
    assert r["magnitude"] == pytest.approx(expected, rel=1e-6)


def test_h6_bearish_exhaustion_fires(fixture):
    bars, buckets = fixture
    events = h6.detect(bars, buckets)
    row = events.filter(events["bar_index"] == T4)
    assert row.height == 1
    r = row.row(0, named=True)
    assert r["direction"] == -1
    assert r["magnitude"] > 0


def test_h3_run_does_not_extend_past_blocked_level(fixture):
    """k=4 (level index 4) must NOT join the run: its sell floor (buy_above at
    level 5, which doesn't exist -> 0) fails, and separately level 3's own
    sell_vol was set to 0 so the up-run at k=4 (which needs sell_below =
    vol(level 3, sell)) is blocked. Confirms magnitude reflects length=3, not 4."""
    bars, buckets = fixture
    events = h3.detect(bars, buckets, delta=25.0)
    row = events.filter(events["bar_index"] == T3)
    r = row.row(0, named=True)
    # length=4 would give a different (larger) magnitude than length=3 with
    # these ratios; assert it matches the length-3 formula, not length-4.
    length_3 = 3 * np.mean([200 / 50, 300 / 60, 400 / 70])
    assert r["magnitude"] == pytest.approx(length_3, rel=1e-6)
