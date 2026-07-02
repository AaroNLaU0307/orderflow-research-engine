# Event Study - BTCUSDT In-Sample

Runner-generated (runners/phase3_event_study.py). Do not hand-edit.

20-cell family (4 signals x 5 horizons), BH-FDR q=0.1. 
Cost model: round trip ~= 12.0bp; materiality gate requires mean gross return >= 18.0bp.

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

| Signal | Horizon (bars) | N | Mean (bp) | Bootstrap SE (bp) | t | raw p | BH-FDR q=0.10 sig | 95% CI (bp) | Spearman IC |
|---|---|---|---|---|---|---|---|---|---|
| H1 | 1 | 4609 | 0.248 | 0.288 | 0.863 | 0.3704 | False | [-0.32, 0.81] | -0.001 |
| H1 | 3 | 4609 | 0.477 | 0.456 | 1.047 | 0.2872 | False | [-0.43, 1.35] | 0.015 |
| H1 | 6 | 4609 | 1.543 | 0.602 | 2.564 | 0.0106 | False | [0.37, 2.73] | 0.010 |
| H1 | 12 | 4608 | 2.121 | 0.829 | 2.558 | 0.0124 | False | [0.51, 3.76] | -0.009 |
| H1 | 48 | 4608 | 2.327 | 1.442 | 1.614 | 0.1096 | False | [-0.53, 5.13] | -0.004 |
| H2 | 1 | 783 | -0.484 | 1.111 | -0.435 | 0.6664 | False | [-2.64, 1.71] | 0.057 |
| H2 | 3 | 783 | 1.074 | 1.454 | 0.738 | 0.4520 | False | [-1.78, 3.92] | 0.026 |
| H2 | 6 | 783 | 1.450 | 1.991 | 0.728 | 0.4664 | False | [-2.48, 5.32] | 0.045 |
| H2 | 12 | 783 | 0.880 | 2.763 | 0.318 | 0.7388 | False | [-4.54, 6.29] | 0.067 |
| H2 | 48 | 783 | -3.683 | 4.635 | -0.795 | 0.4194 | False | [-12.74, 5.43] | 0.016 |
| H3 | 1 | 62 | 2.654 | 2.711 | 0.979 | 0.3340 | False | [-2.92, 7.70] | -0.177 |
| H3 | 3 | 62 | -2.479 | 4.317 | -0.574 | 0.5672 | False | [-10.85, 6.08] | 0.053 |
| H3 | 6 | 62 | 1.410 | 6.824 | 0.207 | 0.8328 | False | [-11.96, 14.79] | -0.016 |
| H3 | 12 | 62 | -7.666 | 9.651 | -0.794 | 0.4260 | False | [-26.49, 11.35] | 0.037 |
| H3 | 48 | 62 | 16.003 | 17.158 | 0.933 | 0.3430 | False | [-16.94, 50.32] | 0.011 |
| H6 | 1 | 286 | 0.649 | 2.006 | 0.324 | 0.7140 | False | [-3.44, 4.42] | -0.000 |
| H6 | 3 | 286 | -2.456 | 3.490 | -0.704 | 0.4738 | False | [-9.42, 4.26] | -0.025 |
| H6 | 6 | 286 | -5.405 | 4.224 | -1.280 | 0.2104 | False | [-13.81, 2.75] | -0.014 |
| H6 | 12 | 286 | -6.554 | 6.485 | -1.011 | 0.3120 | False | [-20.10, 5.32] | -0.014 |
| H6 | 48 | 286 | -6.175 | 9.203 | -0.671 | 0.5074 | False | [-24.88, 11.20] | 0.025 |

## Promotion gates

| Signal | Gate1 (N>=300) | Gate2 (FDR>=2 horizons, >=1 >=30m) | Gate3 E(signal) eligible horizons | Gate4 h* IS-segment signs (2022H2/2023/2024) | Gate4 pass | h* | Promoted |
|---|---|---|---|---|---|---|---|
| H1 | True | False | [] | None | False | None | False |
| H2 | True | False | [] | None | False | None | False |
| H3 | False | False | [] | None | False | None | False |
| H6 | False | False | [] | None | False | None | False |

## No signals promoted

No signal cleared all four promotion gates on BTC in-sample data. Per the falsification protocol, this is a fully valid and reported outcome - see the per-cell table above for which gate(s) each signal failed (informational null vs. economic null, per preregistration section 2).
