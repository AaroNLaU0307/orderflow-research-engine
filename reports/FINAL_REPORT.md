# Order Flow Research Engine v1 - Final Report

Runner-generated (runners/phase5_final_report.py). Numeric content is read directly
from the source CSV/JSON artifacts of each phase, never hand-typed. Do not hand-edit.

Study period: 2022-07-01 to 2026-06-30. In-sample (discovery): 2022-07-01 to 2024-12-31. Out-of-sample (confirmation, reserved, untouched by this study - see section 3): 2025-01-01 to 2026-06-30.

## 1. Headline result

Four classic order-flow footprint signals (H1 delta divergence, H2 absorption, H3 stacked imbalance, H6 exhaustion) were tested on BTCUSDT perpetual futures in-sample under a pre-registered falsification protocol. Two further hypotheses (H4 liquidity wall, H5 liquidity pull) were DATA-BLOCKED for the entire study (section 6). Of the 20 tested cells (4 signals x 5 horizons), **0 cleared BH-FDR significance at q=0.1**, and **0 of 4 signals were promoted** to the confirmatory backtest.

The most statistically credible cell in the entire 20-cell table - the highest-mean cell among those clearing raw p<0.05 (before FDR correction) - was H1 at h=12 bars, mean gross return 2.12bp (raw p=0.0124, t=2.558, not BH-significant). Against the pre-registered materiality bar of 18.0bp (1.5x the ~12.0bp round-trip cost floor), this is ~8.5x below the threshold required to call it economically material even before considering statistical significance at all. **This is a double null: informational (fails BH-FDR) and economic (even the best cell falls far short of materiality).** (Note: a handful of other cells, e.g. H3 h=48 at 16.0bp, show a nominally larger point estimate but a far wider standard error - SE=17.2bp vs 0.8bp here - i.e. noise, not signal; excluded from this comparison for exactly that reason.)

## 2. Phase 3 event study (BTC in-sample, 20-cell family)

Verbatim from reports/event_study_btc.md / event_study_btc_cells.csv / event_study_btc_gates.csv.

| signal | horizon_bars | n_events | observed_mean_bp | bootstrap_se_bp | t_stat | p_value | bh_significant_q10 |
|---|---|---|---|---|---|---|---|
| H1 | 1 | 4609 | 0.248 | 0.288 | 0.863 | 0.3704 | False |
| H1 | 3 | 4609 | 0.477 | 0.456 | 1.047 | 0.2872 | False |
| H1 | 6 | 4609 | 1.543 | 0.602 | 2.564 | 0.0106 | False |
| H1 | 12 | 4608 | 2.121 | 0.829 | 2.558 | 0.0124 | False |
| H1 | 48 | 4608 | 2.327 | 1.442 | 1.614 | 0.1096 | False |
| H2 | 1 | 783 | -0.484 | 1.111 | -0.435 | 0.6664 | False |
| H2 | 3 | 783 | 1.074 | 1.454 | 0.738 | 0.4520 | False |
| H2 | 6 | 783 | 1.450 | 1.991 | 0.728 | 0.4664 | False |
| H2 | 12 | 783 | 0.880 | 2.763 | 0.318 | 0.7388 | False |
| H2 | 48 | 783 | -3.683 | 4.635 | -0.795 | 0.4194 | False |
| H3 | 1 | 62 | 2.654 | 2.711 | 0.979 | 0.3340 | False |
| H3 | 3 | 62 | -2.479 | 4.317 | -0.574 | 0.5672 | False |
| H3 | 6 | 62 | 1.410 | 6.824 | 0.207 | 0.8328 | False |
| H3 | 12 | 62 | -7.666 | 9.651 | -0.794 | 0.4260 | False |
| H3 | 48 | 62 | 16.003 | 17.158 | 0.933 | 0.3430 | False |
| H6 | 1 | 286 | 0.649 | 2.006 | 0.324 | 0.7140 | False |
| H6 | 3 | 286 | -2.456 | 3.490 | -0.704 | 0.4738 | False |
| H6 | 6 | 286 | -5.405 | 4.224 | -1.280 | 0.2104 | False |
| H6 | 12 | 286 | -6.554 | 6.485 | -1.011 | 0.3120 | False |
| H6 | 48 | 286 | -6.175 | 9.203 | -0.671 | 0.5074 | False |

| signal | gate1_min_events | gate2_fdr | gate3_materiality | gate3_eligible_horizons | gate4_year_consistency | h_star | promoted |
|---|---|---|---|---|---|---|---|
| H1 | True | False | False | [] | False | n/a | False |
| H2 | True | False | False | [] | False | n/a | False |
| H3 | False | False | False | [] | False | n/a | False |
| H6 | False | False | False | [] | False | n/a | False |

## 3. Phase 4 backtest, OOS, ETH replication, DSR - all reserved (no promotions)

Zero signals were promoted in section 2, so per preregistration section 6.5 and explicit instruction: **Phase 4 confirmatory backtest was not run (no-op).** The out-of-sample segment (2025-01-01 to 2026-06-30) is reserved for promoted signals only; none were promoted, so **no event-return statistic of any kind was computed on OOS data** - not descriptively, not for completeness. It remains untouched, available cleanly for any future pre-registered follow-up. ETH replication is promoted-signals-only per the prereg; the ETH bar store exists and passed the same Phase 2 QA as BTC (see reports/QA_SUMMARY.md), but no ETH detection or event study was run, since there is nothing to replicate.

**Deflated Sharpe Ratio:** no promoted strategy exists to deflate. The declared total trial count is disclosed for transparency regardless: N_trials = 140 = 20 (BTC in-sample cells) + 20 (BTC out-of-sample cells, would-have-been) + 20 (ETH replication cells, would-have-been) + 80 (sensitivity grid cells, section 4) - preregistration section 6.7.

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
- **Day-cluster bootstrap:** p-values and CIs resample calendar days (not individual events) with replacement, 10,000 reps, respecting intraday event clustering and serial dependence. Seeded deterministically (orderflow.stats.stable_seed) after a reproducibility bug was found and fixed mid-review (Python's hash() on a tuple is randomized per process by default).
- **Segment purging:** an event is admitted to a segment's statistics only if its longest horizon's forward window (48 bars) closes entirely within that same segment - per-event, not per-horizon, so all 5 horizons of a cell always share an identical event set.
- **Quarantine:** a confirmed exchange-side data gap (2022-09-06, both symbols, present in both monthly and daily Binance archives) is excluded from event formation and any forward-return window overlapping it is nulled - src/orderflow/quarantine.py, applied before dedup so a quarantined event cannot have suppressed a legitimate nearby one via the 6-bar dedup rule.
- **DSR trial count:** N=140, declared and enumerated in section 3 above.
