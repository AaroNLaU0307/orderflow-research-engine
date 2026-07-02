# Phase 2 QA Summary

Runner-generated (runners/phase2_qa.py). Do not hand-edit.

## FINAL GATE: PASS-WITH-EXCEPTIONS

The reconciliation check's purpose is to validate aggTrades, the only dataset confirmatory statistics touch; klines is validation-only. A breach day is not a blocking failure if it is classified as KLINES_HOLE (aggTrades independently verified complete) or AGG_PARTIAL_GAP (repaired) or AGG_PARTIAL_GAP_UPSTREAM (quarantined). See the classification section below for every breach day's verdict. PASS-WITH-EXCEPTIONS requires zero UNEXPLAINED days and zero checksum failures and exact bar-store counts for both symbols.

## Manifest completeness

- Manifest entries: 1652
- Expected monthly files (symbols x datasets x months): 288
- Missing or unrecorded: 0
- Checksum failures: 0

## Inline gap / monotonicity scan (per ingested month)

- Months logged: 96
- Anomalous months: 11
  - BTCUSDT 2022-08: monotonic=True, missing_days=[28, 29, 30], agg_id_gaps=1
  - BTCUSDT 2022-09: monotonic=True, missing_days=[1, 10], agg_id_gaps=4316654
  - BTCUSDT 2022-10: monotonic=True, missing_days=[29], agg_id_gaps=1
  - BTCUSDT 2022-11: monotonic=True, missing_days=[7, 14], agg_id_gaps=2
  - BTCUSDT 2023-05: monotonic=False, missing_days=[9], agg_id_gaps=2714401
  - BTCUSDT 2023-10: monotonic=False, missing_days=[], agg_id_gaps=7976734
  - ETHUSDT 2022-08: monotonic=True, missing_days=[28, 29, 30], agg_id_gaps=1
  - ETHUSDT 2022-09: monotonic=True, missing_days=[1], agg_id_gaps=13391218
  - ETHUSDT 2022-10: monotonic=True, missing_days=[29], agg_id_gaps=1
  - ETHUSDT 2022-11: monotonic=True, missing_days=[7, 14], agg_id_gaps=2
  - ETHUSDT 2023-05: monotonic=True, missing_days=[10], agg_id_gaps=1

## Daily aggTrades vs klines volume reconciliation (gate: <0.5%, per calendar day)

### BTCUSDT

- Days with both aggTrades and klines data: 1461
- Days with aggTrades only (klines archive not yet published for that day): 0
- Days with klines only (aggTrades missing - should be 0 after backfill): 0
- Breach days (diff >= 0.5%, among days with both sources): 5
- Max diff: 13.6446%, mean diff: 0.0164%
- Worst 5 breach days:
  - 2023-11-10: aggTrades=299,373.89, klines=263,429.96, diff=13.6446%
  - 2024-10-28: aggTrades=264,558.49, klines=256,128.62, diff=3.2913%
  - 2025-01-14: aggTrades=212,769.12, klines=209,383.35, diff=1.6170%
  - 2022-09-06: aggTrades=931,039.05, klines=945,489.14, diff=1.5283%
  - 2025-01-29: aggTrades=169,989.86, klines=168,870.64, diff=0.6628%
- Raw gate (breach count only, not classification-aware): raw FAIL - see breach classification below for per-day verdicts

### ETHUSDT

- Days with both aggTrades and klines data: 1461
- Days with aggTrades only (klines archive not yet published for that day): 0
- Days with klines only (aggTrades missing - should be 0 after backfill): 0
- Breach days (diff >= 0.5%, among days with both sources): 4
- Max diff: 4.5110%, mean diff: 0.0086%
- Worst 5 breach days:
  - 2022-09-06: aggTrades=10,576,846.12, klines=11,076,502.23, diff=4.5110%
  - 2024-10-28: aggTrades=2,973,908.17, klines=2,899,028.95, diff=2.5829%
  - 2025-01-14: aggTrades=2,711,818.43, klines=2,669,270.39, diff=1.5940%
  - 2025-01-29: aggTrades=2,863,466.61, klines=2,845,655.83, diff=0.6259%
- Raw gate (breach count only, not classification-aware): raw FAIL - see breach classification below for per-day verdicts

## Monthly-archive-gap backfill (daily-archive splice)

- Months repaired via daily-archive backfill: 11
  - BTCUSDT 2022-08: missing_days=[28, 29, 30] -> recovered from daily archive
  - BTCUSDT 2022-09: missing_days=[1, 10] -> recovered from daily archive
  - BTCUSDT 2022-10: missing_days=[29] -> recovered from daily archive
  - BTCUSDT 2022-11: missing_days=[7, 14] -> recovered from daily archive
  - BTCUSDT 2023-05: missing_days=[9] -> recovered from daily archive
  - ETHUSDT 2022-08: missing_days=[28, 29, 30] -> recovered from daily archive
  - ETHUSDT 2022-09: missing_days=[1] -> recovered from daily archive
  - ETHUSDT 2022-10: missing_days=[29] -> recovered from daily archive
  - ETHUSDT 2022-11: missing_days=[7, 14] -> recovered from daily archive
  - ETHUSDT 2023-05: missing_days=[10] -> recovered from daily archive
  - ETHUSDT 2023-05: missing_days=[1, 2, 3, 4, 5, 7, 8, 9, 11, 13] -> recovered from daily archive
- Months where daily archive ALSO lacked the data (unrecoverable): 0

Provenance: data/manifest.json records the sha256 of every individual file ingested, including both the monthly zip and any daily backfill zips for a repaired month (so a repaired month has both its monthly-zip manifest entry AND separate entries for each spliced daily zip). data/qa_backfill_log.jsonl is the authoritative per-month record of which months were repaired and from which specific days.

## Breach-day classification (KLINES_HOLE / AGG_PARTIAL_GAP / AGG_PARTIAL_GAP_UPSTREAM / UNEXPLAINED)

Every reconciliation breach day is classified against the daily-archive ground truth. KLINES_HOLE: aggTrades independently verified complete (matches its own daily archive exactly, contiguous agg_trade_id sequence) and the diff is magnitude-weighted-explained by zero-volume klines minutes - exonerates aggTrades, the only dataset confirmatory statistics touch. AGG_PARTIAL_GAP: the monthly aggTrades rollup was short vs. the daily archive for that day - repaired by splicing in the daily archive's data (see backfill section above). AGG_PARTIAL_GAP_UPSTREAM: the daily archive has the same hole as the monthly one (not repairable by re-splicing) - handled via data/quarantine_windows.json (bars overlapping the window are excluded from event formation; forward returns spanning it are nulled).

| Symbol | Date | Direction | Diff% | Zero-vol klines min | Daily archive max ID jump | Daily archive max ts gap (min) | Verdict |
|---|---|---|---|---|---|---|---|
| BTCUSDT | 2022-09-06 | agg<k | -1.5283 | 0 | 31646 | 6.35 | AGG_PARTIAL_GAP_UPSTREAM |
| BTCUSDT | 2023-11-10 | agg>k | 13.6446 | 99 | 1 | 0.09 | KLINES_HOLE |
| BTCUSDT | 2024-10-28 | agg>k | 3.2913 | 89 | 1 | 14.51 | KLINES_HOLE |
| BTCUSDT | 2025-01-14 | agg>k | 1.6170 | 2 | 1 | 0.09 | KLINES_HOLE |
| BTCUSDT | 2025-01-29 | agg>k | 0.6628 | 17 | 1 | 0.09 | KLINES_HOLE |
| ETHUSDT | 2022-09-06 | agg<k | -4.5110 | 0 | 94136 | 11.39 | AGG_PARTIAL_GAP_UPSTREAM |
| ETHUSDT | 2023-05-01 | agg<k | -0.6454 | 0 | 1 | 0.08 | AGG_PARTIAL_GAP |
| ETHUSDT | 2023-05-02 | agg<k | -0.6616 | 0 | 1 | 0.08 | AGG_PARTIAL_GAP |
| ETHUSDT | 2023-05-03 | agg<k | -0.6424 | 0 | 1 | 0.09 | AGG_PARTIAL_GAP |
| ETHUSDT | 2023-05-04 | agg<k | -0.7836 | 0 | 1 | 0.09 | AGG_PARTIAL_GAP |
| ETHUSDT | 2023-05-05 | agg<k | -0.5162 | 0 | 1 | 0.11 | AGG_PARTIAL_GAP |
| ETHUSDT | 2023-05-07 | agg<k | -0.7615 | 0 | 1 | 0.1 | AGG_PARTIAL_GAP |
| ETHUSDT | 2023-05-08 | agg<k | -0.5550 | 0 | 1 | 0.06 | AGG_PARTIAL_GAP |
| ETHUSDT | 2023-05-09 | agg<k | -0.7231 | 0 | 1 | 0.1 | AGG_PARTIAL_GAP |
| ETHUSDT | 2023-05-11 | agg<k | -0.5871 | 0 | 1 | 0.1 | AGG_PARTIAL_GAP |
| ETHUSDT | 2023-05-13 | agg<k | -0.7290 | 0 | 1 | 0.11 | AGG_PARTIAL_GAP |
| ETHUSDT | 2024-10-28 | agg>k | 2.5829 | 89 | 1 | 14.51 | KLINES_HOLE |
| ETHUSDT | 2025-01-14 | agg>k | 1.5940 | 3 | 1 | 0.08 | KLINES_HOLE |
| ETHUSDT | 2025-01-29 | agg>k | 0.6259 | 17 | 1 | 0.09 | KLINES_HOLE |

- Totals: KLINES_HOLE=7 (no action, aggTrades exonerated), AGG_PARTIAL_GAP=10 (repaired by splice, see above), AGG_PARTIAL_GAP_UPSTREAM=2 (quarantined, see data/quarantine_windows.json), UNEXPLAINED=0

## Bar-store sanity counts

- BTCUSDT: 420,768 bars (expected 420,768 = 1461 days x 288) -> PASS; zero-trade bars: 9; range 2022-07-01 00:00:00 to 2026-06-30 23:55:00
  Zero-trade bar timestamps (likely exchange maintenance/outage windows):
    - 2022-09-06 17:15:00
    - 2023-09-12 08:35:00
    - 2023-09-12 08:40:00
    - 2023-09-12 08:45:00
    - 2024-10-28 16:25:00
    - 2024-10-28 16:30:00
    - 2025-08-29 06:20:00
    - 2025-08-29 06:25:00
    - 2025-08-29 06:30:00
- ETHUSDT: 420,768 bars (expected 420,768 = 1461 days x 288) -> PASS; zero-trade bars: 10; range 2022-07-01 00:00:00 to 2026-06-30 23:55:00
  Zero-trade bar timestamps (likely exchange maintenance/outage windows):
    - 2022-09-06 17:10:00
    - 2022-09-06 17:15:00
    - 2023-09-12 08:35:00
    - 2023-09-12 08:40:00
    - 2023-09-12 08:45:00
    - 2024-10-28 16:25:00
    - 2024-10-28 16:30:00
    - 2025-08-29 06:20:00
    - 2025-08-29 06:25:00
    - 2025-08-29 06:30:00

## Raw zip/csv retention status

- Total remaining under data/raw/: 716.3 MB
  - .csv: 170 files, 573.4 MB
  - .zip: 170 files, 142.7 MB
  - .CHECKSUM: 1666 files, 0.2 MB

Raw aggTrades/klines/fundingRate .zip and extracted .csv files are deleted immediately after each month is staged to parquet (per docs/BRIEF.md section 2.4); only their tiny .CHECKSUM sidecar files remain (a few hundred bytes each). bookDepth raw files remain because 157 daily bookDepth files failed to parse (see note below) and the exception occurs before the cleanup step - this is descriptive-context data only (never a signal input) and does not affect Phase 3. Separately, all 48 months of BTCUSDT monthly aggTrades zips have been re-downloaded and retained under data/raw_retained/BTCUSDT/aggTrades/ (download-only, not parsed) so the Delta=10 and 3-minute-bar sensitivity configs (preregistration section 8) do not require a second download later - Delta=50 and 15m-bar configs are still derivable from the existing 5m/Delta=25 parquet store by aggregation. Staging/computation of the sensitivity grid itself remains deferred until after main results review, per instruction.

Separately noted (not part of the gates above, does not affect any confirmatory signal): 157 of 1275 daily BTCUSDT bookDepth files failed to parse (`could not parse '-5.00' as dtype i64` on the percentage column) - some bookDepth archive days format percentage as a float string ('-5.00') rather than an integer string ('-5'), a header/format inconsistency in the same family as the header-presence and timestamp-unit quirks already documented in the prereg. Since bookDepth is descriptive-only per preregistration section 3, this is not a Phase 3 blocker; flagged for a follow-up fix before any bookDepth descriptive exhibit is produced.
