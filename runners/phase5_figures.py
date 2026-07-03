"""Phase 5: README figures. Report-only visualization - no figure here
feeds any gate, threshold, or decision; preregistration defines none.

Reads reports/event_study_btc_cells.csv and reports/sensitivity_grid_cells.csv
for figs 1-3. No per-event file is persisted anywhere in this repo (only
aggregated cell-level CSVs), so fig 4's event markers are re-derived here
directly from data/parquet/BTCUSDT/{bars,buckets}.parquet via the identical
detection + hygiene + quarantine pipeline runners/phase3_event_study.py
uses - not a different or looser one.

Hard constraint (fig 4): no OOS bar is ever read. The bar store is sliced
to IS and cut 48 bars before IS_END immediately after loading, before any
other processing touches it, and the cut is asserted, not just intended.

Writes PNGs to reports/figures/ - runner-generated and immutable like the
rest of reports/, do not hand-edit.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow import events, figures, quarantine  # noqa: E402
from orderflow.config import (  # noqa: E402
    BAR_MS,
    DELTA,
    FDR_Q,
    IS_END_MS,
    MATERIALITY_BP,
    ROUND_TRIP_BP,
    WARM_UP_BARS,
)
from orderflow.signals import h1, h2, h3, h6  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PARQUET_DIR = ROOT / "data" / "parquet"
REPORTS_DIR = ROOT / "reports"
FIGURES_DIR = REPORTS_DIR / "figures"
SYMBOL = "BTCUSDT"
SIGNALS = ["H1", "H2", "H3", "H6"]
FIG4_WINDOW_MS = 7 * 86_400_000
FIG4_CUTOFF_MS = IS_END_MS - 48 * BAR_MS  # hard constraint: nothing at or after this is ever read


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _is_only_events_for_fig4() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Re-derive the IS event set for fig 4 only, from the raw bar/bucket
    store - same detectors, same warm-up + dedup + quarantine hygiene as
    runners/phase3_event_study.py. Returns (bars, events), both already cut
    at FIG4_CUTOFF_MS; no row at or after that timestamp is ever produced
    by this function.
    """
    bars = pl.read_parquet(PARQUET_DIR / SYMBOL / "bars.parquet")
    buckets = pl.read_parquet(PARQUET_DIR / SYMBOL / "buckets.parquet")

    bars = bars.filter(pl.col("bar_ts").dt.epoch(time_unit="ms") < FIG4_CUTOFF_MS)
    max_ts_ms = bars["bar_ts"].dt.epoch(time_unit="ms").max()
    assert max_ts_ms is None or max_ts_ms < FIG4_CUTOFF_MS, "fig4 bar cut failed - an OOS-adjacent bar leaked through"
    buckets = buckets.filter(pl.col("bar_index") <= bars["bar_index"].max())

    qwindows = quarantine.load_quarantine_windows()
    parts = {
        "H1": h1.detect(bars),
        "H2": h2.detect(bars, buckets, delta=DELTA[SYMBOL]),
        "H3": h3.detect(bars, buckets, delta=DELTA[SYMBOL]),
        "H6": h6.detect(bars, buckets),
    }
    nonempty = [df for df in parts.values() if df.height > 0]
    combined = pl.concat(nonempty) if nonempty else next(iter(parts.values()))
    combined = quarantine.filter_quarantined_events(combined, SYMBOL, BAR_MS, qwindows)
    combined = events.hygiene(combined, WARM_UP_BARS)
    return bars, combined


def run() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    log("Reading event_study_btc_cells.csv and sensitivity_grid_cells.csv...")
    cells_df = pl.read_csv(REPORTS_DIR / "event_study_btc_cells.csv")
    sensitivity_df = pl.read_csv(REPORTS_DIR / "sensitivity_grid_cells.csv")

    log("Fig 1: 20-cell forest plot...")
    figures.make_fig1_forest(cells_df, MATERIALITY_BP, ROUND_TRIP_BP, FIGURES_DIR / "fig1_forest_20cells.png")

    log("Fig 2: BH step plot...")
    figures.make_fig2_bh_step(cells_df, FDR_Q, FIGURES_DIR / "fig2_bh_step.png")

    log("Fig 3: sensitivity heatmap...")
    figures.make_fig3_sensitivity_heatmap(cells_df, sensitivity_df, FIGURES_DIR / "fig3_sensitivity_heatmap.png")

    log("Fig 4: re-deriving IS-only events from the bar/bucket store (no OOS bar ever read)...")
    bars, is_events = _is_only_events_for_fig4()
    log(f"  {bars.height:,} IS bars (cut at {FIG4_CUTOFF_MS}), {is_events.height:,} events across {SIGNALS}")
    window_start_ms, window_end_ms = figures.select_fig4_window(is_events, FIG4_WINDOW_MS)
    log(f"  selected window: [{window_start_ms}, {window_end_ms})")
    figures.make_fig4_signal_examples(bars, is_events, window_start_ms, window_end_ms, FIGURES_DIR / "fig4_signal_examples.png")

    for name in ["fig1_forest_20cells.png", "fig2_bh_step.png", "fig3_sensitivity_heatmap.png", "fig4_signal_examples.png"]:
        size = (FIGURES_DIR / name).stat().st_size
        log(f"  wrote {FIGURES_DIR / name} ({size:,} bytes)")
    log("Phase 5 figures complete.")


if __name__ == "__main__":
    run()
