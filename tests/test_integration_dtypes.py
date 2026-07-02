"""Regression test for a real-data-only bug: detector output's bar_ts came
back as an opaque polars Object dtype (not Datetime), which every unit test
missed because none of them chained detector output into a real datetime
operation - test_signals/test_truncation_invariance only ever compared on
bar_index, and test_eventstudy/test_quarantine built their event fixtures by
hand rather than running them through h1-h6.detect(). This test exercises
the actual integration path: detect -> hygiene -> add_forward_returns ->
quarantine, which is exactly where the Object dtype broke (polars raised
"cannot cast 'Object' type" inside quarantine's .dt.epoch() call).
"""
import datetime as dt

import polars as pl

from orderflow import events, eventstudy, quarantine
from orderflow.signals import h1, h2, h3, h6

from fixtures import FixtureBuilder

N_BARS = 9100
T1, T2, T3, T4 = 8700, 8750, 8800, 8900


def _fixture():
    fb = FixtureBuilder(N_BARS, seed=42)
    fb.inject_clean_new_high(T1, jump=200.0, anchor_offset=500.0)
    fb.set_delta_run(T1 - 24 - 23, 24, delta_value=100.0, volume_value=100.0)
    fb.set_delta_run(T1 - 23, 24, delta_value=0.0, volume_value=20.0)
    fb.override_buckets(T2, [(50_000.0, 30.0, 170.0), (50_025.0, 20.0, 20.0), (50_050.0, 15.0, 10.0)])
    fb.low[T2], fb.high[T2], fb.close[T2], fb.open[T2] = 50_000.0, 50_100.0, 50_040.0, 50_010.0
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
    fb.low[T3], fb.high[T3], fb.close[T3] = levels_px[0], levels_px[4] + 25.0, levels_px[2]
    fb.inject_clean_new_high(T4, jump=200.0, anchor_offset=500.0)
    import numpy as np

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


def test_detector_output_bar_ts_is_proper_datetime_not_object():
    bars, buckets = _fixture()
    for detector_events in [
        h1.detect(bars),
        h2.detect(bars, buckets, delta=25.0),
        h3.detect(bars, buckets, delta=25.0),
        h6.detect(bars, buckets),
    ]:
        assert detector_events.height > 0
        assert isinstance(detector_events.schema["bar_ts"], pl.Datetime), detector_events.schema["bar_ts"]


def test_full_pipeline_detect_to_quarantine_does_not_raise():
    """The actual integration path used by runners/phase3_event_study.py."""
    bars, buckets = _fixture()
    parts = [h1.detect(bars), h2.detect(bars, buckets, delta=25.0), h3.detect(bars, buckets, delta=25.0), h6.detect(bars, buckets)]
    combined = pl.concat([p for p in parts if p.height > 0])

    qwindows = {"BTCUSDT": [(1, 2)]}  # arbitrary window, not expected to hit any real event
    filtered = quarantine.filter_quarantined_events(combined, "BTCUSDT", 5 * 60_000, qwindows)
    hygiened = events.hygiene(filtered)
    assert hygiened.height > 0
    assert isinstance(hygiened.schema["bar_ts"], pl.Datetime)

    with_returns = eventstudy.add_forward_returns(hygiened, bars, horizons=[1, 6])
    assert with_returns.height == hygiened.height

    nulled = quarantine.null_returns_overlapping_quarantine(with_returns, "BTCUSDT", bars, [1, 6], 5 * 60_000, qwindows)
    assert nulled.height == with_returns.height
