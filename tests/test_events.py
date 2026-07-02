import datetime as dt

import polars as pl

from orderflow import events

UTC = dt.timezone.utc


def _events(rows):
    if not rows:
        return pl.DataFrame(
            schema={"bar_index": pl.Int64, "bar_ts": pl.Datetime, "signal": pl.Utf8, "direction": pl.Int8, "magnitude": pl.Float64}
        )
    return pl.DataFrame(rows, schema=["bar_index", "bar_ts", "signal", "direction", "magnitude"], orient="row").with_columns(
        pl.col("direction").cast(pl.Int8)
    )


def _ts(i):
    return dt.datetime(2024, 1, 1, tzinfo=UTC) + dt.timedelta(minutes=5 * i)


def test_warmup_filters_early_bars():
    rows = [(100, _ts(100), "H1", 1, 1.0), (8640, _ts(8640), "H1", 1, 1.0), (8639, _ts(8639), "H1", 1, 1.0)]
    out = events.apply_warmup(_events(rows), warm_up_bars=8640)
    assert out["bar_index"].to_list() == [8640]


def test_dedup_keeps_first_within_gap_same_signal_direction():
    rows = [
        (100, _ts(100), "H1", 1, 1.0),
        (103, _ts(103), "H1", 1, 2.0),  # within 6 bars of 100 -> suppressed
        (107, _ts(107), "H1", 1, 3.0),  # 107-100=7 > 6 -> kept
    ]
    out = events.dedup(_events(rows), gap_bars=6)
    assert out["bar_index"].to_list() == [100, 107]


def test_dedup_does_not_suppress_across_different_signals_or_directions():
    rows = [
        (100, _ts(100), "H1", 1, 1.0),
        (101, _ts(101), "H2", 1, 1.0),  # different signal -> not suppressed
        (102, _ts(102), "H1", -1, 1.0),  # different direction -> not suppressed
    ]
    out = events.dedup(_events(rows), gap_bars=6)
    assert sorted(out["bar_index"].to_list()) == [100, 101, 102]


def test_dedup_boundary_exactly_gap_bars_apart_is_suppressed():
    rows = [(100, _ts(100), "H1", 1, 1.0), (106, _ts(106), "H1", 1, 2.0)]  # exactly 6 apart
    out = events.dedup(_events(rows), gap_bars=6)
    assert out["bar_index"].to_list() == [100]


def test_hygiene_empty_input():
    out = events.hygiene(_events([]))
    assert out.height == 0
