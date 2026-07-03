import datetime as dt

import polars as pl
import pytest

from orderflow import figures

UTC = dt.timezone.utc
SIGNALS = ["H1", "H2", "H3", "H6"]
HORIZONS = [1, 3, 6, 12, 48]
MIN_PNG_BYTES = 5_000  # a trivial/blank matplotlib PNG is far smaller than this


def _synthetic_cells_df() -> pl.DataFrame:
    rows = []
    p_values = {}
    i = 0
    for sig in SIGNALS:
        for h in HORIZONS:
            i += 1
            p_values[(sig, h)] = 0.02 * i  # distinct, ascending-ish p-values
    ranked = sorted(p_values.items(), key=lambda kv: kv[1])
    rank_of = {k: idx + 1 for idx, (k, _v) in enumerate(ranked)}
    n = len(p_values)
    for sig in SIGNALS:
        for h in HORIZONS:
            p = p_values[(sig, h)]
            rank = rank_of[(sig, h)]
            rows.append(
                {
                    "signal": sig,
                    "horizon_bars": h,
                    "n_events": 500,
                    "observed_mean_bp": (hash((sig, h)) % 21) - 10,
                    "bootstrap_se_bp": 2.0,
                    "t_stat": 1.0,
                    "p_value": p,
                    "bh_significant_q10": False,
                    "ci95_lo_bp": (hash((sig, h)) % 21) - 10 - 3.0,
                    "ci95_hi_bp": (hash((sig, h)) % 21) - 10 + 3.0,
                    "rank_by_p": rank,
                    "operative_bh_threshold": (rank / n) * 0.10,
                }
            )
    return pl.DataFrame(rows)


def _synthetic_sensitivity_df() -> pl.DataFrame:
    rows = []
    for config in ["delta10_bar5m", "delta50_bar5m", "bar3m_delta25", "bar15m_delta25"]:
        for sig in SIGNALS:
            for h in HORIZONS:
                rows.append({"config": config, "signal": sig, "horizon_bars": h, "t_stat": (hash((config, sig, h)) % 400) / 100 - 2.0})
    return pl.DataFrame(rows)


def _synthetic_bars_and_events():
    start = dt.datetime(2023, 3, 1, tzinfo=UTC)
    n = 2000  # ~ a week of 5-min bars
    bar_ts = [start + dt.timedelta(minutes=5 * i) for i in range(n)]
    close = [50_000.0 + (i % 50) for i in range(n)]
    bars = pl.DataFrame({"bar_index": list(range(n)), "bar_ts": bar_ts, "close": close})

    event_rows = []
    for j, sig in enumerate(SIGNALS):
        idx = 100 + j * 50  # all four comfortably within the first 7 days
        event_rows.append({"bar_index": idx, "bar_ts": bar_ts[idx], "signal": sig, "direction": 1 if j % 2 == 0 else -1})
    events_df = pl.DataFrame(event_rows)
    return bars, events_df


@pytest.fixture
def tmp_png(tmp_path):
    return tmp_path / "fig.png"


def test_fig1_forest_generates_nontrivial_png(tmp_png):
    figures.make_fig1_forest(_synthetic_cells_df(), materiality_bp=18.0, round_trip_bp=12.0, out_path=tmp_png)
    assert tmp_png.exists()
    assert tmp_png.stat().st_size > MIN_PNG_BYTES


def test_fig2_bh_step_generates_nontrivial_png(tmp_png):
    figures.make_fig2_bh_step(_synthetic_cells_df(), fdr_q=0.10, out_path=tmp_png)
    assert tmp_png.exists()
    assert tmp_png.stat().st_size > MIN_PNG_BYTES


def test_fig3_sensitivity_heatmap_generates_nontrivial_png(tmp_png):
    figures.make_fig3_sensitivity_heatmap(_synthetic_cells_df(), _synthetic_sensitivity_df(), out_path=tmp_png)
    assert tmp_png.exists()
    assert tmp_png.stat().st_size > MIN_PNG_BYTES


def test_select_fig4_window_finds_earliest_all_signal_window():
    bars, events_df = _synthetic_bars_and_events()
    window_ms = 7 * 86_400_000
    start_ms, end_ms = figures.select_fig4_window(events_df, window_ms)
    assert end_ms - start_ms == window_ms
    # every signal must have >=1 event inside [start_ms, end_ms)
    ts_ms = events_df["bar_ts"].dt.epoch(time_unit="ms")
    for sig in SIGNALS:
        sig_ts = events_df.filter(pl.col("signal") == sig)["bar_ts"].dt.epoch(time_unit="ms")
        assert ((sig_ts >= start_ms) & (sig_ts < end_ms)).any()
    # earliest candidate is the smallest event bar_ts among the "last signal to complete the set"
    assert start_ms == int(ts_ms.min())


def test_select_fig4_window_raises_when_no_window_covers_all_signals():
    bars, events_df = _synthetic_bars_and_events()
    with pytest.raises(ValueError):
        figures.select_fig4_window(events_df, window_ms=1)  # 1ms window can't span 4 distinct bars


def test_fig4_signal_examples_generates_nontrivial_png(tmp_png):
    bars, events_df = _synthetic_bars_and_events()
    window_ms = 7 * 86_400_000
    start_ms, end_ms = figures.select_fig4_window(events_df, window_ms)
    figures.make_fig4_signal_examples(bars, events_df, start_ms, end_ms, out_path=tmp_png)
    assert tmp_png.exists()
    assert tmp_png.stat().st_size > MIN_PNG_BYTES
