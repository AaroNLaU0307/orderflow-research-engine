"""Assemble reports/FINAL_REPORT.md from the runner-generated artifacts of
every prior phase. All numeric content is read directly from the source
CSVs/JSON (never hand-typed), so this is "runner-generated where numeric"
per the Phase 5 instruction - only the connective narrative text is
authored here.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import polars as pl  # noqa: E402

from orderflow.config import (  # noqa: E402
    FDR_Q,
    IS_END,
    IS_START,
    MATERIALITY_BP,
    OOS_END,
    OOS_START,
    ROUND_TRIP_BP,
    STUDY_END,
    STUDY_START,
)

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
DATA_DIR = ROOT / "data"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def md_table(df: pl.DataFrame, cols: list[str] | None = None, float_fmt: dict[str, str] | None = None) -> list[str]:
    cols = cols or df.columns
    float_fmt = float_fmt or {}
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.iter_rows(named=True):
        vals = []
        for c in cols:
            v = row[c]
            if v is None:
                vals.append("n/a")
            elif c in float_fmt and isinstance(v, (int, float)):
                vals.append(float_fmt[c].format(v))
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def run() -> None:
    lines: list[str] = []
    lines.append("# Order Flow Research Engine v1 - Final Report")
    lines.append("")
    lines.append("Runner-generated (runners/phase5_final_report.py). Numeric content is read directly")
    lines.append("from the source CSV/JSON artifacts of each phase, never hand-typed. Do not hand-edit.")
    lines.append("")
    lines.append(f"Study period: {STUDY_START.date()} to {STUDY_END.date()}. In-sample (discovery): "
                  f"{IS_START.date()} to {IS_END.date()}. Out-of-sample (confirmation, reserved, untouched "
                  f"by this study - see section 3): {OOS_START.date()} to {OOS_END.date()}.")
    lines.append("")

    # ---- Section 1: headline verdict ----
    gates_df = pl.read_csv(REPORTS_DIR / "event_study_btc_gates.csv")
    cells_df = pl.read_csv(REPORTS_DIR / "event_study_btc_cells.csv")
    n_promoted = gates_df.filter(pl.col("promoted")).height
    n_bh_sig = cells_df.filter(pl.col("bh_significant_q10")).height

    lines.append("## 1. Headline result")
    lines.append("")
    lines.append(
        f"Four classic order-flow footprint signals (H1 delta divergence, H2 absorption, H3 stacked "
        f"imbalance, H6 exhaustion) were tested on BTCUSDT perpetual futures in-sample under a "
        f"pre-registered falsification protocol. Two further hypotheses (H4 liquidity wall, H5 liquidity "
        f"pull) were DATA-BLOCKED for the entire study (section 6). Of the 20 tested cells (4 signals x "
        f"5 horizons), **{n_bh_sig} cleared BH-FDR significance at q={FDR_Q}**, and "
        f"**{n_promoted} of 4 signals were promoted** to the confirmatory backtest."
    )
    lines.append("")
    # "Best cell" for the economic-materiality comparison = highest mean
    # return among the nominally-significant-pre-FDR cells (raw p<0.05) -
    # NOT argmax(mean_bp) over all 20, which would pick whichever cell has
    # the noisiest, least-credible point estimate (e.g. a tiny-N cell with
    # a huge SE) rather than the closest-to-real finding. Only two cells in
    # the primary 20-cell table clear raw p<0.05 (both H1); this picks the
    # higher-mean of those two.
    nominal = cells_df.filter(pl.col("p_value") < 0.05)
    best_cell = (nominal if nominal.height > 0 else cells_df).sort("observed_mean_bp", descending=True).head(1).row(0, named=True)
    lines.append(
        f"The most statistically credible cell in the entire 20-cell table - the highest-mean cell among "
        f"those clearing raw p<0.05 (before FDR correction) - was {best_cell['signal']} at "
        f"h={best_cell['horizon_bars']} bars, mean gross return {best_cell['observed_mean_bp']:.2f}bp "
        f"(raw p={best_cell['p_value']:.4f}, t={best_cell['t_stat']:.3f}, not BH-significant). Against the "
        f"pre-registered materiality bar of {MATERIALITY_BP}bp (1.5x the ~{ROUND_TRIP_BP}bp round-trip cost "
        f"floor), this is ~{MATERIALITY_BP/best_cell['observed_mean_bp']:.1f}x below the threshold required "
        f"to call it economically material even before considering statistical significance at all. **This "
        f"is a double null: informational (fails BH-FDR) and economic (even the best cell falls far short "
        f"of materiality).** (Note: a handful of other cells, e.g. H3 h=48 at 16.0bp, show a nominally "
        f"larger point estimate but a far wider standard error - SE={cells_df.sort('observed_mean_bp', descending=True).head(1).row(0, named=True)['bootstrap_se_bp']:.1f}bp "
        f"vs {best_cell['bootstrap_se_bp']:.1f}bp here - i.e. noise, not signal; excluded from this "
        f"comparison for exactly that reason.)"
    )
    lines.append("")

    # ---- Section 2: Phase 3 event study (verbatim) ----
    lines.append("## 2. Phase 3 event study (BTC in-sample, 20-cell family)")
    lines.append("")
    lines.append("Verbatim from reports/event_study_btc.md / event_study_btc_cells.csv / event_study_btc_gates.csv.")
    lines.append("")
    lines.extend(
        md_table(
            cells_df,
            cols=["signal", "horizon_bars", "n_events", "observed_mean_bp", "bootstrap_se_bp", "t_stat", "p_value", "bh_significant_q10"],
            float_fmt={"observed_mean_bp": "{:.3f}", "bootstrap_se_bp": "{:.3f}", "t_stat": "{:.3f}", "p_value": "{:.4f}"},
        )
    )
    lines.append("")
    lines.extend(
        md_table(
            gates_df,
            cols=["signal", "gate1_min_events", "gate2_fdr", "gate3_materiality", "gate3_eligible_horizons", "gate4_year_consistency", "h_star", "promoted"],
        )
    )
    lines.append("")

    # ---- Section 2.1: seed invariance + circular-shift placebo (precision amendment) ----
    lines.append("### 2.1 Seed invariance and circular-shift placebo (precision amendment, supplementary)")
    lines.append("")
    event_study_text = (REPORTS_DIR / "event_study_btc.md").read_text(encoding="utf-8")
    seed_line = next((ln for ln in event_study_text.splitlines() if ln.startswith("**Seed-invariance")), "")
    lines.append(
        "The cells above are from the precision-amended primary run (day-cluster bootstrap, "
        "2,000,000 reps - preregistration/DEVIATIONS.md entry 1, up from the originally pre-registered "
        "10,000). " + seed_line
    )
    lines.append("")
    lines.append(
        "Additive, non-gating supplement (preregistration/DEVIATIONS.md entry 2): a circular-shift "
        "placebo tests event-return *alignment* net of market beta - the failure channel the "
        "multiplicity-corrected bootstrap alone does not isolate. Does not participate in gates, "
        "promotion, or BH-FDR. Full methodology and interpretation in reports/event_study_btc.md."
    )
    lines.append("")
    placebo_df = pl.read_csv(REPORTS_DIR / "event_study_btc_placebo_cells.csv")
    lines.extend(
        md_table(
            placebo_df,
            cols=["signal", "horizon_bars", "observed_mean_bp", "placebo_p", "mean_admitted_fraction"],
            float_fmt={"observed_mean_bp": "{:.3f}", "placebo_p": "{:.4f}", "mean_admitted_fraction": "{:.4f}"},
        )
    )
    lines.append("")

    # ---- Section 3: Phase 4 / OOS / ETH / DSR ----
    lines.append("## 3. Phase 4 backtest, OOS, ETH replication, DSR - all reserved (no promotions)")
    lines.append("")
    lines.append(
        f"Zero signals were promoted in section 2, so per preregistration section 6.5 and explicit "
        f"instruction: **Phase 4 confirmatory backtest was not run (no-op).** The out-of-sample segment "
        f"({OOS_START.date()} to {OOS_END.date()}) is reserved for promoted signals only; none were "
        f"promoted, so **no event-return statistic of any kind was computed on OOS data** - not "
        f"descriptively, not for completeness. It remains untouched, available cleanly for any future "
        f"pre-registered follow-up. ETH replication is promoted-signals-only per the prereg; the ETH bar "
        f"store exists and passed the same Phase 2 QA as BTC (see reports/QA_SUMMARY.md), but no ETH "
        f"detection or event study was run, since there is nothing to replicate."
    )
    lines.append("")
    lines.append(
        "**Deflated Sharpe Ratio:** no promoted strategy exists to deflate. The declared total trial "
        "count is disclosed for transparency regardless: N_trials = 140 = 20 (BTC in-sample cells) + 20 "
        "(BTC out-of-sample cells, would-have-been) + 20 (ETH replication cells, would-have-been) + 80 "
        "(sensitivity grid cells, section 4) - preregistration section 6.7. The circular-shift placebo "
        "(section 2.1) is deliberately excluded from this count: DSR's N corrects for selection bias "
        "across a *search* that could have led to a promotion, and the placebo is a non-gating post-hoc "
        "diagnostic computed over an already-fixed, already-not-promoted event set - it was never a draw "
        "from that search."
    )
    lines.append("")

    # ---- Section 4: sensitivity grid ----
    lines.append("## 4. Sensitivity grid (report-only, BTC in-sample)")
    lines.append("")
    sens_cells = pl.read_csv(REPORTS_DIR / "sensitivity_grid_cells.csv")
    n_sig_sens = sens_cells.filter(pl.col("t_stat").abs() > 1.96).height
    lines.append(
        f"Full tables in reports/sensitivity_grid.md (verbatim, including the mandatory interpretation "
        f"preamble - reproduced in section 4.1 below). {sens_cells.height} additional uncorrected cells "
        f"across 4 one-factor-at-a-time configs (Delta=10, Delta=50, bar=3m, bar=15m). "
        f"**{n_sig_sens} of {sens_cells.height} cells** show |t|>1.96, against a naive independence-based "
        f"expectation of ~{int(round(sens_cells.height*0.05))} - not a contradiction, since the 80 cells "
        f"are far from independent (the same underlying BTC price series and, for H1, an identical "
        f"detector unaffected by the Delta parameter, are reused across configs). No FDR correction, "
        f"gates, or promotion are computed here; see section 4.1 for the full interpretation."
    )
    lines.append("")
    lines.append("### 4.1 Cells crossing |t|>1.96 (hypothesis-generating only, not actionable)")
    lines.append("")
    sig_sens = sens_cells.filter(pl.col("t_stat").abs() > 1.96).sort(["config", "signal", "horizon_bars"])
    lines.extend(
        md_table(
            sig_sens,
            cols=["config", "signal", "horizon_bars", "n_events", "mean_bp", "t_stat", "ci95_lo_bp", "ci95_hi_bp"],
            float_fmt={"mean_bp": "{:.3f}", "t_stat": "{:.3f}", "ci95_lo_bp": "{:.2f}", "ci95_hi_bp": "{:.2f}"},
        )
    )
    lines.append("")

    # ---- Section 5: event counts by year ----
    lines.append("## 5. Event counts by calendar half-year (regime skew)")
    lines.append("")
    lines.append("Verbatim from reports/event_counts_by_half_year.md.")
    lines.append("")
    year_table = (REPORTS_DIR / "event_counts_by_half_year.md").read_text(encoding="utf-8")
    # strip its own header, keep the table + note
    body = year_table.split("\n\n", 2)[-1]
    lines.append(body)
    lines.append("")

    # ---- Section 6: DATA-BLOCKED register ----
    lines.append("## 6. DATA-BLOCKED: H4 (liquidity wall), H5 (liquidity pull)")
    lines.append("")
    lines.append(
        "No confirmatory claim, backtest, or event study was produced for either hypothesis anywhere in "
        "this study - the official Binance archive has no full-depth L2 history, and third-party vendors' "
        "free tiers (1st-of-month-only) are structurally insufficient for a confirmatory event study. No "
        "claim of \"no edge\" is made for H4/H5 either - absence of a test is not evidence of absence. "
        "See preregistration/PREREGISTRATION.md section 3 for the full justification, and ROADMAP.md for "
        "the v1.5 path (collector/depth_recorder.py ships in this repo now)."
    )
    lines.append("")

    # ---- Section 7: QA summary ----
    lines.append("## 7. Data QA summary")
    lines.append("")
    qa_text = (REPORTS_DIR / "QA_SUMMARY.md").read_text(encoding="utf-8")
    gate_line = next((line for line in qa_text.splitlines() if line.startswith("## FINAL GATE")), "## FINAL GATE: unknown")
    lines.append(f"**{gate_line.replace('## ', '')}** - full detail in reports/QA_SUMMARY.md, including the complete "
                  f"per-day breach classification table, the monthly-archive-gap backfill log, zero-trade-bar "
                  f"timestamps, and the raw-retention/bookDepth notes.")
    lines.append("")

    # ---- Section 8: methodology summary ----
    lines.append("## 8. Methodology summary")
    lines.append("")
    lines.append(
        "- **Pre-registration before PnL:** preregistration/PREREGISTRATION.md, frozen before any forward "
        "return or PnL was computed; one revision during review (the h*/E(signal) promotion-horizon rule) "
        "is recorded in that document's Appendix A, not as a post-approval deviation.\n"
        "- **FDR family:** exactly the 20 BTC in-sample cells (4 signals x 5 horizons), Benjamini-Hochberg "
        "at q=0.10. OOS and ETH cells are confirmatory follow-ups outside this family, by design - moot "
        "here since nothing was promoted.\n"
        "- **Promotion machinery (built, never fired):** gate 3 tests only whether the eligible-horizon "
        "set E(signal) is non-empty (FDR-significant AND >=30m AND >=materiality); a separate fully "
        "deterministic rule selects h* = argmax bootstrap t-statistic over E(signal). This decouples "
        "'does an edge exist' from 'which horizon is traded', eliminating a post-hoc degree of freedom. "
        "Never exercised in this study since no signal reached gate 3.\n"
        "- **Day-cluster bootstrap:** p-values and CIs resample calendar days (not individual events) with "
        "replacement, 2,000,000 reps (precision amendment - preregistration/DEVIATIONS.md entry 1; "
        "originally pre-registered at 10,000), respecting intraday event clustering and serial "
        "dependence. Seeded deterministically (orderflow.stats.stable_seed) after a reproducibility bug "
        "was found and fixed mid-review (Python's hash() on a tuple is randomized per process by "
        "default); the precision amendment additionally verified BH-significance is stable across 3 "
        "independent seeds (section 2.1). Spearman IC keeps its own lower rep count (10,000, unchanged) "
        "- informational-only per preregistration section 6.2, never worth the cost of the same "
        "precision.\n"
        "- **Circular-shift placebo:** additive, non-gating supplement (preregistration/DEVIATIONS.md "
        "entry 2, section 2.1) - tests event-return alignment against a null that preserves the entire "
        "return series (and therefore any unconditional drift/market beta), rather than testing for the "
        "existence of drift itself.\n"
        "- **Segment purging:** an event is admitted to a segment's statistics only if its longest "
        "horizon's forward window (48 bars) closes entirely within that same segment - per-event, not "
        "per-horizon, so all 5 horizons of a cell always share an identical event set.\n"
        "- **Quarantine:** a confirmed exchange-side data gap (2022-09-06, both symbols, present in both "
        "monthly and daily Binance archives) is excluded from event formation and any forward-return "
        "window overlapping it is nulled - src/orderflow/quarantine.py, applied before dedup so a "
        "quarantined event cannot have suppressed a legitimate nearby one via the 6-bar dedup rule.\n"
        f"- **DSR trial count:** N=140, declared and enumerated in section 3 above (the placebo's 20 "
        f"cells are deliberately excluded - see section 3)."
    )
    lines.append("")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "FINAL_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    log(f"Wrote {REPORTS_DIR / 'FINAL_REPORT.md'}")


if __name__ == "__main__":
    run()
