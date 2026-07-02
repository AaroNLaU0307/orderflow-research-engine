"""Phase 3 section-8 sensitivity grid: report-only, one-factor-at-a-time,
BTC in-sample only. NO FDR, NO gates, NO h*, NO promotion vocabulary - see
the mandatory interpretation preamble written into the report.

Window-size constants are rescaled per config to preserve wall-clock
duration relative to the primary 5-minute-bar convention (e.g. 96 bars
[8h] -> 160 three-minute bars / 32 fifteen-minute bars). Threshold RATIOS
(4x median, 70% aggression, 3x imbalance, 95th percentile, 20% zone) are
NOT rescaled - only window sizes measured in bar-counts. Forward-return
horizons are kept as the literal bar-counts {1,3,6,12,48} from
preregistration section 6.1 for every config (not wall-clock-rescaled):
5 minutes does not evenly divide into 3-minute or 15-minute bars, so the
horizon set is defined portably in bar-count terms and its wall-clock
meaning is stated per config below. This is an explicit interpretive
choice, flagged for review.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow import events, eventstudy, stats  # noqa: E402
from orderflow.config import HORIZONS_BARS  # noqa: E402
from orderflow.signals import h1, h2, h3, h6  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "parquet_sensitivity"
REPORTS_DIR = ROOT / "reports"
SIGNALS = ["H1", "H2", "H3", "H6"]

# path -> (delta, bar_minutes, scaled windows). Scale factor = 5/bar_minutes
# relative to the primary 5-minute-bar convention (24, 8640, 96, 2016, 6).
SENSITIVITY_CONFIGS = {
    "delta10_bar5m": {
        "label": "Delta=10 USDT, bar=5m (baseline Delta=25)",
        "delta": 10.0,
        "bar_minutes": 5,
        "h1_cumdelta_window": 24,
        "h1_sigma_window": 8640,
        "h24_high_window": 24,
        "h2_volume_window": 96,
        "h3_volume_window": 96,
        "h6_volume_window": 2016,
        "dedup_gap_bars": 6,
        "warmup_bars": 8640,
    },
    "delta50_bar5m": {
        "label": "Delta=50 USDT, bar=5m (baseline Delta=25)",
        "delta": 50.0,
        "bar_minutes": 5,
        "h1_cumdelta_window": 24,
        "h1_sigma_window": 8640,
        "h24_high_window": 24,
        "h2_volume_window": 96,
        "h3_volume_window": 96,
        "h6_volume_window": 2016,
        "dedup_gap_bars": 6,
        "warmup_bars": 8640,
    },
    "bar3m_delta25": {
        "label": "bar=3m, Delta=25 USDT (baseline bar=5m)",
        "delta": 25.0,
        "bar_minutes": 3,
        "h1_cumdelta_window": 40,
        "h1_sigma_window": 14400,
        "h24_high_window": 40,
        "h2_volume_window": 160,
        "h3_volume_window": 160,
        "h6_volume_window": 3360,
        "dedup_gap_bars": 10,
        "warmup_bars": 14400,
    },
    "bar15m_delta25": {
        "label": "bar=15m, Delta=25 USDT (baseline bar=5m)",
        "delta": 25.0,
        "bar_minutes": 15,
        "h1_cumdelta_window": 8,
        "h1_sigma_window": 2880,
        "h24_high_window": 8,
        "h2_volume_window": 32,
        "h3_volume_window": 32,
        "h6_volume_window": 672,
        "dedup_gap_bars": 2,
        "warmup_bars": 2880,
    },
}


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def detect_all(bars: pl.DataFrame, buckets: pl.DataFrame, cfg: dict) -> pl.DataFrame:
    parts = [
        h1.detect(bars, cumdelta_window=cfg["h1_cumdelta_window"], sigma_window=cfg["h1_sigma_window"], high_window=cfg["h24_high_window"]),
        h2.detect(bars, buckets, delta=cfg["delta"], volume_window=cfg["h2_volume_window"]),
        h3.detect(bars, buckets, delta=cfg["delta"], volume_window=cfg["h3_volume_window"]),
        h6.detect(bars, buckets, volume_window=cfg["h6_volume_window"], high_window=cfg["h24_high_window"]),
    ]
    nonempty = [p for p in parts if p.height > 0]
    combined = pl.concat(nonempty) if nonempty else parts[0]
    after_warmup = events.apply_warmup(combined, warm_up_bars=cfg["warmup_bars"])
    return events.dedup(after_warmup, gap_bars=cfg["dedup_gap_bars"])


def run_one_config(name: str, cfg: dict) -> dict:
    log(f"=== {name}: {cfg['label']} ===")
    store_dir = DATA_DIR / name / "BTCUSDT"
    bars = pl.read_parquet(store_dir / "bars.parquet")
    buckets = pl.read_parquet(store_dir / "buckets.parquet")
    log(f"  {bars.height:,} bars, {buckets.height:,} buckets")

    raw_counts = {
        "H1": h1.detect(bars, cumdelta_window=cfg["h1_cumdelta_window"], sigma_window=cfg["h1_sigma_window"], high_window=cfg["h24_high_window"]).height,
        "H2": h2.detect(bars, buckets, delta=cfg["delta"], volume_window=cfg["h2_volume_window"]).height,
        "H3": h3.detect(bars, buckets, delta=cfg["delta"], volume_window=cfg["h3_volume_window"]).height,
        "H6": h6.detect(bars, buckets, volume_window=cfg["h6_volume_window"], high_window=cfg["h24_high_window"]).height,
    }
    all_events = detect_all(bars, buckets, cfg)
    log(f"  raw events: {raw_counts}, after warmup+dedup: {all_events.height:,}")

    all_events = eventstudy.add_forward_returns(all_events, bars, horizons=HORIZONS_BARS)
    is_events = all_events.filter(pl.col("purge_ok"))
    log(f"  events surviving purge admission: {is_events.height:,}")

    cell_records = []
    for sig in SIGNALS:
        sig_events = is_events.filter(pl.col("signal") == sig)
        for h in HORIZONS_BARS:
            c = eventstudy.cell_stats(sig_events, h, n_reps=10_000, seed=stats.stable_seed(name, sig, h))
            mean = c.get("observed_mean")
            ci_lo, ci_hi = c.get("ci95_lo"), c.get("ci95_hi")
            se_bp = (ci_hi - ci_lo) / (2 * 1.96) * 10_000 if ci_lo is not None and ci_hi is not None else None
            t_stat = (mean * 10_000) / se_bp if se_bp else None
            cell_records.append(
                {
                    "config": name,
                    "signal": sig,
                    "horizon_bars": h,
                    "n_events": c["n_events"],
                    "mean_bp": mean * 10_000 if mean is not None else float("nan"),
                    "se_bp": se_bp,
                    "t_stat": t_stat,
                    "ci95_lo_bp": ci_lo * 10_000 if ci_lo is not None else None,
                    "ci95_hi_bp": ci_hi * 10_000 if ci_hi is not None else None,
                }
            )
            log(f"    {sig} h={h}: n={c['n_events']}, mean={cell_records[-1]['mean_bp']:.3f}bp, t={t_stat if t_stat is not None else float('nan'):.3f}" if t_stat is not None else f"    {sig} h={h}: n={c['n_events']}, insufficient data")

    return {
        "raw_counts": raw_counts,
        "final_count": all_events.height,
        "final_by_signal": {sig: all_events.filter(pl.col("signal") == sig).height for sig in SIGNALS},
        "cells": cell_records,
    }


def run() -> None:
    results = {}
    for name, cfg in SENSITIVITY_CONFIGS.items():
        results[name] = run_one_config(name, cfg)

    all_cells = []
    for name, r in results.items():
        all_cells.extend(r["cells"])
    cells_df = pl.DataFrame(all_cells)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cells_df.write_csv(REPORTS_DIR / "sensitivity_grid_cells.csv")
    log(f"Wrote {REPORTS_DIR / 'sensitivity_grid_cells.csv'}")

    write_report(results)
    log("Sensitivity grid complete.")


def write_report(results: dict) -> None:
    lines = []
    lines.append("# Sensitivity Grid - BTCUSDT In-Sample (report-only)")
    lines.append("")
    lines.append("Runner-generated (runners/phase3_sensitivity_run.py). Do not hand-edit.")
    lines.append("")
    lines.append("## Mandatory interpretation preamble")
    lines.append("")
    lines.append(
        "These are 80 additional, UNCORRECTED cells (4 configs x 4 signals x 5 horizons) whose only "
        "role is robustness-of-the-null: plateau evidence that the primary Phase 3 falsification "
        "(0 of 20 cells BH-FDR significant at q=0.10, BTC in-sample, 5m/Delta=25) is not an artifact "
        "of that specific bar/bucket choice. **No FDR correction, no promotion gates, no h* selection, "
        "and no promotion decision are computed or implied here.** Under the global null, with 80 "
        "independent-ish t-statistics at the |t|>1.96 (~5%) two-sided threshold, roughly 4 cells are "
        "expected to cross that bar by chance alone; an isolated CI-excluding-zero cell in the table "
        "below is hypothesis-generating only and cannot be promoted - acting on one would require a "
        "fresh pre-registered study on unseen data. H3's event count mechanically multiplies at "
        "Delta=10 and bar=3m (finer buckets/bars create more opportunities for its 3-consecutive-level "
        "imbalance condition to fire); that changes statistical power, not the substance of any "
        "conclusion, and is reported as such rather than as a finding."
    )
    lines.append("")
    lines.append("## Scaled window constants per config")
    lines.append("")
    lines.append(
        "Threshold RATIOS (H2 4x median volume, H2 70% aggression, H3 3.0x imbalance ratio, H6 95th "
        "volume percentile, H2 20% zone fraction) are unchanged across all configs. Only window sizes "
        "measured in bar-counts are rescaled, to preserve wall-clock duration relative to the primary "
        "5-minute-bar convention:"
    )
    lines.append("")
    lines.append("| Config | Delta | Bar | H1 cumD window (2h) | H1 sigma window (30d) | H2/H3 vol window (8h) | H6 vol window (1wk) | Dedup gap (30min) | Warm-up |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for name, cfg in SENSITIVITY_CONFIGS.items():
        lines.append(
            f"| {name} | {cfg['delta']} | {cfg['bar_minutes']}m | {cfg['h1_cumdelta_window']} | {cfg['h1_sigma_window']} | "
            f"{cfg['h2_volume_window']} | {cfg['h6_volume_window']} | {cfg['dedup_gap_bars']} | {cfg['warmup_bars']} |"
        )
    lines.append("")
    lines.append(
        "**Horizon interpretation:** forward-return horizons are kept as the literal bar-counts "
        "{1,3,6,12,48} from preregistration section 6.1 for every config (not wall-clock-rescaled - "
        "5 minutes does not evenly divide into 3-minute or 15-minute bars). Wall-clock meaning per "
        "config: delta10/delta50 (bar=5m) = {5m,15m,30m,1h,4h} (unchanged); bar=3m = "
        "{3m,9m,18m,36m,144m}; bar=15m = {15m,45m,1.5h,3h,12h}."
    )
    lines.append("")

    for name, cfg in SENSITIVITY_CONFIGS.items():
        r = results[name]
        lines.append(f"## {name}: {cfg['label']}")
        lines.append("")
        lines.append("| Signal | Raw events | Final (warmup+dedup) |")
        lines.append("|---|---|---|")
        for sig in SIGNALS:
            lines.append(f"| {sig} | {r['raw_counts'][sig]:,} | {r['final_by_signal'][sig]:,} |")
        lines.append("")
        lines.append("| Signal | Horizon (bars) | N | Mean (bp) | SE (bp) | t | 95% CI (bp) |")
        lines.append("|---|---|---|---|---|---|---|")
        for c in r["cells"]:
            se = f"{c['se_bp']:.3f}" if c["se_bp"] is not None else "n/a"
            t = f"{c['t_stat']:.3f}" if c["t_stat"] is not None else "n/a"
            ci = f"[{c['ci95_lo_bp']:.2f}, {c['ci95_hi_bp']:.2f}]" if c["ci95_lo_bp"] is not None else "n/a"
            lines.append(f"| {c['signal']} | {c['horizon_bars']} | {c['n_events']} | {c['mean_bp']:.3f} | {se} | {t} | {ci} |")
        lines.append("")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "sensitivity_grid.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run()
