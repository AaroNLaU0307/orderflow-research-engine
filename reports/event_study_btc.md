# Event Study - BTCUSDT In-Sample

Runner-generated (runners/phase3_event_study.py). Do not hand-edit.

20-cell family (4 signals x 5 horizons), BH-FDR q=0.1. 
Cost model: round trip ~= 12.0bp; materiality gate requires mean gross return >= 18.0bp.

## Event accounting

- Raw detected: 11,820 -> after quarantine filter: 11,820 -> after warm-up (bar_index>=8640): 11,810 -> after dedup (6-bar, keep-first): 11,161

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
| H1 | 1 | 4609 | 0.248 | 0.289 | 0.860 | 0.3718 | False | [-0.33, 0.80] | -0.001 |
| H1 | 3 | 4609 | 0.477 | 0.456 | 1.047 | 0.2944 | False | [-0.43, 1.36] | 0.015 |
| H1 | 6 | 4609 | 1.543 | 0.597 | 2.584 | 0.0112 | False | [0.37, 2.71] | 0.010 |
| H1 | 12 | 4608 | 2.121 | 0.822 | 2.581 | 0.0098 | False | [0.50, 3.72] | -0.009 |
| H1 | 48 | 4608 | 2.327 | 1.435 | 1.622 | 0.1092 | False | [-0.56, 5.06] | -0.004 |
| H2 | 1 | 783 | -0.484 | 1.069 | -0.452 | 0.6486 | False | [-2.63, 1.56] | 0.057 |
| H2 | 3 | 783 | 1.074 | 1.469 | 0.731 | 0.4718 | False | [-1.82, 3.93] | 0.026 |
| H2 | 6 | 783 | 1.450 | 1.947 | 0.745 | 0.4496 | False | [-2.32, 5.32] | 0.045 |
| H2 | 12 | 783 | 0.880 | 2.710 | 0.325 | 0.7546 | False | [-4.52, 6.11] | 0.067 |
| H2 | 48 | 783 | -3.683 | 4.538 | -0.812 | 0.4224 | False | [-12.72, 5.07] | 0.016 |
| H3 | 1 | 62 | 2.654 | 2.830 | 0.938 | 0.3368 | False | [-3.14, 7.96] | -0.177 |
| H3 | 3 | 62 | -2.479 | 4.306 | -0.576 | 0.5636 | False | [-10.97, 5.90] | 0.053 |
| H3 | 6 | 62 | 1.410 | 6.842 | 0.206 | 0.8418 | False | [-11.89, 14.93] | -0.016 |
| H3 | 12 | 62 | -7.666 | 9.507 | -0.806 | 0.4242 | False | [-26.18, 11.08] | 0.037 |
| H3 | 48 | 62 | 16.003 | 16.956 | 0.944 | 0.3550 | False | [-17.31, 49.15] | 0.011 |
| H6 | 1 | 286 | 0.649 | 2.002 | 0.324 | 0.7260 | False | [-3.48, 4.37] | -0.000 |
| H6 | 3 | 286 | -2.456 | 3.420 | -0.718 | 0.4862 | False | [-9.15, 4.25] | -0.025 |
| H6 | 6 | 286 | -5.405 | 4.302 | -1.257 | 0.2014 | False | [-14.23, 2.64] | -0.014 |
| H6 | 12 | 286 | -6.554 | 6.558 | -0.999 | 0.3200 | False | [-20.26, 5.44] | -0.014 |
| H6 | 48 | 286 | -6.175 | 9.111 | -0.678 | 0.5010 | False | [-24.53, 11.19] | 0.025 |

## Promotion gates

| Signal | Gate1 (N>=300) | Gate2 (FDR>=2 horizons, >=1 >=30m) | Gate3 E(signal) eligible horizons | Gate4 h* IS-segment signs (2022H2/2023/2024) | Gate4 pass | h* | Promoted |
|---|---|---|---|---|---|---|---|
| H1 | True | False | [] | None | False | None | False |
| H2 | True | False | [] | None | False | None | False |
| H3 | False | False | [] | None | False | None | False |
| H6 | False | False | [] | None | False | None | False |

## No signals promoted

No signal cleared all four promotion gates on BTC in-sample data. Per the falsification protocol, this is a fully valid and reported outcome - see the per-cell table above for which gate(s) each signal failed (informational null vs. economic null, per preregistration section 2).
