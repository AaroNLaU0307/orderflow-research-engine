Original project brief, agent-executed under human-gated review at every phase; see the commit history for the review cadence.

# Order Flow Research Engine v1 — BTCUSDT Perpetual Futures
You are building a confirmatory quantitative research project, not a trading bot. The deliverable is a GitHub-ready research repository (`orderflow-research-engine`) that tests whether classic order-flow signals contain exploitable information in Binance BTCUSDT perpetual futures, under a falsification-first protocol. A clean negative result is a fully acceptable — and publishable — outcome. Do not optimize toward positive results.
---
## 0. Non-negotiable research principles
These override everything else in this document.
1. **Pre-registration before PnL.** All hypotheses, event definitions, parameters, horizons, statistical gates, and cost models are locked in `preregistration/PREREGISTRATION.md` and committed BEFORE any code touches forward returns or PnL. After sign-off, no definition changes. Any unavoidable deviation goes in `preregistration/DEVIATIONS.md` with justification and is flagged in the final report.
2. **No parameter search.** All parameters come from practitioner/academic convention, stated with rationale. Sensitivity grids are reported as robustness (plateau evidence), never used for selection.
3. **Look-ahead prevention.** Every signal must pass a truncation-invariance unit test: recompute all events on data truncated at time T; the set of events with timestamp < T must be bit-identical to the full-sample run. Signals use only completed bars; execution is next-bar-open.
4. **Full cost modeling.** Taker fees, slippage, and funding are in every net number. Never report gross-only conclusions.
5. **Multiplicity is accounted for.** BH-FDR across all tested cells; Deflated Sharpe Ratio with an explicitly declared total trial count for any promoted strategy.
6. **Honest reporting.** If a signal fails, the report says it failed and why. No silent re-runs, no cherry-picked windows.
## 1. Git / repo rules (permanent, from prior projects)
- Git author email: `189274301+AaroNLaU0307@users.noreply.github.com` — set per-repo with `git config user.email` before the first commit. The real email must never appear in any commit.
- Commit messages via `git commit -F <ascii-file>` only (stdin pipes have introduced BOM corruption before). Message files must be pure ASCII.
- **Never `git push` without the user's explicit confirmation in chat.**
- Runner-generated report snapshots under `reports/` are immutable — never hand-edit them; they must remain bit-identical to their source CSV/JSON outputs. Hand-written files (`README.md`, prereg docs) are editable.
- Repo name: `orderflow-research-engine`. Initialize locally; remote setup and push only after user approval.
## 2. Data plan
### 2.1 Sources (all free, official Binance archive)
Base URL pattern: `https://data.binance.vision/data/futures/um/{monthly|daily}/{dataset}/{SYMBOL}/...`
| Dataset | Use | Notes |
|---|---|---|
| `aggTrades` (monthly zips) | Primary. Footprints, delta, all four v1 signals | Columns: aggTradeId, price, qty, firstId, lastId, timestamp, isBuyerMaker. `isBuyerMaker=true` ⇒ SELL aggressor. |
| `fundingRate` (monthly) | Funding PnL for positions crossing 00:00/08:00/16:00 UTC | |
| `klines` 1m (monthly) | QA reconciliation only (volume cross-check vs aggTrades) | |
| `bookDepth` (daily) | Descriptive context only — aggregate depth at ±1/2/3/5/10% bands. NOT usable for wall/pull signals. | Do not build signals from this. |
Every zip has a `.CHECKSUM` (sha256) — verify before ingest; log failures.
### 2.2 Known data quirks (handle defensively, add unit tests)
- Header row presence is inconsistent across archive periods — sniff first line per file, never assume.
- Timestamp units may vary (ms vs µs across datasets/eras) — sniff magnitude, normalize to UTC nanoseconds internally.
- Files can be re-published by Binance (see their updates changelog) — record the sha256 of every ingested file in `data/manifest.json` for reproducibility.
- Gap scan: assert no missing days; assert intra-day monotonic timestamps; log and quarantine anomalies.
- QA reconciliation: daily base-asset volume from aggTrades must match 1m-klines daily volume within 0.5%; investigate any breach.
### 2.3 Sample period and universes
- **Primary universe:** BTCUSDT USD-M perpetual.
- **Replication universe (pre-registered):** ETHUSDT perp — pipeline runs on it ONLY for signals promoted on BTC, as out-of-family replication.
- **Period:** 2022-07-01 → 2026-06-30 (48 months).
  - In-sample (discovery): 2022-07-01 → 2024-12-31.
  - Out-of-sample (confirmation): 2025-01-01 → 2026-06-30.
- If disk/compute forces a shorter window, the decision is made and documented at Phase 1 (prereg), never after seeing results. Estimate raw compressed volume in Phase 0 first.
### 2.4 ETL
- Python 3.11+, `polars` (lazy/streaming) + `pyarrow`. Month-by-month streaming: download → checksum → parse → build 5-minute footprint bars → persist parquet → optionally delete raw zip (keep manifest hash).
- Persisted schema per bar: `bar_ts` (UTC, bar open), per-price-bucket rows: `bucket_px, buy_vol, sell_vol, trade_count`, plus bar aggregates: OHLC, total volume, total delta, cumulative delta.
- Everything downstream reads only the parquet bar store. Raw ticks are touched exactly once.
## 3. Signal definitions (v1 scope)
All signals are computed on **completed 5-minute UTC-aligned time bars** with footprint price buckets of **25 USDT for BTC** (~2–3 bp of price; ETH: 1 USDT). Sensitivity grid (report-only): bucket ×0.5 / ×2, bar 3m / 15m.
Delta of a bucket = buy_vol − sell_vol (buy = aggressor buy, i.e., isBuyerMaker=false).
### Data-blocked (document, do not test)
- **H4 Liquidity wall** and **H5 Liquidity pull** require historical full-depth L2, which is not freely available (official archive has none; third-party vendors are paid; Tardis free samples cover only the 1st of each month — insufficient for confirmatory inference). Mark both as `DATA-BLOCKED` in the prereg with this justification. Deliver `collector/depth_recorder.py` (websocket `@depth@100ms` diff recorder + snapshot sync, parquet output, restart-safe) so live L2 collection can start now for a future v1.5. Do NOT run confirmatory tests on Tardis samples.
### Testable in v1 (exact operational definitions go in prereg; defaults below are the pre-registered convention values)
**H1 — Delta divergence (bearish case; bullish is mirrored).**
Event at bar t if: close_t is the maximum close over the trailing 24 bars (2h) AND the 24-bar rolling sum of delta at t is below its value at the previous 24-bar price high by more than 0.5σ (σ = trailing 30-day std of the 24-bar delta sum). Direction: short. Magnitude: the delta shortfall z-score.
**H2 — Absorption (bullish case at lows; mirrored at highs).**
Event at bar t if there exists a price bucket p in the bottom 20% of bar t's range where: bucket volume ≥ 4× the median bucket volume of the trailing 96 bars, AND sell_vol(p) ≥ 70% of bucket volume (aggressive selling), AND close_t ≥ p + 1 bucket (price refused to break). Direction: long. Magnitude: bucket volume multiple.
**H3 — Stacked imbalance (bullish case; mirrored).**
Diagonal footprint imbalance, ATAS/Orderflows convention: buy_vol at bucket p vs sell_vol at bucket p−1; imbalance if ratio ≥ 3.0 with opposing side ≥ trailing-96-bar P25 bucket volume (anti-div-by-tiny filter). Event if ≥ 3 consecutive buckets show same-direction imbalance within one bar. Direction: with the imbalance. Magnitude: stack length × mean ratio.
**H6 — Exhaustion (bearish case at highs; mirrored).**
Event at bar t if: bar volume ≥ 95th percentile of trailing 2016 bars (1 week), AND close_t is a 24-bar high, AND the top 2 price buckets of the bar have negative combined delta (aggressive buying dries up / sellers hit into the extreme). Direction: short (reversal). Magnitude: volume percentile × |extreme-bucket delta|.
**Event hygiene (all signals):** same-signal-same-direction events within 6 bars are deduplicated (keep first). Events in the first 2016 bars of the sample (warm-up) are discarded.
## 4. Statistical plan
### 4.1 Event study (gross information content)
- Forward signed log return per event: r(h) = direction × log(open_{t+1+h} / open_{t+1}), h ∈ {1, 3, 6, 12, 48} bars = {5m, 15m, 30m, 1h, 4h}. Entry reference = next bar open (execution-realistic, no same-bar leakage).
- Cells: 4 signals × 5 horizons = 20 (BTC in-sample). Per cell: mean signed return, t-stat, and a **stationary block bootstrap** p-value (mean block length = 1 day of bars, 10,000 resamples) to respect overlap/serial dependence.
- Also compute Spearman IC between event magnitude and forward signed return per signal×horizon (block-bootstrap CI) — informational, not gating.
- **Multiplicity:** BH-FDR at q = 0.10 across all 20 cells.
- **Consistency check:** per-calendar-year mean signed return sign agreement (report; a signal flipping sign across years is flagged even if pooled-significant).
### 4.2 Promotion gates (pre-registered, all must hold in-sample)
A signal is promoted to backtest iff:
1. ≥ 300 deduplicated in-sample events;
2. BH-FDR significant (q < 0.10) at ≥ 2 horizons, at least one of which is ≥ 30m;
3. **Economic materiality:** mean signed gross return at the best FDR-significant horizon ≥ 1.5× round-trip cost (see §4.3) — i.e., ≥ ~18 bp;
4. Sign consistency in ≥ 2 of the ≥2.5 in-sample calendar years.
Signals failing gates are reported as falsified (distinguish: no-information vs information-but-uneconomic). Do not proceed to backtest for them.
### 4.3 Cost model (pre-registered)
- Taker fee 5.0 bp per side (Binance USD-M VIP0, no BNB discount — conservative).
- Slippage: half-spread (1 tick = 0.1 USDT, negligible for BTC) + 1.0 bp impact buffer per side.
- Round trip ≈ 12 bp. State this prominently; it is the null-killer for short-horizon order flow.
- Funding: apply the historical funding rate to any position open across a funding timestamp.
### 4.4 Confirmatory backtest (promoted signals only)
- Rule: enter at next bar open after event, exit at the fixed promoted horizon; max 1 concurrent position per signal (overlapping events skipped — pre-registered); constant notional.
- Net PnL includes fees, slippage, funding.
- Evaluation: walk-forward over the full period with **purge + embargo** (purge = promoted horizon length; embargo = 1 day) between any IS-derived quantile thresholds (e.g., rolling volume percentiles) and evaluation windows; since parameters are convention-fixed, the IS→OOS split is the primary confirmation: the OOS (2025-01→2026-06) net result must independently show a positive bootstrap 95% CI lower bound on the per-trade signed net return, and OOS net Sharpe reported with CI.
- **Deflated Sharpe Ratio:** trial count N declared explicitly = all cells examined in the entire study (20 BTC cells + sensitivity-grid cells + ETH replication cells) — enumerate the number in the report; also report PSR.
- Bootstrap CI on annualized net Sharpe (stationary block bootstrap on daily PnL, block = 5 days, 10,000 reps).
- ETH replication: identical frozen pipeline, promoted signals only; report as independent confirmation/failure.
## 5. Execution phases (with hard STOPs)
**Phase 0 — Data audit.** Set up env; download ONE sample day each of aggTrades / fundingRate / klines / bookDepth for BTCUSDT; verify checksums; print schemas, timestamp units, header behavior; estimate total download size for the full period; write `reports/DATA_AUDIT.md`. → **STOP. Wait for user review.**
**Phase 1 — Pre-registration.** Write `preregistration/PREREGISTRATION.md` fixing every definition in §3–§4 (with any Phase-0-driven adjustments, e.g., sample window vs disk budget), plus DATA-BLOCKED entries for H4/H5. Commit it. → **STOP. Do not compute any forward return or PnL until the user replies "prereg approved".**
**Phase 2 — ETL + QA.** Full download + ingest + parquet bar store; QA suite (checksums, gaps, monotonicity, klines reconciliation); truncation-invariance unit tests for all four signal detectors (pytest). All tests green before Phase 3.
**Phase 3 — Event studies.** Detect events, run §4.1 on BTC in-sample; apply gates §4.2; produce `reports/event_study_btc.md` + CSVs (runner-generated, immutable). Report both gross tables and cost-adjusted materiality verdicts.
**Phase 4 — Backtests.** Only promoted signals, per §4.4. OOS confirmation + ETH replication. `reports/backtest_<signal>.md` + CSVs.
**Phase 5 — Finalize.** Hand-written `README.md` (methodology-first: falsification protocol, FDR, DSR, cost model, data-blocked disclosure, honest results summary), `ROADMAP.md` (v1.5: L2 wall/pull on self-recorded depth via `collector/`; v2: Deribit options-flow × order-flow fusion — data feasibility TBD), `DEVIATIONS.md` if any. Prepare commit series with ASCII message files. → **STOP. Never push without explicit user confirmation.**
## 6. Repo layout
```
orderflow-research-engine/
├── README.md                  # hand-written, editable
├── ROADMAP.md
├── preregistration/
│   ├── PREREGISTRATION.md
│   └── DEVIATIONS.md
├── src/orderflow/             # etl.py, footprint.py, signals/{h1..h6}.py, eventstudy.py, backtest.py, costs.py, stats.py
├── collector/depth_recorder.py
├── runners/                   # phase runners, each emits reports/ artifacts
├── tests/                     # truncation invariance, QA, detector unit tests
├── reports/                   # runner-generated, IMMUTABLE
└── data/                      # gitignored except manifest.json
```
## 7. Out of scope for v1
- Any L2-dependent confirmatory testing (H4/H5) — collector only.
- Options flow fusion (v2 roadmap note only).
- Live trading, order routing, ML models, parameter optimization of any kind.
Begin with Phase 0.
