# Order Flow Research Engine v1 - Final Report

Runner-generated (runners/phase5_final_report.py). Numeric content is read directly
from the source CSV/JSON artifacts of each phase, never hand-typed. Do not hand-edit.

Study period: 2022-07-01 to 2026-06-30. In-sample (discovery): 2022-07-01 to 2024-12-31. Out-of-sample (confirmation, reserved, untouched by this study - see section 3): 2025-01-01 to 2026-06-30.

## 1. Headline result

Four classic order-flow footprint signals (H1 delta divergence, H2 absorption, H3 stacked imbalance, H6 exhaustion) were tested on BTCUSDT perpetual futures in-sample under a pre-registered falsification protocol. Two further hypotheses (H4 liquidity wall, H5 liquidity pull) were DATA-BLOCKED for the entire study (section 6). Of the 20 tested cells (4 signals x 5 horizons), **0 cleared BH-FDR significance at q=0.1**, and **0 of 4 signals were promoted** to the confirmatory backtest.

The most statistically credible cell in the entire 20-cell table - the highest-mean cell among those clearing raw p<0.05 (before FDR correction) - was H1 at h=12 bars, mean gross return 2.12bp (raw p=0.0109, t=2.571, not BH-significant). Against the pre-registered materiality bar of 18.0bp (1.5x the ~12.0bp round-trip cost floor), this is ~8.5x below the threshold required to call it economically material even before considering statistical significance at all. **This is a double null: informational (fails BH-FDR) and economic (even the best cell falls far short of materiality).** (Note: a handful of other cells, e.g. H3 h=48 at 16.0bp, show a nominally larger point estimate but a far wider standard error - SE=17.0bp vs 0.8bp here - i.e. noise, not signal; excluded from this comparison for exactly that reason.)

## 2. Phase 3 event study (BTC in-sample, 20-cell family)

Verbatim from reports/event_study_btc.md / event_study_btc_cells.csv / event_study_btc_gates.csv.

| signal | horizon_bars | n_events | observed_mean_bp | bootstrap_se_bp | t_stat | p_value | bh_significant_q10 |
|---|---|---|---|---|---|---|---|
| H1 | 1 | 4609 | 0.248 | 0.289 | 0.860 | 0.3856 | False |
| H1 | 3 | 4609 | 0.477 | 0.455 | 1.050 | 0.2930 | False |
| H1 | 6 | 4609 | 1.543 | 0.596 | 2.588 | 0.0100 | False |
| H1 | 12 | 4608 | 2.121 | 0.825 | 2.571 | 0.0109 | False |
| H1 | 48 | 4608 | 2.327 | 1.424 | 1.634 | 0.1038 | False |
| H2 | 1 | 783 | -0.484 | 1.084 | -0.446 | 0.6571 | False |
| H2 | 3 | 783 | 1.074 | 1.444 | 0.743 | 0.4524 | False |
| H2 | 6 | 783 | 1.450 | 1.975 | 0.734 | 0.4595 | False |
| H2 | 12 | 783 | 0.880 | 2.731 | 0.322 | 0.7454 | False |
| H2 | 48 | 783 | -3.683 | 4.605 | -0.800 | 0.4257 | False |
| H3 | 1 | 62 | 2.654 | 2.761 | 0.961 | 0.3394 | False |
| H3 | 3 | 62 | -2.479 | 4.314 | -0.575 | 0.5612 | False |
| H3 | 6 | 62 | 1.410 | 6.847 | 0.206 | 0.8379 | False |
| H3 | 12 | 62 | -7.666 | 9.503 | -0.807 | 0.4136 | False |
| H3 | 48 | 62 | 16.003 | 16.975 | 0.943 | 0.3437 | False |
| H6 | 1 | 286 | 0.649 | 1.997 | 0.325 | 0.7169 | False |
| H6 | 3 | 286 | -2.456 | 3.464 | -0.709 | 0.4800 | False |
| H6 | 6 | 286 | -5.405 | 4.249 | -1.272 | 0.1980 | False |
| H6 | 12 | 286 | -6.554 | 6.514 | -1.006 | 0.3121 | False |
| H6 | 48 | 286 | -6.175 | 9.271 | -0.666 | 0.5128 | False |

| signal | gate1_min_events | gate2_fdr | gate3_materiality | gate3_eligible_horizons | gate4_year_consistency | h_star | promoted |
|---|---|---|---|---|---|---|---|
| H1 | True | False | False | [] | False | n/a | False |
| H2 | True | False | False | [] | False | n/a | False |
| H3 | False | False | False | [] | False | n/a | False |
| H6 | False | False | False | [] | False | n/a | False |

### 2.1 Seed invariance and circular-shift placebo (precision amendment, supplementary)

The cells above are from the precision-amended primary run (day-cluster bootstrap, 2,000,000 reps - preregistration/DEVIATIONS.md entry 1, up from the originally pre-registered 10,000). **Seed-invariance HOLDS**: the BH-significant set is identical across all 3 seeds. This is expected at 2,000,000 reps for a result this far from the FDR boundary in either direction; it does not by itself mean p-values/CIs are bit-identical across seeds (they are not - that would indicate a seeding bug, not precision), only that the qualitative significant/not-significant call for every cell is stable.

Additive, non-gating supplement (preregistration/DEVIATIONS.md entry 2): a circular-shift placebo tests event-return *alignment* net of market beta - the failure channel the multiplicity-corrected bootstrap alone does not isolate. Does not participate in gates, promotion, or BH-FDR. Full methodology and interpretation in reports/event_study_btc.md.

| signal | horizon_bars | observed_mean_bp | placebo_p | mean_admitted_fraction |
|---|---|---|---|---|
| H1 | 1 | 0.248 | 0.2811 | 0.9664 |
| H1 | 3 | 0.477 | 0.2199 | 0.9664 |
| H1 | 6 | 1.543 | 0.0047 | 0.9664 |
| H1 | 12 | 2.121 | 0.0058 | 0.9664 |
| H1 | 48 | 2.327 | 0.0850 | 0.9664 |
| H2 | 1 | -0.484 | 0.3816 | 0.9668 |
| H2 | 3 | 1.074 | 0.2443 | 0.9668 |
| H2 | 6 | 1.450 | 0.2637 | 0.9668 |
| H2 | 12 | 0.880 | 0.6295 | 0.9668 |
| H2 | 48 | -3.683 | 0.3589 | 0.9668 |
| H3 | 1 | 2.654 | 0.1642 | 0.9661 |
| H3 | 3 | -2.479 | 0.4400 | 0.9661 |
| H3 | 6 | 1.410 | 0.7603 | 0.9661 |
| H3 | 12 | -7.666 | 0.2455 | 0.9661 |
| H3 | 48 | 16.003 | 0.2367 | 0.9661 |
| H6 | 1 | 0.649 | 0.4722 | 0.9662 |
| H6 | 3 | -2.456 | 0.1135 | 0.9662 |
| H6 | 6 | -5.405 | 0.0168 | 0.9662 |
| H6 | 12 | -6.554 | 0.0371 | 0.9662 |
| H6 | 48 | -6.175 | 0.3187 | 0.9662 |

## 3. Phase 4 backtest, OOS, ETH replication, DSR - all reserved (no promotions)

Zero signals were promoted in section 2, so per preregistration section 6.5 and explicit instruction: **Phase 4 confirmatory backtest was not run (no-op).** The out-of-sample segment (2025-01-01 to 2026-06-30) is reserved for promoted signals only; none were promoted, so **no event-return statistic of any kind was computed on OOS data** - not descriptively, not for completeness. It remains untouched, available cleanly for any future pre-registered follow-up. ETH replication is promoted-signals-only per the prereg; the ETH bar store exists and passed the same Phase 2 QA as BTC (see reports/QA_SUMMARY.md), but no ETH detection or event study was run, since there is nothing to replicate.

**Deflated Sharpe Ratio:** no promoted strategy exists to deflate. The declared total trial count is disclosed for transparency regardless: N_trials = 140 = 20 (BTC in-sample cells) + 20 (BTC out-of-sample cells, would-have-been) + 20 (ETH replication cells, would-have-been) + 80 (sensitivity grid cells, section 4) - preregistration section 6.7. The circular-shift placebo (section 2.1) is deliberately excluded from this count: DSR's N corrects for selection bias across a *search* that could have led to a promotion, and the placebo is a non-gating post-hoc diagnostic computed over an already-fixed, already-not-promoted event set - it was never a draw from that search.

## 4. Sensitivity grid (report-only, BTC in-sample)

Full tables in reports/sensitivity_grid.md (verbatim, including the mandatory interpretation preamble - reproduced in section 4.1 below). 80 additional uncorrected cells across 4 one-factor-at-a-time configs (Delta=10, Delta=50, bar=3m, bar=15m). **8 of 80 cells** show |t|>1.96, against a naive independence-based expectation of ~4 - not a contradiction, since the 80 cells are far from independent (the same underlying BTC price series and, for H1, an identical detector unaffected by the Delta parameter, are reused across configs). No FDR correction, gates, or promotion are computed here; see section 4.1 for the full interpretation.

### 4.1 Cells crossing |t|>1.96 (hypothesis-generating only, not actionable)

| config | signal | horizon_bars | n_events | mean_bp | t_stat | ci95_lo_bp | ci95_hi_bp |
|---|---|---|---|---|---|---|---|
| bar15m_delta25 | H3 | 3 | 6 | -37.438 | -2.133 | -74.20 | -5.39 |
| bar15m_delta25 | H3 | 12 | 6 | -77.646 | -2.086 | -159.04 | -13.10 |
| bar3m_delta25 | H3 | 1 | 178 | -3.781 | -2.023 | -7.47 | -0.14 |
| delta10_bar5m | H1 | 6 | 4609 | 1.542 | 2.616 | 0.39 | 2.70 |
| delta10_bar5m | H1 | 12 | 4609 | 2.054 | 2.479 | 0.44 | 3.68 |
| delta10_bar5m | H3 | 12 | 277 | -9.828 | -2.335 | -17.98 | -1.48 |
| delta50_bar5m | H1 | 6 | 4609 | 1.543 | 2.588 | 0.36 | 2.70 |
| delta50_bar5m | H1 | 12 | 4609 | 2.056 | 2.482 | 0.39 | 3.64 |

## 5. Event counts by calendar half-year (regime skew)

Verbatim from reports/event_counts_by_half_year.md.

Full deduped BTC sample (warm-up + dedup + quarantine filter applied; both IS and OOS periods included) - counts only. No forward returns computed for OOS events; this table does not touch the OOS-reservation rule, it only documents where detected events fall in calendar time.

| Signal | 2022H2 | 2023H1 | 2023H2 | 2024H1 | 2024H2 | 2025H1 | 2025H2 | 2026H1 | Total | IS share |
|---|---|---|---|---|---|---|---|---|---|---|
| H1 | 799 | 903 | 919 | 969 | 1020 | 1136 | 1008 | 1031 | 7785 | 59.2% |
| H2 | 24 | 46 | 81 | 256 | 376 | 519 | 574 | 489 | 2365 | 33.1% |
| H3 | 4 | 3 | 3 | 18 | 34 | 55 | 95 | 69 | 281 | 22.1% |
| H6 | 56 | 35 | 49 | 62 | 84 | 139 | 177 | 128 | 730 | 39.2% |

Calendar-time IS share (2022H2-2024H2 out of the full 2022H2-2026H1 sample): 62.6%. Compare each signal's IS share above against this 62.6% baseline to see regime skew - e.g. a signal materially above baseline fires disproportionately in the discovery period, below baseline disproportionately post-discovery.


## 6. DATA-BLOCKED: H4 (liquidity wall), H5 (liquidity pull)

No confirmatory claim, backtest, or event study was produced for either hypothesis anywhere in this study - the official Binance archive has no full-depth L2 history, and third-party vendors' free tiers (1st-of-month-only) are structurally insufficient for a confirmatory event study. No claim of "no edge" is made for H4/H5 either - absence of a test is not evidence of absence. See preregistration/PREREGISTRATION.md section 3 for the full justification, and ROADMAP.md for the v1.5 path (collector/depth_recorder.py ships in this repo now).

## 7. Data QA summary

**FINAL GATE: PASS-WITH-EXCEPTIONS** - full detail in reports/QA_SUMMARY.md, including the complete per-day breach classification table, the monthly-archive-gap backfill log, zero-trade-bar timestamps, and the raw-retention/bookDepth notes.

## 8. Methodology summary

- **Pre-registration before PnL:** preregistration/PREREGISTRATION.md, frozen before any forward return or PnL was computed; one revision during review (the h*/E(signal) promotion-horizon rule) is recorded in that document's Appendix A, not as a post-approval deviation.
- **FDR family:** exactly the 20 BTC in-sample cells (4 signals x 5 horizons), Benjamini-Hochberg at q=0.10. OOS and ETH cells are confirmatory follow-ups outside this family, by design - moot here since nothing was promoted.
- **Promotion machinery (built, never fired):** gate 3 tests only whether the eligible-horizon set E(signal) is non-empty (FDR-significant AND >=30m AND >=materiality); a separate fully deterministic rule selects h* = argmax bootstrap t-statistic over E(signal). This decouples 'does an edge exist' from 'which horizon is traded', eliminating a post-hoc degree of freedom. Never exercised in this study since no signal reached gate 3.
- **Day-cluster bootstrap:** p-values and CIs resample calendar days (not individual events) with replacement, 2,000,000 reps (precision amendment - preregistration/DEVIATIONS.md entry 1; originally pre-registered at 10,000), respecting intraday event clustering and serial dependence. Seeded deterministically (orderflow.stats.stable_seed) after a reproducibility bug was found and fixed mid-review (Python's hash() on a tuple is randomized per process by default); the precision amendment additionally verified BH-significance is stable across 3 independent seeds (section 2.1). Spearman IC keeps its own lower rep count (10,000, unchanged) - informational-only per preregistration section 6.2, never worth the cost of the same precision.
- **Circular-shift placebo:** additive, non-gating supplement (preregistration/DEVIATIONS.md entry 2, section 2.1) - tests event-return alignment against a null that preserves the entire return series (and therefore any unconditional drift/market beta), rather than testing for the existence of drift itself.
- **Segment purging:** an event is admitted to a segment's statistics only if its longest horizon's forward window (48 bars) closes entirely within that same segment - per-event, not per-horizon, so all 5 horizons of a cell always share an identical event set.
- **Quarantine:** a confirmed exchange-side data gap (2022-09-06, both symbols, present in both monthly and daily Binance archives) is excluded from event formation and any forward-return window overlapping it is nulled - src/orderflow/quarantine.py, applied before dedup so a quarantined event cannot have suppressed a legitimate nearby one via the 6-bar dedup rule.
- **DSR trial count:** N=140, declared and enumerated in section 3 above (the placebo's 20 cells are deliberately excluded - see section 3).
