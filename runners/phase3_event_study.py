"""Phase 3: event study on BTCUSDT in-sample data.

Detects all four testable signals (both directions), applies event hygiene
(warm-up + dedup), computes forward returns with section-5 segment purging,
runs the 20-cell (4 signals x 5 horizons) BTC in-sample event study with
BH-FDR at q=0.10, and applies the section 6.5 promotion gates. Writes
reports/event_study_btc.md + CSVs (runner-generated, immutable).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow import events, eventstudy, stats  # noqa: E402
from orderflow.config import DELTA, FDR_Q, HORIZONS_BARS, MATERIALITY_BP, ROUND_TRIP_BP  # noqa: E402
from orderflow.signals import h1, h2, h3, h6  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PARQUET_DIR = ROOT / "data" / "parquet"
REPORTS_DIR = ROOT / "reports"

SYMBOL = "BTCUSDT"
SIGNALS = ["H1", "H2", "H3", "H6"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def detect_all(bars: pl.DataFrame, buckets: pl.DataFrame, delta: float) -> pl.DataFrame:
    parts = [
        h1.detect(bars),
        h2.detect(bars, buckets, delta=delta),
        h3.detect(bars, buckets, delta=delta),
        h6.detect(bars, buckets),
    ]
    parts = [p for p in parts if p.height > 0]
    combined = pl.concat(parts) if parts else parts[0]
    return events.hygiene(combined)


def run() -> None:
    log(f"Loading {SYMBOL} bars/buckets...")
    bars = pl.read_parquet(PARQUET_DIR / SYMBOL / "bars.parquet")
    buckets = pl.read_parquet(PARQUET_DIR / SYMBOL / "buckets.parquet")
    log(f"  {bars.height:,} bars, {buckets.height:,} buckets")

    log("Detecting events (H1, H2, H3, H6)...")
    all_events = detect_all(bars, buckets, DELTA[SYMBOL])
    log(f"  {all_events.height:,} events after warm-up + dedup")
    for sig in SIGNALS:
        n = all_events.filter(pl.col("signal") == sig).height
        log(f"    {sig}: {n:,}")

    log("Computing forward returns + segment purging...")
    all_events = eventstudy.add_forward_returns(all_events, bars, horizons=HORIZONS_BARS)

    is_events = all_events.filter((pl.col("segment") == "IS") & pl.col("purge_ok"))
    log(f"  {is_events.height:,} BTC in-sample events survive purging")

    # 20-cell family: 4 signals x 5 horizons, BTC IS only
    cell_records = []
    cell_lookup: dict[tuple[str, int], dict] = {}
    p_values = []
    cell_keys = []
    for sig in SIGNALS:
        sig_events = is_events.filter(pl.col("signal") == sig)
        for h in HORIZONS_BARS:
            stats_dict = eventstudy.cell_stats(sig_events, h, n_reps=10_000, seed=hash((sig, h)) % (2**31))
            cell_lookup[(sig, h)] = stats_dict
            p_values.append(stats_dict.get("p_value", float("nan")))
            cell_keys.append((sig, h))
            log(f"  {sig} h={h}: n={stats_dict['n_events']}, mean={stats_dict.get('observed_mean', float('nan')):.6f}, p={stats_dict.get('p_value', float('nan')):.4f}")

    bh_sig = stats.bh_fdr(p_values, q=FDR_Q)
    for (sig, h), significant in zip(cell_keys, bh_sig):
        cell_lookup[(sig, h)]["bh_significant"] = significant

    for (sig, h), c in cell_lookup.items():
        cell_records.append(
            {
                "signal": sig,
                "horizon_bars": h,
                "n_events": c["n_events"],
                "observed_mean_logret": c.get("observed_mean"),
                "observed_mean_bp": c.get("observed_mean", float("nan")) * 10_000,
                "p_value": c.get("p_value"),
                "bh_significant_q10": c.get("bh_significant", False),
                "ci95_lo_bp": c.get("ci95_lo", float("nan")) * 10_000 if c.get("ci95_lo") is not None else None,
                "ci95_hi_bp": c.get("ci95_hi", float("nan")) * 10_000 if c.get("ci95_hi") is not None else None,
                "spearman_ic": c.get("spearman_ic"),
                "ic_ci95_lo": c.get("ic_ci95_lo"),
                "ic_ci95_hi": c.get("ic_ci95_hi"),
            }
        )
    cells_df = pl.DataFrame(cell_records).sort(["signal", "horizon_bars"])
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cells_df.write_csv(REPORTS_DIR / "event_study_btc_cells.csv")
    log(f"Wrote {REPORTS_DIR / 'event_study_btc_cells.csv'}")

    # promotion gates per signal
    gate_records = []
    promoted_signals = {}
    for sig in SIGNALS:
        signal_cells = {h: cell_lookup[(sig, h)] for h in HORIZONS_BARS}
        is_events_by_horizon_ok = {h: is_events.filter(pl.col("signal") == sig) for h in HORIZONS_BARS}
        decision = eventstudy.promotion_decision(signal_cells, is_events_by_horizon_ok)
        gate_records.append(
            {
                "signal": sig,
                "gate1_min_events": decision["gate1_min_events"],
                "gate2_fdr": decision["gate2_fdr"],
                "gate3_materiality": decision["gate3_materiality"],
                "gate4_year_consistency": decision["gate4_year_consistency"],
                "eligible_horizons": str(decision["eligible_horizons"]),
                "h_star": decision["h_star"],
                "promoted": decision["promoted"],
            }
        )
        if decision["promoted"]:
            promoted_signals[sig] = decision
        log(f"  {sig}: promoted={decision['promoted']} (gates: {decision['gate1_min_events']},{decision['gate2_fdr']},{decision['gate3_materiality']},{decision['gate4_year_consistency']}, h*={decision['h_star']})")

    gates_df = pl.DataFrame(gate_records)
    gates_df.write_csv(REPORTS_DIR / "event_study_btc_gates.csv")
    log(f"Wrote {REPORTS_DIR / 'event_study_btc_gates.csv'}")

    write_markdown_report(cells_df, gates_df, promoted_signals, is_events)
    log("Phase 3 event study complete.")


def write_markdown_report(cells_df: pl.DataFrame, gates_df: pl.DataFrame, promoted_signals: dict, is_events: pl.DataFrame) -> None:
    lines = []
    lines.append("# Event Study - BTCUSDT In-Sample")
    lines.append("")
    lines.append("Runner-generated (runners/phase3_event_study.py). Do not hand-edit.")
    lines.append("")
    lines.append(f"20-cell family (4 signals x 5 horizons), BH-FDR q={FDR_Q}. ")
    lines.append(f"Cost model: round trip ~= {ROUND_TRIP_BP}bp; materiality gate requires mean gross return >= {MATERIALITY_BP}bp.")
    lines.append("")
    lines.append("## Cells")
    lines.append("")
    lines.append("| Signal | Horizon (bars) | N | Mean (bp) | p-value | BH-sig q=0.10 | 95% CI (bp) | Spearman IC |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in cells_df.iter_rows(named=True):
        ci = f"[{row['ci95_lo_bp']:.2f}, {row['ci95_hi_bp']:.2f}]" if row["ci95_lo_bp"] is not None else "n/a"
        ic = f"{row['spearman_ic']:.3f}" if row["spearman_ic"] is not None else "n/a"
        lines.append(
            f"| {row['signal']} | {row['horizon_bars']} | {row['n_events']} | {row['observed_mean_bp']:.3f} | "
            f"{row['p_value']:.4f} | {row['bh_significant_q10']} | {ci} | {ic} |"
        )
    lines.append("")
    lines.append("## Promotion gates")
    lines.append("")
    lines.append("| Signal | Gate1 (>=300) | Gate2 (FDR) | Gate3 (materiality) | Gate4 (year-consistency) | h* | Promoted |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in gates_df.iter_rows(named=True):
        lines.append(
            f"| {row['signal']} | {row['gate1_min_events']} | {row['gate2_fdr']} | {row['gate3_materiality']} | "
            f"{row['gate4_year_consistency']} | {row['h_star']} | {row['promoted']} |"
        )
    lines.append("")
    if promoted_signals:
        lines.append(f"## Promoted signals: {', '.join(promoted_signals.keys())}")
        lines.append("")
        lines.append("Proceeding to Phase 4 confirmatory backtest for these signals only.")
    else:
        lines.append("## No signals promoted")
        lines.append("")
        lines.append(
            "No signal cleared all four promotion gates on BTC in-sample data. Per the falsification "
            "protocol, this is a fully valid and reported outcome - see the per-cell table above for "
            "which gate(s) each signal failed (informational null vs. economic null, per "
            "preregistration section 2)."
        )
    lines.append("")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "event_study_btc.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    run()
