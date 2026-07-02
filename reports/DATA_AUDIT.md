# Phase 0 — Data Audit

Status: complete. No forward returns or PnL have been computed. This report only
covers data availability, schema, and size/feasibility — the pre-registration
gate (Phase 1) has not yet been crossed.

Generated: 2026-07-02. Source: `runners/phase0_data_audit.py` plus ad hoc
`curl`/`polars` probes against `https://data.binance.vision`.

## 1. Method

For each of the four datasets (aggTrades, fundingRate, klines, bookDepth) we
downloaded one representative sample for BTCUSDT, verified the accompanying
`.CHECKSUM` (sha256), extracted, and inspected schema/dtypes/header behavior
with polars. We additionally pulled a sample from the *start* of the study
window (2022-07-01), the *end* of the study window (2026-06-25), and did a
binary search to pin down when `bookDepth` archive coverage begins — because
the spec explicitly warns that header presence and timestamp units are not
guaranteed stable across eras.

Sample files live under `data/sample/` (gitignored; not committed).

## 2. Checksum verification

All 4 primary samples passed sha256 verification against their `.CHECKSUM` file:

| File | Result |
|---|---|
| `BTCUSDT-aggTrades-2025-03-17.zip` | OK |
| `BTCUSDT-1m-2025-03-17.zip` | OK |
| `BTCUSDT-bookDepth-2025-03-17.zip` | OK |
| `BTCUSDT-fundingRate-2025-03.zip` | OK |

## 3. Schemas (recent era, 2025-03-17 / 2025-03)

**aggTrades** — `agg_trade_id:Int64, price:Float64, quantity:Float64, first_trade_id:Int64, last_trade_id:Int64, transact_time:Int64, is_buyer_maker:Boolean`. 1,374,312 rows for one day. `is_buyer_maker` split ~50.6%/49.4% true/false, consistent with the spec's convention (`isBuyerMaker=true` -> SELL aggressor).

**klines (1m)** — `open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore`. Exactly 1,440 rows (one per minute of the day) — clean, no gaps in the sample day.

**bookDepth** — `timestamp:String (not epoch — "YYYY-MM-DD HH:MM:SS"), percentage:Int64, depth:Float64, notional:Float64`. 10 fixed percentage bands (-5,-4,-3,-2,-1,1,2,3,4,5) x 2,811 distinct snapshot timestamps = 28,110 rows/day (snapshot cadence ~30.7s, not fixed-interval — must not assume evenly spaced when parsing). Confirmed descriptive-only per spec; not used for confirmatory signals.

**fundingRate** — `calc_time:Int64, funding_interval_hours:Int64, last_funding_rate:Float64`. 93 rows for March 2025 (31 days x 3 funding events/day), `funding_interval_hours` uniformly 8.

## 4. Confirmed quirks (as warned in spec — now empirically pinned down)

- **Header row presence is inconsistent by era.** 2025-03-17 aggTrades/klines files have a header row. 2022-07-01 (start of study period) aggTrades/klines files have **no header row** — same column order, confirmed by manually assigning the recent-era column names and checking the values parse correctly (prices, boolean flag, monotonic ms timestamps all sane). ETL must sniff the first field of the first line (numeric vs. alphabetic) per file rather than assuming.
- **Timestamp units are stable at milliseconds for futures/um across the entire study window.** Checked three points: 2022-07-01 (`1656633600033` ms), 2025-03-17 (`1742169600044` ms), 2026-06-25 (`1782345600095` ms). All 13-digit ms-epoch, all correctly decode to the expected UTC date. No ms->us switch was observed on this endpoint (unlike Binance spot market data, which did switch some archives to microseconds in 2025) — but per spec we still sniff digit-count per file defensively rather than hardcoding.
- **`bookDepth` archive coverage does not extend back to the study start.** Binary search: 404 (`NoSuchKey`) for BTCUSDT on 2022-07-01, 2022-08-01, 2022-10-01, 2022-12-01, 2022-12-15, 2022-12-20, 2022-12-25; HTTP 200 from 2023-01-01 onward. So `bookDepth` is only available for roughly the last ~42 of the 48 study months. This does not affect any confirmatory test (bookDepth is descriptive-context-only per spec, H4/H5 are already DATA-BLOCKED for the separate reason of no historical full-depth L2), but it means any descriptive bookDepth charts in the final report will be captioned as covering 2023-01 onward, not the full period.

## 5. QA reconciliation (sanity-checked now, will run at full scale in Phase 2)

On the 2025-03-17 BTCUSDT sample:
- aggTrades summed `quantity` = 182,662.0630; klines summed `volume` = 182,662.0820. Difference = **0.0000%** (well inside the 0.5% gate).
- `transact_time` is non-decreasing across all 1,374,312 rows in the day (monotonicity holds).
- `agg_trade_id` is fully contiguous (0 gaps) within the day.

This is one day, not a substitute for the full-period QA suite required in Phase 2, but it confirms the reconciliation approach and gate threshold are workable on real data.

## 6. Size / feasibility estimate for the full 48-month period (2022-07-01 to 2026-06-30)

Monthly `aggTrades` zip size is volume-dependent, not constant — sampled 16 months for BTCUSDT and 14 for ETHUSDT spread across the period (quarterly-ish cadence plus period start/end) to get a representative average rather than assuming a single month is typical:

| Symbol | Months sampled | Min | Max | Mean |
|---|---|---|---|---|
| BTCUSDT | 16 | 330 MB (2023-07) | 829 MB (2022-07) | ~543 MB/month |
| ETHUSDT | 14 | 237 MB (2023-07) | 1,039 MB (2025-10) | ~565 MB/month |

Extrapolated to 48 months:

| Dataset | BTCUSDT | ETHUSDT | Total |
|---|---|---|---|
| aggTrades (monthly) | ~26.1 GB | ~27.1 GB | **~53.2 GB** |
| klines 1m (monthly, ~2 MB/mo, low variance) | ~0.1 GB | ~0.1 GB | ~0.2 GB |
| fundingRate (monthly, <1 KB/mo) | negligible | negligible | negligible |
| bookDepth (daily, BTC only, ~457 KB/day, coverage from 2023-01) | ~0.6 GB | n/a (descriptive, BTC-only) | ~0.6 GB |
| **Total network egress (compressed zips)** | | | **~54 GB** |

Per the ETL plan (§2.4 of the brief), raw zips are processed month-by-month and can be deleted after parquet persistence, keeping only the sha256 in `data/manifest.json`. So **peak local disk usage is much lower than 54 GB** — roughly one month's raw files (<1 GB) plus the growing parquet bar store. The parquet store itself (5-minute footprint bars, not raw ticks) will be a small fraction of the raw size — rough order-of-magnitude estimate is low hundreds of MB to low single-digit GB for the full 48-month x 2-symbol footprint bar table, not tens of GB.

**Local disk available:** 984 GB free on the working drive (`C:`). Not a constraint at any estimate in this table.

**Conclusion: full 48-month, 2-symbol period is feasible as originally scoped in the brief. No window shortening is needed at Phase 1.**

## 7. Open items carried into Phase 1 (pre-registration)

- Header-sniffing and timestamp-unit-sniffing logic (per-file, not per-dataset-assumed) must be implemented in `src/orderflow/etl.py` before any ingestion, per the confirmed quirks above.
- `bookDepth` descriptive charts will be scoped to 2023-01-01 onward and captioned accordingly.
- No other deviations from the brief's data plan were found necessary.
