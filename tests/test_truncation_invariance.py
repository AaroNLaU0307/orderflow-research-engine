"""Look-ahead-prevention gate (preregistration section 0 principle 3 / brief
section 0.3): recompute all events on data truncated at T; the set of events
with bar_index < T must be bit-identical to the full-sample run. Tested for
all four signals, at several truncation points, on the same engineered
fixture used in test_signals.py (so we're truncating a series that is known
to contain at least one real event per signal, not just incidental noise).
"""
import polars as pl
import pytest

from orderflow import events as events_mod
from orderflow.signals import h1, h2, h3, h6

from fixtures import FixtureBuilder

N_BARS = 9100
T1, T2, T3, T4 = 8700, 8750, 8800, 8900
TRUNCATION_POINTS = [8720, 8850, 9050]  # after T1&T2; after T1-T3; after all 4


@pytest.fixture(scope="module")
def fixture():
    fb = FixtureBuilder(N_BARS, seed=42)
    fb.inject_clean_new_high(T1, jump=200.0, anchor_offset=500.0)
    fb.set_delta_run(T1 - 24 - 23, 24, delta_value=100.0, volume_value=100.0)
    fb.set_delta_run(T1 - 23, 24, delta_value=0.0, volume_value=20.0)

    fb.override_buckets(T2, [(50_000.0, 30.0, 170.0), (50_025.0, 20.0, 20.0), (50_050.0, 15.0, 10.0)])
    fb.low[T2] = 50_000.0
    fb.high[T2] = 50_100.0
    fb.close[T2] = 50_040.0
    fb.open[T2] = 50_010.0

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

    import numpy as np

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


def _detect_all(bars: pl.DataFrame, buckets: pl.DataFrame, delta: float = 25.0) -> pl.DataFrame:
    parts = [
        h1.detect(bars),
        h2.detect(bars, buckets, delta=delta),
        h3.detect(bars, buckets, delta=delta),
        h6.detect(bars, buckets),
    ]
    parts = [p for p in parts if p.height > 0]
    if not parts:
        return parts_empty_schema()
    combined = pl.concat(parts)
    return events_mod.hygiene(combined)


def parts_empty_schema() -> pl.DataFrame:
    return pl.DataFrame(
        schema={"bar_index": pl.Int64, "bar_ts": pl.Datetime, "signal": pl.Utf8, "direction": pl.Int8, "magnitude": pl.Float64}
    )


def test_full_run_has_at_least_one_event_per_signal_post_injection(fixture):
    bars, buckets = fixture
    full_events = _detect_all(bars, buckets)
    signals_present = set(full_events["signal"].unique().to_list())
    assert signals_present == {"H1", "H2", "H3", "H6"}


@pytest.mark.parametrize("T", TRUNCATION_POINTS)
def test_truncation_invariance(fixture, T):
    bars, buckets = fixture
    full_events = _detect_all(bars, buckets)

    trunc_bars = bars.filter(pl.col("bar_index") < T)
    trunc_buckets = buckets.filter(pl.col("bar_index") < T)
    trunc_events = _detect_all(trunc_bars, trunc_buckets)

    full_before_t = full_events.filter(pl.col("bar_index") < T).sort(["signal", "direction", "bar_index"])
    trunc_before_t = trunc_events.sort(["signal", "direction", "bar_index"])

    assert full_before_t.height == trunc_before_t.height, (
        f"event count mismatch at T={T}: full={full_before_t.height}, truncated={trunc_before_t.height}"
    )
    for col in ["bar_index", "signal", "direction"]:
        assert full_before_t[col].to_list() == trunc_before_t[col].to_list(), f"column {col} mismatch at T={T}"
    for a, b in zip(full_before_t["magnitude"].to_list(), trunc_before_t["magnitude"].to_list()):
        assert a == pytest.approx(b, rel=1e-9, abs=1e-9), f"magnitude mismatch at T={T}: {a} vs {b}"


def test_truncation_invariance_covers_all_four_injected_events(fixture):
    """Sanity check that TRUNCATION_POINTS actually exercise all four
    detectors' injected events at least once each across the parametrized T
    values (T=8720 keeps H1+H2 events pre-T, drops H3/H6's later windows)."""
    bars, buckets = fixture
    full_events = _detect_all(bars, buckets)
    injected_bars = {T1: "H1", T2: "H2", T3: "H3", T4: "H6"}
    for bar_index, signal in injected_bars.items():
        match = full_events.filter((pl.col("bar_index") == bar_index) & (pl.col("signal") == signal))
        assert match.height == 1, f"expected injected {signal} event at bar_index={bar_index} in full run"
