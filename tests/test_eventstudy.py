import datetime as dt

import numpy as np
import polars as pl
import pytest

from orderflow import eventstudy
from orderflow.config import IS_END, OOS_START

UTC = dt.timezone.utc


def _bars_spanning_boundary():
    """5-min bars from 2024-12-30 00:00 to 2025-01-03 00:00, straddling the
    IS/OOS boundary (2024-12-31 23:59:59 / 2025-01-01 00:00)."""
    start = dt.datetime(2024, 12, 30, tzinfo=UTC)
    n = int((dt.datetime(2025, 1, 3, tzinfo=UTC) - start).total_seconds() // 300) + 1
    bar_ts = [start + dt.timedelta(minutes=5 * i) for i in range(n)]
    rng = np.random.default_rng(0)
    close = 50_000 + np.cumsum(rng.normal(0, 1, n))
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    return pl.DataFrame(
        {
            "bar_index": np.arange(n),
            "bar_ts": bar_ts,
            "open": open_,
            "high": open_ + 1,
            "low": open_ - 1,
            "close": close,
            "volume": np.full(n, 10.0),
            "delta": np.zeros(n),
            "cumulative_delta": np.zeros(n),
            "trade_count": np.full(n, 5),
        }
    )


def _event(bar_index, bar_ts, direction=1, magnitude=1.0, signal="H1"):
    return pl.DataFrame(
        [(bar_index, bar_ts, signal, direction, magnitude)],
        schema=["bar_index", "bar_ts", "signal", "direction", "magnitude"],
        orient="row",
    ).with_columns(pl.col("direction").cast(pl.Int8))


def test_segment_of():
    assert eventstudy.segment_of(dt.datetime(2023, 5, 1, tzinfo=UTC)) == "IS"
    assert eventstudy.segment_of(dt.datetime(2025, 6, 1, tzinfo=UTC)) == "OOS"
    assert eventstudy.segment_of(dt.datetime(2022, 1, 1, tzinfo=UTC)) is None  # before study start
    assert eventstudy.segment_of(dt.datetime(2027, 1, 1, tzinfo=UTC)) is None  # after study end


def test_forward_returns_basic_value():
    bars = _bars_spanning_boundary()
    # pick an event comfortably inside IS with full runway
    t = 100
    ev = _event(t, bars["bar_ts"][t])
    out = eventstudy.add_forward_returns(ev, bars, horizons=[1, 3])
    row = out.row(0, named=True)
    entry_open = bars["open"][t + 1]
    target1 = bars["open"][t + 2]
    target3 = bars["open"][t + 4]
    assert row["r_1"] == pytest.approx(1 * np.log(target1 / entry_open))
    assert row["r_3"] == pytest.approx(1 * np.log(target3 / entry_open))


def test_forward_returns_direction_flips_sign():
    bars = _bars_spanning_boundary()
    t = 100
    ev_long = _event(t, bars["bar_ts"][t], direction=1)
    ev_short = _event(t, bars["bar_ts"][t], direction=-1)
    r_long = eventstudy.add_forward_returns(ev_long, bars, horizons=[1]).row(0, named=True)["r_1"]
    r_short = eventstudy.add_forward_returns(ev_short, bars, horizons=[1]).row(0, named=True)["r_1"]
    assert r_long == pytest.approx(-r_short)


def test_forward_returns_null_when_out_of_bounds():
    bars = _bars_spanning_boundary()
    last = bars.height - 1
    ev = _event(last, bars["bar_ts"][last])  # no room for even h=1
    out = eventstudy.add_forward_returns(ev, bars, horizons=[1, 48])
    row = out.row(0, named=True)
    assert row["r_1"] is None
    assert row["r_48"] is None
    assert row["purge_ok"] is False


def test_purge_ok_false_when_48bar_window_crosses_is_oos_boundary():
    bars = _bars_spanning_boundary()
    # find the bar_index whose bar_ts is exactly IS_END's bar (last IS bar)
    is_end_row = bars.filter(pl.col("bar_ts") <= IS_END).tail(1)
    t = is_end_row["bar_index"][0]
    # this event's own bar is IS, but t+1+48 will land in OOS
    ev = _event(t, bars["bar_ts"][t])
    out = eventstudy.add_forward_returns(ev, bars, horizons=[1, 48])
    row = out.row(0, named=True)
    assert row["segment"] == "IS"
    assert row["purge_ok"] is False  # even though r_1 and r_48 are both numerically computable


def test_purge_ok_true_well_inside_is_with_full_runway():
    bars = _bars_spanning_boundary()
    # an early bar, far from the boundary, with room for all horizons
    t = 10
    ev = _event(t, bars["bar_ts"][t])
    out = eventstudy.add_forward_returns(ev, bars, horizons=[1, 48])
    row = out.row(0, named=True)
    assert row["segment"] == "IS"
    assert row["purge_ok"] is True


def test_purge_ok_true_just_inside_oos_with_runway():
    bars = _bars_spanning_boundary()
    oos_start_row = bars.filter(pl.col("bar_ts") >= OOS_START).head(1)
    t = oos_start_row["bar_index"][0]
    ev = _event(t, bars["bar_ts"][t])
    out = eventstudy.add_forward_returns(ev, bars, horizons=[1, 48])
    row = out.row(0, named=True)
    assert row["segment"] == "OOS"
    assert row["purge_ok"] is True  # plenty of OOS bars remain in this fixture


def test_year_consistency_two_of_three_positive():
    rows = []
    for year_dt, sign in [
        (dt.datetime(2022, 8, 1, tzinfo=UTC), 1),
        (dt.datetime(2023, 6, 1, tzinfo=UTC), 1),
        (dt.datetime(2024, 6, 1, tzinfo=UTC), -1),
    ]:
        for i in range(5):
            rows.append((i, year_dt + dt.timedelta(minutes=5 * i), "H1", 1, 1.0))
    events = pl.DataFrame(rows, schema=["bar_index", "bar_ts", "signal", "direction", "magnitude"], orient="row").with_columns(
        pl.col("direction").cast(pl.Int8)
    )
    # attach r_6 manually with the desired sign per segment
    r_values = []
    idx = 0
    for _year_dt, sign in [(1, 1), (2, 1), (3, -1)]:
        for i in range(5):
            r_values.append(sign * 0.01)
            idx += 1
    events = events.with_columns(pl.Series("r_6", r_values))
    result = eventstudy.year_consistency(events, horizon=6)
    assert result["consistent"] is True
    assert result["segment_signs"]["2022H2"] == 1
    assert result["segment_signs"]["2023"] == 1
    assert result["segment_signs"]["2024"] == -1


def _cell_stats_fixture(n=80):
    rng = np.random.default_rng(0)
    rows = []
    for i in range(n):
        bar_ts = dt.datetime(2023, 6, 1, tzinfo=UTC) + dt.timedelta(minutes=5 * i)
        rows.append((i, bar_ts, "H1", 1, float(rng.uniform(0, 5))))
    events = pl.DataFrame(rows, schema=["bar_index", "bar_ts", "signal", "direction", "magnitude"], orient="row").with_columns(
        pl.col("direction").cast(pl.Int8)
    )
    r = rng.normal(0.001, 0.01, n)
    return events.with_columns(pl.Series("r_6", r))


def test_cell_stats_ic_n_reps_defaults_to_n_reps():
    """cell_stats(..., ic_n_reps=None) must behave identically to passing
    ic_n_reps=n_reps explicitly - the decoupling is opt-in, not a behavior
    change for existing call sites that don't pass it."""
    events = _cell_stats_fixture()
    a = eventstudy.cell_stats(events, 6, n_reps=500, seed=42)
    b = eventstudy.cell_stats(events, 6, n_reps=500, ic_n_reps=500, seed=42)
    assert a["spearman_ic"] == b["spearman_ic"]
    assert a["p_value"] == b["p_value"]
    assert a["ci95_lo"] == b["ci95_lo"] and a["ci95_hi"] == b["ci95_hi"]


def test_cell_stats_ic_n_reps_independent_of_n_reps():
    """The precision amendment raises n_reps (mean bootstrap) to 2,000,000
    while intentionally leaving the Spearman IC bootstrap at a much lower
    rep count - must not error and must still return a sane IC."""
    events = _cell_stats_fixture()
    result = eventstudy.cell_stats(events, 6, n_reps=50_000, ic_n_reps=200, seed=42)
    assert result["n_events"] == events.height
    assert -1.0 <= result["spearman_ic"] <= 1.0


def test_promotion_decision_all_gates_pass():
    signal_cells = {
        6: {"n_events": 400, "bh_significant": True, "observed_mean": 0.003, "ci95_lo": 0.001, "ci95_hi": 0.005},
        12: {"n_events": 400, "bh_significant": True, "observed_mean": 0.004, "ci95_lo": 0.002, "ci95_hi": 0.006},
        1: {"n_events": 400, "bh_significant": False, "observed_mean": 0.0001, "ci95_lo": -0.001, "ci95_hi": 0.0012},
    }
    # 0.003 log-return ~= 30bp > 18bp materiality threshold
    is_events = pl.DataFrame(
        [(i, dt.datetime(2023, 6, 1, tzinfo=UTC) + dt.timedelta(minutes=5 * i), "H1", 1, 1.0, 0.01) for i in range(300)]
        + [(i, dt.datetime(2024, 6, 1, tzinfo=UTC) + dt.timedelta(minutes=5 * i), "H1", 1, 1.0, 0.01) for i in range(300)],
        schema=["bar_index", "bar_ts", "signal", "direction", "magnitude", "r_6"],
        orient="row",
    ).with_columns(pl.col("direction").cast(pl.Int8))
    is_events = is_events.with_columns(pl.col("r_6").alias("r_12"))
    result = eventstudy.promotion_decision(signal_cells, {6: is_events, 12: is_events})
    assert result["gate1_min_events"] is True
    assert result["gate2_fdr"] is True
    assert result["gate3_materiality"] is True
    assert result["h_star"] in (6, 12)
    assert result["promoted"] is True


def test_promotion_decision_fails_min_events():
    signal_cells = {6: {"n_events": 50, "bh_significant": True, "observed_mean": 0.01, "ci95_lo": 0.005, "ci95_hi": 0.015}}
    result = eventstudy.promotion_decision(signal_cells, {})
    assert result["gate1_min_events"] is False
    assert result["promoted"] is False


def test_promotion_decision_fails_materiality_when_return_too_small():
    signal_cells = {
        6: {"n_events": 400, "bh_significant": True, "observed_mean": 0.0001, "ci95_lo": 0.00005, "ci95_hi": 0.00015},
        12: {"n_events": 400, "bh_significant": True, "observed_mean": 0.0001, "ci95_lo": 0.00005, "ci95_hi": 0.00015},
    }
    result = eventstudy.promotion_decision(signal_cells, {})
    assert result["gate3_materiality"] is False
    assert result["h_star"] is None
    assert result["promoted"] is False
