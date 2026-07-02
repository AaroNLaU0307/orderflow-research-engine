# Phase 2 QA Summary

Runner-generated (runners/phase2_qa.py). Do not hand-edit.

## Manifest completeness

- Manifest entries: 1582
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

- Days with both aggTrades and klines data: 1431
- Days with aggTrades only (klines archive not yet published for that day): 30
  - ['2026-06-01', '2026-06-02', '2026-06-03', '2026-06-04', '2026-06-05', '2026-06-06', '2026-06-07', '2026-06-08', '2026-06-09', '2026-06-10', '2026-06-11', '2026-06-12', '2026-06-13', '2026-06-14', '2026-06-15', '2026-06-16', '2026-06-17', '2026-06-18', '2026-06-19', '2026-06-20', '2026-06-21', '2026-06-22', '2026-06-23', '2026-06-24', '2026-06-25', '2026-06-26', '2026-06-27', '2026-06-28', '2026-06-29', '2026-06-30']
- Days with klines only (aggTrades missing - should be 0 after backfill): 0
- Breach days (diff >= 0.5%, among days with both sources): 5
- Max diff: 13.6446%, mean diff: 0.0158%
- Worst 5 breach days:
  - 2023-11-10: aggTrades=299,373.89, klines=263,429.96, diff=13.6446%
  - 2024-10-28: aggTrades=264,558.49, klines=256,128.62, diff=3.2913%
  - 2025-01-14: aggTrades=212,769.12, klines=209,383.35, diff=1.6170%
  - 2022-09-06: aggTrades=931,039.05, klines=945,489.14, diff=1.5283%
  - 2025-01-29: aggTrades=169,989.86, klines=168,870.64, diff=0.6628%
- Gate: FAIL

### ETHUSDT

- Days with both aggTrades and klines data: 1431
- Days with aggTrades only (klines archive not yet published for that day): 30
  - ['2026-06-01', '2026-06-02', '2026-06-03', '2026-06-04', '2026-06-05', '2026-06-06', '2026-06-07', '2026-06-08', '2026-06-09', '2026-06-10', '2026-06-11', '2026-06-12', '2026-06-13', '2026-06-14', '2026-06-15', '2026-06-16', '2026-06-17', '2026-06-18', '2026-06-19', '2026-06-20', '2026-06-21', '2026-06-22', '2026-06-23', '2026-06-24', '2026-06-25', '2026-06-26', '2026-06-27', '2026-06-28', '2026-06-29', '2026-06-30']
- Days with klines only (aggTrades missing - should be 0 after backfill): 0
- Breach days (diff >= 0.5%, among days with both sources): 14
- Max diff: 4.5110%, mean diff: 0.0127%
- Worst 5 breach days:
  - 2022-09-06: aggTrades=10,576,846.12, klines=11,076,502.23, diff=4.5110%
  - 2024-10-28: aggTrades=2,973,908.17, klines=2,899,028.95, diff=2.5829%
  - 2025-01-14: aggTrades=2,711,818.43, klines=2,669,270.39, diff=1.5940%
  - 2023-05-04: aggTrades=2,618,581.00, klines=2,639,262.75, diff=0.7836%
  - 2023-05-07: aggTrades=3,174,118.00, klines=3,198,475.67, diff=0.7615%
- Gate: FAIL

## Monthly-archive-gap backfill (daily-archive splice)

- Months repaired via daily-archive backfill: 10
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
- Months where daily archive ALSO lacked the data (unrecoverable): 0

Provenance: data/manifest.json records the sha256 of every individual file ingested, including both the monthly zip and any daily backfill zips for a repaired month (so a repaired month has both its monthly-zip manifest entry AND separate entries for each spliced daily zip). data/qa_backfill_log.jsonl is the authoritative per-month record of which months were repaired and from which specific days.

## Bar-store sanity counts

- BTCUSDT: 420,768 bars (expected 420,768 = 1461 days x 288) -> PASS; zero-trade bars: 9; range 2022-07-01 00:00:00 to 2026-06-30 23:55:00
- ETHUSDT: 420,768 bars (expected 420,768 = 1461 days x 288) -> PASS; zero-trade bars: 10; range 2022-07-01 00:00:00 to 2026-06-30 23:55:00

## Raw zip/csv retention status

- Total remaining under data/raw/: 408.3 MB
  - .csv: 168 files, 318.4 MB
  - .zip: 168 files, 89.7 MB
  - .CHECKSUM: 1577 files, 0.2 MB

Raw aggTrades/klines/fundingRate .zip and extracted .csv files are deleted immediately after each month is staged to parquet (per docs/BRIEF.md section 2.4); only their tiny .CHECKSUM sidecar files remain (a few hundred bytes each). bookDepth raw files remain because 157 daily bookDepth files failed to parse (see note below) and the exception occurs before the cleanup step - this is descriptive-context data only (never a signal input) and does not affect Phase 3. Consequence: the 5-minute/Delta=25(BTC)/Delta=1(ETH) parquet bar store is the only persisted artifact: Delta=50(BTC) and 15m-bar sensitivity configs can be re-derived from it by aggregation, but Delta=10(BTC) and 3m-bar configs would require re-downloading raw aggTrades, since the 5-minute bars are already a coarser aggregation than a 3-minute bar would need. No re-download is being done now; this is deferred per instruction.

Separately noted (not part of the gates above, does not affect any confirmatory signal): 157 of 1275 daily BTCUSDT bookDepth files failed to parse (`could not parse '-5.00' as dtype i64` on the percentage column) - some bookDepth archive days format percentage as a float string ('-5.00') rather than an integer string ('-5'), a header/format inconsistency in the same family as the header-presence and timestamp-unit quirks already documented in the prereg. Since bookDepth is descriptive-only per preregistration section 3, this is not a Phase 3 blocker; flagged for a follow-up fix before any bookDepth descriptive exhibit is produced.
