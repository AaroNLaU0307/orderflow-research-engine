# Sensitivity Grid - BTCUSDT In-Sample (report-only)

Runner-generated (runners/phase3_sensitivity_run.py). Do not hand-edit.

## Mandatory interpretation preamble

These are 80 additional, UNCORRECTED cells (4 configs x 4 signals x 5 horizons) whose only role is robustness-of-the-null: plateau evidence that the primary Phase 3 falsification (0 of 20 cells BH-FDR significant at q=0.10, BTC in-sample, 5m/Delta=25) is not an artifact of that specific bar/bucket choice. **No FDR correction, no promotion gates, no h* selection, and no promotion decision are computed or implied here.** Under the global null, with 80 independent-ish t-statistics at the |t|>1.96 (~5%) two-sided threshold, roughly 4 cells are expected to cross that bar by chance alone; an isolated CI-excluding-zero cell in the table below is hypothesis-generating only and cannot be promoted - acting on one would require a fresh pre-registered study on unseen data. H3's event count mechanically multiplies at Delta=10 and bar=3m (finer buckets/bars create more opportunities for its 3-consecutive-level imbalance condition to fire); that changes statistical power, not the substance of any conclusion, and is reported as such rather than as a finding.

## Scaled window constants per config

Threshold RATIOS (H2 4x median volume, H2 70% aggression, H3 3.0x imbalance ratio, H6 95th volume percentile, H2 20% zone fraction) are unchanged across all configs. Only window sizes measured in bar-counts are rescaled, to preserve wall-clock duration relative to the primary 5-minute-bar convention:

| Config | Delta | Bar | H1 cumD window (2h) | H1 sigma window (30d) | H2/H3 vol window (8h) | H6 vol window (1wk) | Dedup gap (30min) | Warm-up |
|---|---|---|---|---|---|---|---|---|
| delta10_bar5m | 10.0 | 5m | 24 | 8640 | 96 | 2016 | 6 | 8640 |
| delta50_bar5m | 50.0 | 5m | 24 | 8640 | 96 | 2016 | 6 | 8640 |
| bar3m_delta25 | 25.0 | 3m | 40 | 14400 | 160 | 3360 | 10 | 14400 |
| bar15m_delta25 | 25.0 | 15m | 8 | 2880 | 32 | 672 | 2 | 2880 |

**Horizon interpretation:** forward-return horizons are kept as the literal bar-counts {1,3,6,12,48} from preregistration section 6.1 for every config (not wall-clock-rescaled - 5 minutes does not evenly divide into 3-minute or 15-minute bars). Wall-clock meaning per config: delta10/delta50 (bar=5m) = {5m,15m,30m,1h,4h} (unchanged); bar=3m = {3m,9m,18m,36m,144m}; bar=15m = {15m,45m,1.5h,3h,12h}.

## delta10_bar5m: Delta=10 USDT, bar=5m (baseline Delta=25)

| Signal | Raw events | Final (warmup+dedup) |
|---|---|---|
| H1 | 4,723 | 4,610 |
| H2 | 3,156 | 2,492 |
| H3 | 285 | 277 |
| H6 | 316 | 295 |

| Signal | Horizon (bars) | N | Mean (bp) | SE (bp) | t | 95% CI (bp) |
|---|---|---|---|---|---|---|
| H1 | 1 | 4609 | 0.248 | 0.286 | 0.865 | [-0.31, 0.81] |
| H1 | 3 | 4609 | 0.476 | 0.447 | 1.065 | [-0.43, 1.33] |
| H1 | 6 | 4609 | 1.542 | 0.589 | 2.616 | [0.39, 2.70] |
| H1 | 12 | 4609 | 2.054 | 0.829 | 2.479 | [0.44, 3.68] |
| H1 | 48 | 4609 | 2.224 | 1.445 | 1.540 | [-0.65, 5.02] |
| H2 | 1 | 2492 | 0.117 | 0.575 | 0.204 | [-1.02, 1.23] |
| H2 | 3 | 2492 | 1.025 | 0.810 | 1.266 | [-0.56, 2.61] |
| H2 | 6 | 2492 | 1.396 | 1.029 | 1.357 | [-0.61, 3.42] |
| H2 | 12 | 2492 | 2.055 | 1.338 | 1.536 | [-0.56, 4.68] |
| H2 | 48 | 2492 | 1.422 | 2.472 | 0.575 | [-3.44, 6.25] |
| H3 | 1 | 277 | -0.066 | 1.534 | -0.043 | [-3.12, 2.90] |
| H3 | 3 | 277 | -0.056 | 2.514 | -0.022 | [-4.95, 4.91] |
| H3 | 6 | 277 | -4.413 | 3.261 | -1.353 | [-10.79, 2.00] |
| H3 | 12 | 277 | -9.828 | 4.209 | -2.335 | [-17.98, -1.48] |
| H3 | 48 | 277 | 1.782 | 8.198 | 0.217 | [-13.94, 18.19] |
| H6 | 1 | 295 | 1.770 | 1.695 | 1.044 | [-1.52, 5.13] |
| H6 | 3 | 295 | -1.785 | 2.795 | -0.639 | [-7.53, 3.42] |
| H6 | 6 | 295 | -1.022 | 3.454 | -0.296 | [-8.00, 5.54] |
| H6 | 12 | 295 | 4.213 | 4.800 | 0.878 | [-5.32, 13.49] |
| H6 | 48 | 295 | 8.171 | 7.689 | 1.063 | [-6.79, 23.35] |

## delta50_bar5m: Delta=50 USDT, bar=5m (baseline Delta=25)

| Signal | Raw events | Final (warmup+dedup) |
|---|---|---|
| H1 | 4,723 | 4,610 |
| H2 | 298 | 280 |
| H3 | 45 | 44 |
| H6 | 327 | 298 |

| Signal | Horizon (bars) | N | Mean (bp) | SE (bp) | t | 95% CI (bp) |
|---|---|---|---|---|---|---|
| H1 | 1 | 4609 | 0.248 | 0.289 | 0.860 | [-0.33, 0.80] |
| H1 | 3 | 4609 | 0.477 | 0.452 | 1.056 | [-0.42, 1.35] |
| H1 | 6 | 4609 | 1.543 | 0.596 | 2.588 | [0.36, 2.70] |
| H1 | 12 | 4609 | 2.056 | 0.828 | 2.482 | [0.39, 3.64] |
| H1 | 48 | 4609 | 2.225 | 1.423 | 1.564 | [-0.52, 5.06] |
| H2 | 1 | 280 | 1.320 | 2.170 | 0.609 | [-2.94, 5.56] |
| H2 | 3 | 280 | 0.589 | 2.896 | 0.203 | [-5.13, 6.22] |
| H2 | 6 | 280 | 0.798 | 3.530 | 0.226 | [-6.24, 7.59] |
| H2 | 12 | 280 | 2.127 | 4.469 | 0.476 | [-6.71, 10.80] |
| H2 | 48 | 280 | 0.781 | 6.828 | 0.114 | [-12.48, 14.29] |
| H3 | 1 | 44 | 0.026 | 3.005 | 0.009 | [-5.90, 5.89] |
| H3 | 3 | 44 | 3.444 | 4.967 | 0.693 | [-6.12, 13.35] |
| H3 | 6 | 44 | 8.223 | 7.056 | 1.165 | [-4.93, 22.73] |
| H3 | 12 | 44 | 11.952 | 7.757 | 1.541 | [-2.59, 27.82] |
| H3 | 48 | 44 | 12.018 | 13.589 | 0.884 | [-14.62, 38.65] |
| H6 | 1 | 298 | 0.699 | 2.073 | 0.337 | [-3.53, 4.60] |
| H6 | 3 | 298 | -1.079 | 3.208 | -0.336 | [-7.30, 5.28] |
| H6 | 6 | 298 | -2.547 | 3.647 | -0.698 | [-9.91, 4.38] |
| H6 | 12 | 298 | -2.851 | 6.003 | -0.475 | [-15.37, 8.16] |
| H6 | 48 | 298 | -3.840 | 9.973 | -0.385 | [-23.73, 15.36] |

## bar3m_delta25: bar=3m, Delta=25 USDT (baseline bar=5m)

| Signal | Raw events | Final (warmup+dedup) |
|---|---|---|
| H1 | 4,808 | 4,691 |
| H2 | 1,975 | 1,613 |
| H3 | 189 | 178 |
| H6 | 502 | 446 |

| Signal | Horizon (bars) | N | Mean (bp) | SE (bp) | t | 95% CI (bp) |
|---|---|---|---|---|---|---|
| H1 | 1 | 4691 | 0.300 | 0.217 | 1.386 | [-0.13, 0.72] |
| H1 | 3 | 4691 | 0.637 | 0.379 | 1.678 | [-0.11, 1.37] |
| H1 | 6 | 4691 | 0.568 | 0.481 | 1.183 | [-0.40, 1.49] |
| H1 | 12 | 4691 | 0.839 | 0.650 | 1.292 | [-0.44, 2.11] |
| H1 | 48 | 4691 | 1.258 | 1.157 | 1.088 | [-1.05, 3.49] |
| H2 | 1 | 1613 | 0.461 | 0.589 | 0.782 | [-0.71, 1.60] |
| H2 | 3 | 1613 | 0.626 | 0.941 | 0.666 | [-1.24, 2.45] |
| H2 | 6 | 1613 | 0.628 | 1.096 | 0.573 | [-1.53, 2.77] |
| H2 | 12 | 1613 | 1.080 | 1.461 | 0.740 | [-1.84, 3.89] |
| H2 | 48 | 1613 | 0.117 | 2.522 | 0.047 | [-4.91, 4.97] |
| H3 | 1 | 178 | -3.781 | 1.869 | -2.023 | [-7.47, -0.14] |
| H3 | 3 | 178 | 0.471 | 2.913 | 0.162 | [-5.21, 6.21] |
| H3 | 6 | 178 | -0.037 | 3.894 | -0.009 | [-7.64, 7.62] |
| H3 | 12 | 178 | 8.754 | 5.728 | 1.528 | [-2.33, 20.12] |
| H3 | 48 | 178 | 6.909 | 8.223 | 0.840 | [-9.16, 23.08] |
| H6 | 1 | 446 | -1.219 | 0.978 | -1.246 | [-3.15, 0.68] |
| H6 | 3 | 446 | -2.866 | 2.059 | -1.392 | [-6.98, 1.10] |
| H6 | 6 | 446 | -4.027 | 2.757 | -1.461 | [-9.45, 1.36] |
| H6 | 12 | 446 | -1.838 | 3.349 | -0.549 | [-8.51, 4.62] |
| H6 | 48 | 446 | -2.879 | 5.503 | -0.523 | [-13.66, 7.91] |

## bar15m_delta25: bar=15m, Delta=25 USDT (baseline bar=5m)

| Signal | Raw events | Final (warmup+dedup) |
|---|---|---|
| H1 | 4,514 | 4,436 |
| H2 | 155 | 147 |
| H3 | 6 | 6 |
| H6 | 91 | 90 |

| Signal | Horizon (bars) | N | Mean (bp) | SE (bp) | t | 95% CI (bp) |
|---|---|---|---|---|---|---|
| H1 | 1 | 4435 | 0.410 | 0.428 | 0.958 | [-0.43, 1.25] |
| H1 | 3 | 4435 | 0.268 | 0.716 | 0.374 | [-1.17, 1.64] |
| H1 | 6 | 4435 | 1.099 | 1.017 | 1.081 | [-0.90, 3.08] |
| H1 | 12 | 4435 | 1.095 | 1.321 | 0.829 | [-1.51, 3.67] |
| H1 | 48 | 4435 | 0.224 | 2.524 | 0.089 | [-4.78, 5.12] |
| H2 | 1 | 147 | 2.914 | 3.306 | 0.882 | [-3.60, 9.36] |
| H2 | 3 | 147 | 7.078 | 5.226 | 1.354 | [-3.43, 17.05] |
| H2 | 6 | 147 | -0.579 | 7.384 | -0.078 | [-15.40, 13.54] |
| H2 | 12 | 147 | -17.547 | 10.039 | -1.748 | [-37.98, 1.37] |
| H2 | 48 | 147 | -3.784 | 14.906 | -0.254 | [-33.47, 24.96] |
| H3 | 1 | 6 | -7.111 | 14.035 | -0.507 | [-34.50, 20.51] |
| H3 | 3 | 6 | -37.438 | 17.554 | -2.133 | [-74.20, -5.39] |
| H3 | 6 | 6 | -33.308 | 19.399 | -1.717 | [-72.51, 3.54] |
| H3 | 12 | 6 | -77.646 | 37.229 | -2.086 | [-159.04, -13.10] |
| H3 | 48 | 6 | -90.106 | 54.334 | -1.658 | [-198.46, 14.53] |
| H6 | 1 | 90 | -4.554 | 3.981 | -1.144 | [-12.45, 3.15] |
| H6 | 3 | 90 | -1.779 | 6.192 | -0.287 | [-14.30, 9.98] |
| H6 | 6 | 90 | -7.150 | 7.040 | -1.016 | [-21.40, 6.20] |
| H6 | 12 | 90 | -10.072 | 9.633 | -1.046 | [-29.33, 8.43] |
| H6 | 48 | 90 | -9.918 | 15.761 | -0.629 | [-41.06, 20.72] |
