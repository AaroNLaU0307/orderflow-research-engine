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

from orderflow import events, eventstudy, quarantine, stats  # noqa: E402
from orderflow.config import BAR_MS, DELTA, FDR_Q, HORIZONS_BARS, MATERIALITY_BP, ROUND_TRIP_BP  # noqa: E402
from orderflow.signals import h1, h2, h3, h6  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PARQUET_DIR = ROOT / "data" / "parquet"
REPORTS_DIR = ROOT / "reports"

SYMBOL = "BTCUSDT"
SIGNALS = ["H1", "H2", "H3", "H6"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def detect_all_stages(bars: pl.DataFrame, buckets: pl.DataFrame, delta: float, symbol: str, qwindows: dict) -> dict:
    """Returns the event-accounting funnel: raw -> after quarantine filter
    -> after warm-up -> after dedup, plus the per-signal raw breakdown."""
    parts = {
        "H1": h1.detect(bars),
        "H2": h2.detect(bars, buckets, delta=delta),
        "H3": h3.detect(bars, buckets, delta=delta),
        "H6": h6.detect(bars, buckets),
    }
    raw_counts = {sig: df.height for sig, df in parts.items()}
    nonempty = [df for df in parts.values() if df.height > 0]
    combined = pl.concat(nonempty) if nonempty else next(iter(parts.values()))

    # quarantine filtering must happen BEFORE dedup: a quarantined event
    # could otherwise have already suppressed a legitimate nearby event via
    # the 6-bar dedup window, which filtering after dedup could not undo.
    after_quarantine = quarantine.filter_quarantined_events(combined, symbol, BAR_MS, qwindows)
    after_warmup = events.apply_warmup(after_quarantine)
    after_dedup = events.dedup(after_warmup)

    return {
        "raw_counts": raw_counts,
        "raw_total": combined.height,
        "after_quarantine": after_quarantine.height,
        "after_warmup": after_warmup.height,
        "after_dedup": after_dedup.height,
        "after_dedup_by_signal": {sig: after_dedup.filter(pl.col("signal") == sig).height for sig in SIGNALS},
        "events": after_dedup,
    }


def run() -> None:
    log(f"Loading {SYMBOL} bars/buckets...")
    bars = pl.read_parquet(PARQUET_DIR / SYMBOL / "bars.parquet")
    buckets = pl.read_parquet(PARQUET_DIR / SYMBOL / "buckets.parquet")
    log(f"  {bars.height:,} bars, {buckets.height:,} buckets")

    qwindows = quarantine.load_quarantine_windows()
    if SYMBOL in qwindows:
        log(f"  {len(qwindows[SYMBOL])} quarantine window(s) loaded for {SYMBOL}: {qwindows[SYMBOL]}")

    log("Detecting events (H1, H2, H3, H6)...")
    funnel = detect_all_stages(bars, buckets, DELTA[SYMBOL], SYMBOL, qwindows)
    all_events = funnel["events"]
    log(
        f"  raw={funnel['raw_total']:,} -> after_quarantine={funnel['after_quarantine']:,} "
        f"-> after_warmup={funnel['after_warmup']:,} -> after_dedup={funnel['after_dedup']:,}"
    )
    for sig in SIGNALS:
        raw = funnel["raw_counts"][sig]
        final = funnel["after_dedup_by_signal"][sig]
        bull = all_events.filter((pl.col("signal") == sig) & (pl.col("direction") == 1)).height
        bear = all_events.filter((pl.col("signal") == sig) & (pl.col("direction") == -1)).height
        log(f"    {sig}: raw={raw:,} -> final={final:,} (bull={bull:,}, bear={bear:,})")

    log("Computing forward returns + segment purging...")
    all_events = eventstudy.add_forward_returns(all_events, bars, horizons=HORIZONS_BARS)
    all_events = quarantine.null_returns_overlapping_quarantine(all_events, SYMBOL, bars, HORIZONS_BARS, BAR_MS, qwindows)

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
        mean = c.get("observed_mean")
        ci_lo, ci_hi = c.get("ci95_lo"), c.get("ci95_hi")
        se_bp = (ci_hi - ci_lo) / (2 * 1.96) * 10_000 if ci_lo is not None and ci_hi is not None else None
        t_stat = (mean * 10_000) / se_bp if se_bp else None
        cell_records.append(
            {
                "signal": sig,
                "horizon_bars": h,
                "n_events": c["n_events"],
                "observed_mean_logret": mean,
                "observed_mean_bp": mean * 10_000 if mean is not None else float("nan"),
                "bootstrap_se_bp": se_bp,
                "t_stat": t_stat,
                "p_value": c.get("p_value"),
                "bh_significant_q10": c.get("bh_significant", False),
                "ci95_lo_bp": ci_lo * 10_000 if ci_lo is not None else None,
                "ci95_hi_bp": ci_hi * 10_000 if ci_hi is not None else None,
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
        yc = decision.get("year_consistency_detail") or {}
        gate_records.append(
            {
                "signal": sig,
                "gate1_min_events": decision["gate1_min_events"],
                "gate2_fdr": decision["gate2_fdr"],
                "gate3_materiality": decision["gate3_materiality"],
                "gate3_eligible_horizons": str(decision["eligible_horizons"]),
                "gate4_year_consistency": decision["gate4_year_consistency"],
                "gate4_segment_signs": str(yc.get("segment_signs")),
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

    write_markdown_report(cells_df, gates_df, promoted_signals, is_events, funnel)
    log("Phase 3 event study complete.")


def write_markdown_report(
    cells_df: pl.DataFrame, gates_df: pl.DataFrame, promoted_signals: dict, is_events: pl.DataFrame, funnel: dict
) -> None:
    lines = []
    lines.append("# Event Study - BTCUSDT In-Sample")
    lines.append("")
    lines.append("Runner-generated (runners/phase3_event_study.py). Do not hand-edit.")
    lines.append("")
    lines.append(f"20-cell family (4 signals x 5 horizons), BH-FDR q={FDR_Q}. ")
    lines.append(f"Cost model: round trip ~= {ROUND_TRIP_BP}bp; materiality gate requires mean gross return >= {MATERIALITY_BP}bp.")
    lines.append("")
    lines.append("## Event accounting")
    lines.append("")
    lines.append(
        f"- Raw detected: {funnel['raw_total']:,} -> after quarantine filter: {funnel['after_quarantine']:,} "
        f"-> after warm-up (bar_index>=8640): {funnel['after_warmup']:,} -> after dedup (6-bar, keep-first): {funnel['after_dedup']:,}"
    )
    lines.append("")
    lines.append("| Signal | Raw | Final (post warm-up+dedup) | Bull | Bear |")
    lines.append("|---|---|---|---|---|")
    for sig in SIGNALS:
        raw = funnel["raw_counts"][sig]
        final = funnel["after_dedup_by_signal"][sig]
        bull = funnel["events"].filter((pl.col("signal") == sig) & (pl.col("direction") == 1)).height
        bear = funnel["events"].filter((pl.col("signal") == sig) & (pl.col("direction") == -1)).height
        lines.append(f"| {sig} | {raw:,} | {final:,} | {bull:,} | {bear:,} |")
    lines.append("")
    lines.append(f"- BTC in-sample events surviving segment-purge admission (used in the 20-cell statistics below): {is_events.height:,}")
    lines.append("")
    lines.append("## Cells")
    lines.append("")
    lines.append("| Signal | Horizon (bars) | N | Mean (bp) | Bootstrap SE (bp) | t | raw p | BH-FDR q=0.10 sig | 95% CI (bp) | Spearman IC |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for row in cells_df.iter_rows(named=True):
        ci = f"[{row['ci95_lo_bp']:.2f}, {row['ci95_hi_bp']:.2f}]" if row["ci95_lo_bp"] is not None else "n/a"
        ic = f"{row['spearman_ic']:.3f}" if row["spearman_ic"] is not None else "n/a"
        se = f"{row['bootstrap_se_bp']:.3f}" if row["bootstrap_se_bp"] is not None else "n/a"
        t = f"{row['t_stat']:.3f}" if row["t_stat"] is not None else "n/a"
        lines.append(
            f"| {row['signal']} | {row['horizon_bars']} | {row['n_events']} | {row['observed_mean_bp']:.3f} | {se} | {t} | "
            f"{row['p_value']:.4f} | {row['bh_significant_q10']} | {ci} | {ic} |"
        )
    lines.append("")
    lines.append("## Promotion gates")
    lines.append("")
    lines.append(
        "| Signal | Gate1 (N>=300) | Gate2 (FDR>=2 horizons, >=1 >=30m) | Gate3 E(signal) eligible horizons | "
        "Gate4 h* IS-segment signs (2022H2/2023/2024) | Gate4 pass | h* | Promoted |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for row in gates_df.iter_rows(named=True):
        lines.append(
            f"| {row['signal']} | {row['gate1_min_events']} | {row['gate2_fdr']} | {row['gate3_eligible_horizons']} | "
            f"{row['gate4_segment_signs']} | {row['gate4_year_consistency']} | {row['h_star']} | {row['promoted']} |"
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
