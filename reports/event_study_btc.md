# Event Study - BTCUSDT In-Sample

Runner-generated (runners/phase3_event_study.py). Do not hand-edit.

20-cell family (4 signals x 5 horizons), BH-FDR q=0.1. 
Cost model: round trip ~= 12.0bp; materiality gate requires mean gross return >= 18.0bp.
Day-cluster bootstrap: 2,000,000 reps (precision amendment - preregistration/DEVIATIONS.md entry 1; was 10,000 at prereg sign-off). Spearman IC: 10,000 reps (unchanged, informational-only per preregistration section 6.2).

## Event accounting

- Raw detected: 11,820 -> after quarantine filter: 11,820 -> after warm-up (bar_index>=8640): 11,810 -> after dedup (6-bar, keep-first): 11,161

**Warm-up clarification:** exactly 10 events were removed at the warm-up stage (bar_index < 8640), broken down as H1=0, H2=3, H3=1, H6=6. This small number is fully explained by two independent, verified mechanisms rather than a partially-applied warm-up: (1) H1's own trailing 8640-bar sigma window (the statistic that sets the warm-up constant in the first place) already makes its earliest possible event bar_index ~8693 - past the warm-up boundary before the filter does anything, so H1 contributes 0. (2) H6's own trailing 2016-bar P95 window makes bars 2016-8639 the only pre-warm-up region where it can fire at all (a 6624-bar span, not the ~30-day full pre-warm-up window); its 6 removed events fall there. (3) H2 and H3 use a pooled-percentile rolling reference (orderflow.rolling.rolling_pooled_percentile for med96/p25_96) that does not enforce a hard minimum-sample count the way polars' native rolling_* functions do (min_periods=window_size) - so they are mechanically eligible to fire from very early bars, not just after ~96 bars of history. Despite that wider eligibility window, only 3 (H2) and 1 (H3) events actually satisfy the full compound trigger condition before bar_index 8640, at bar_index 2754+ and 6421 respectively - both already well past 96, so their own reference windows were fully populated regardless. This is empirical rarity of the compound pattern in that stretch of the sample, not a partially-populated statistic; verified by confirming zero events with bar_index<8640 survive into the post-warm-up, post-dedup event set actually used below.

| Signal | Raw | Final (post warm-up+dedup) | Bull | Bear |
|---|---|---|---|---|
| H1 | 8,005 | 7,785 | 3,894 | 3,891 |
| H2 | 2,729 | 2,365 | 1,702 | 663 |
| H3 | 291 | 281 | 145 | 136 |
| H6 | 795 | 730 | 364 | 366 |

- BTC in-sample events surviving segment-purge admission (used in the 20-cell statistics below): 5,740

## Cells

| Signal | Horizon (bars) | N | Mean (bp) | Bootstrap SE (bp) | t | raw p | BH-FDR q=0.10 sig | 95% CI (bp) | Spearman IC | Rank by p | Operative BH threshold | MC-SE of p-hat | Straddles threshold |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H1 | 1 | 4609 | 0.248 | 0.289 | 0.860 | 0.3856 | False | [-0.33, 0.80] | -0.001 | 9 | 0.0450 | 0.000344 | False |
| H1 | 3 | 4609 | 0.477 | 0.455 | 1.050 | 0.2930 | False | [-0.43, 1.36] | 0.015 | 5 | 0.0250 | 0.000322 | False |
| H1 | 6 | 4609 | 1.543 | 0.596 | 2.588 | 0.0100 | False | [0.37, 2.71] | 0.010 | 1 | 0.0050 | 0.000070 | False |
| H1 | 12 | 4608 | 2.121 | 0.825 | 2.571 | 0.0109 | False | [0.49, 3.73] | -0.009 | 2 | 0.0100 | 0.000073 | False |
| H1 | 48 | 4608 | 2.327 | 1.424 | 1.634 | 0.1038 | False | [-0.48, 5.10] | -0.004 | 3 | 0.0150 | 0.000216 | False |
| H2 | 1 | 783 | -0.484 | 1.084 | -0.446 | 0.6571 | False | [-2.62, 1.63] | 0.057 | 17 | 0.0850 | 0.000336 | False |
| H2 | 3 | 783 | 1.074 | 1.444 | 0.743 | 0.4524 | False | [-1.79, 3.87] | 0.026 | 12 | 0.0600 | 0.000352 | False |
| H2 | 6 | 783 | 1.450 | 1.975 | 0.734 | 0.4595 | False | [-2.47, 5.28] | 0.045 | 13 | 0.0650 | 0.000352 | False |
| H2 | 12 | 783 | 0.880 | 2.731 | 0.322 | 0.7454 | False | [-4.48, 6.22] | 0.067 | 19 | 0.0950 | 0.000308 | False |
| H2 | 48 | 783 | -3.683 | 4.605 | -0.800 | 0.4257 | False | [-12.80, 5.25] | 0.016 | 11 | 0.0550 | 0.000350 | False |
| H3 | 1 | 62 | 2.654 | 2.761 | 0.961 | 0.3394 | False | [-2.94, 7.88] | -0.177 | 7 | 0.0350 | 0.000335 | False |
| H3 | 3 | 62 | -2.479 | 4.314 | -0.575 | 0.5612 | False | [-11.01, 5.90] | 0.053 | 16 | 0.0800 | 0.000351 | False |
| H3 | 6 | 62 | 1.410 | 6.847 | 0.206 | 0.8379 | False | [-12.03, 14.81] | -0.016 | 20 | 0.1000 | 0.000261 | False |
| H3 | 12 | 62 | -7.666 | 9.503 | -0.807 | 0.4136 | False | [-26.45, 10.80] | 0.037 | 10 | 0.0500 | 0.000348 | False |
| H3 | 48 | 62 | 16.003 | 16.975 | 0.943 | 0.3437 | False | [-16.72, 49.83] | 0.011 | 8 | 0.0400 | 0.000336 | False |
| H6 | 1 | 286 | 0.649 | 1.997 | 0.325 | 0.7169 | False | [-3.45, 4.38] | -0.000 | 18 | 0.0900 | 0.000319 | False |
| H6 | 3 | 286 | -2.456 | 3.464 | -0.709 | 0.4800 | False | [-9.30, 4.28] | -0.025 | 14 | 0.0700 | 0.000353 | False |
| H6 | 6 | 286 | -5.405 | 4.249 | -1.272 | 0.1980 | False | [-14.03, 2.62] | -0.014 | 4 | 0.0200 | 0.000282 | False |
| H6 | 12 | 286 | -6.554 | 6.514 | -1.006 | 0.3121 | False | [-20.19, 5.35] | -0.014 | 6 | 0.0300 | 0.000328 | False |
| H6 | 48 | 286 | -6.175 | 9.271 | -0.666 | 0.5128 | False | [-24.93, 11.41] | 0.025 | 15 | 0.0750 | 0.000353 | False |

**Precision self-containment check (post-hoc robustness diagnostic - not a pre-registered rule; added this round alongside the precision amendment):** for each cell, MC-SE of p-hat = sqrt(p-hat*(1-p-hat)/2,000,000), and the operative BH step-up threshold at that cell's rank (ascending by p, 1-indexed) is (rank/20)*0.1. A cell 'straddles' if its p-hat +/- 3xMC-SE interval contains its own operative threshold - i.e. finite-K Monte Carlo noise in p-hat could plausibly have flipped its significant/not-significant call. **No cell straddles its operative threshold at 2,000,000 reps.** Binding case (closest miss, rank 2): H1 h=12, p-hat=0.0109 +/- 0.0002 vs operative threshold 0.0100 - interval excludes the threshold, so the near-miss is not a precision artifact.

## Seed invariance (precision amendment)

The 20-cell family above was computed at seed label 'BTC-IS' (canonical/reported). To confirm the BH-FDR-significant set is not an artifact of Monte Carlo noise at this rep count, the full family was re-computed at 2,000,000 reps under 2 further independent seed labels. Primary BH-significant set: (none).

| Seed label | BH-significant set | Matches primary |
|---|---|---|
| BTC-IS-seedB | (none) | True |
| BTC-IS-seedC | (none) | True |

**Seed-invariance HOLDS**: the BH-significant set is identical across all 3 seeds. This is expected at 2,000,000 reps for a result this far from the FDR boundary in either direction; it does not by itself mean p-values/CIs are bit-identical across seeds (they are not - that would indicate a seeding bug, not precision), only that the qualitative significant/not-significant call for every cell is stable.

## Circular-shift placebo (supplementary, non-gating)

Additive supplement per preregistration/DEVIATIONS.md entry 2 - does **not** participate in gates, promotion, or BH-FDR, which remain frozen on the day-cluster bootstrap table above. For each signal's deduplicated BTC in-sample event set, K=10,000 circular shifts were drawn (one random offset per shift, applied to all of that signal's event bar-indices simultaneously, wrapping within the IS bar range; offset uniform over {2016, ..., N_IS_bars-2016} to forbid near-identity alignment). Shifted events landing in warm-up or a quarantine window are dropped for that replicate (same hygiene as reality); a shifted event's longest-horizon window decides admission once, shared across all horizons, exactly mirroring the real segment-purge rule. Placebo p (two-sided) = fraction of shifts whose |mean signed forward return| >= |observed|. Rationale: circular shifting preserves the entire return series, so unconditional drift sits inside the null - this tests event-return *alignment* net of market beta, the failure channel (bull-market beta masquerading as signal) the multiplicity-corrected bootstrap alone does not isolate. If placebo and bootstrap disagree anywhere, the disagreement is reported verbatim below, not reconciled or re-run.

| Signal | Horizon (bars) | Observed mean (bp) | Placebo p | Mean admitted fraction |
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

**Why the bootstrap and placebo disagree on H6 (mechanism, not a contradiction to resolve):** the two methods answer different questions. H6 conditions on P95 volume, so its events select high-dispersion states. The day-cluster bootstrap resamples the actual event days and inherits that dispersion; the circular-shift placebo relocates the event pattern to typical (unconditioned) states, producing a tighter null. The placebo therefore absorbs drift but does not preserve volatility-state conditioning - making it anti-conservative for state-conditioned signals like H6, which is precisely why the pre-registered gates run on the bootstrap and not on the placebo. **H6's sign is explicitly negative** (h=6: -5.405bp, h=12: -6.554bp) - the placebo is flagging possible *contrarian* alignment (fading the exhaustion signal), not support for H6 as originally hypothesized. No multiplicity procedure is applied to the placebo column: it is a non-gating diagnostic, and at K=10,000 its smallest p-values (e.g. H1 h=6's 0.0047, exactly 47/10,000) carry Monte Carlo granularity of the same kind just eliminated from the primary family by the precision amendment above - any threshold claim on the placebo column would be unstable by construction. Under either inference method the study's conclusion is unchanged where it matters: every cell sits far below the 18.0bp materiality bar, E(signal) = empty set for all four signals, and zero promotions occur.

## Promotion gates

| Signal | Gate1 (N>=300) | Gate2 (FDR>=2 horizons, >=1 >=30m) | Gate3 E(signal) eligible horizons | Gate4 h* IS-segment signs (2022H2/2023/2024) | Gate4 pass | h* | Promoted |
|---|---|---|---|---|---|---|---|
| H1 | True | False | [] | None | False | None | False |
| H2 | True | False | [] | None | False | None | False |
| H3 | False | False | [] | None | False | None | False |
| H6 | False | False | [] | None | False | None | False |

## No signals promoted

No signal cleared all four promotion gates on BTC in-sample data. Per the falsification protocol, this is a fully valid and reported outcome - see the per-cell table above for which gate(s) each signal failed (informational null vs. economic null, per preregistration section 2).
