# BTC Event Counts by Calendar Half-Year

Runner-generated (runners/phase3_year_table.py). Do not hand-edit.

Full deduped BTC sample (warm-up + dedup + quarantine filter applied; both IS and OOS periods included) - counts only. No forward returns computed for OOS events; this table does not touch the OOS-reservation rule, it only documents where detected events fall in calendar time.

| Signal | 2022H2 | 2023H1 | 2023H2 | 2024H1 | 2024H2 | 2025H1 | 2025H2 | 2026H1 | Total | IS share |
|---|---|---|---|---|---|---|---|---|---|---|
| H1 | 799 | 903 | 919 | 969 | 1020 | 1136 | 1008 | 1031 | 7785 | 59.2% |
| H2 | 24 | 46 | 81 | 256 | 376 | 519 | 574 | 489 | 2365 | 33.1% |
| H3 | 4 | 3 | 3 | 18 | 34 | 55 | 95 | 69 | 281 | 22.1% |
| H6 | 56 | 35 | 49 | 62 | 84 | 139 | 177 | 128 | 730 | 39.2% |

Calendar-time IS share (2022H2-2024H2 out of the full 2022H2-2026H1 sample): 62.6%. Compare each signal's IS share above against this 62.6% baseline to see regime skew - e.g. a signal materially above baseline fires disproportionately in the discovery period, below baseline disproportionately post-discovery.
