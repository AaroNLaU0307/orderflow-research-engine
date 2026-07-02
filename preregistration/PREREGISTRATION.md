# Pre-Registration — Order Flow Research Engine v1

**Status:** APPROVED 2026-07-02, following one required revision to §6.5
(the horizon-selection rule, Appendix A resolution 2). Every definition below
is now frozen; any unavoidable change is logged in
[`DEVIATIONS.md`](DEVIATIONS.md), never made silently.

**Version:** v1.1 (v1.0 was the pre-review draft; v1.1 incorporates the
ratified Appendix A resolutions, most substantively the §6.5 rewrite)
**Date:** 2026-07-02
**Canonical source brief:** [`docs/BRIEF.md`](../docs/BRIEF.md) (verbatim, committed Phase 1)
**Phase 0 audit:** [`reports/DATA_AUDIT.md`](../reports/DATA_AUDIT.md)

This document is written to be self-sufficient: a reader who has never seen the
brief should be able to reproduce the entire study from this file alone. Where
the brief left an operational detail implicit or ambiguous, this document
resolves it explicitly and flags the resolution in Appendix A so it can be
checked before sign-off.

---

## 1. Study identification

**Title:** Order Flow Research Engine v1 — does classic order-flow footprint
analysis contain exploitable information in Binance BTCUSDT perpetual futures?

**Nature of the study:** Confirmatory, falsification-first. A clean negative
result (no promoted signals) is a fully acceptable and intended possible
outcome. No parameter is fit to data; every threshold below comes from stated
practitioner/academic convention. Sensitivity grids are robustness evidence
only, never a selection mechanism.

**Universes:**
- **Primary:** BTCUSDT USD-margined perpetual futures (Binance `futures/um`).
- **Replication (pre-registered, conditional):** ETHUSDT USD-margined perpetual
  futures. The pipeline runs on ETH **only** for signals that are promoted on
  BTC (§6 gates). ETH is never used for discovery.

**Sample period:** 2022-07-01 to 2026-06-30 (48 months), per the original
brief and confirmed feasible in Phase 0 (§6 of `DATA_AUDIT.md`; ~54 GB
compressed download, 984 GB free locally — no shortening required).

- **In-sample / discovery (IS):** 2022-07-01 00:00 UTC → 2024-12-31 23:59 UTC.
- **Out-of-sample / confirmation (OOS):** 2025-01-01 00:00 UTC → 2026-06-30 23:59 UTC.

**Data sources.** All from the official free Binance historical archive.
Base URL pattern:

```
https://data.binance.vision/data/futures/um/{monthly|daily}/{dataset}/{SYMBOL}/...
```

| Dataset | Cadence used | Role | Confirmed schema (Phase 0) |
|---|---|---|---|
| `aggTrades` | monthly zips | Primary — footprints, delta, all 4 testable signals | `agg_trade_id, price, quantity, first_trade_id, last_trade_id, transact_time, is_buyer_maker`. `is_buyer_maker=true` ⇒ SELL aggressor (buy aggressor = `is_buyer_maker=false`). |
| `fundingRate` | monthly zips | Funding PnL for positions open across a funding timestamp | `calc_time, funding_interval_hours, last_funding_rate`. Interval confirmed 8h (3 events/day) in sample. |
| `klines` (1m) | monthly zips | QA reconciliation only (never a signal input) | `open_time, open, high, low, close, volume, close_time, quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore`. |
| `bookDepth` | daily zips | Descriptive context only. **Not** usable for any confirmatory signal (see §3, H4/H5). | `timestamp (string, not epoch), percentage, depth, notional`. Archive coverage confirmed to start ~2023-01-01, i.e. **not** available for the first ~6 months of the study period; any descriptive bookDepth exhibit in the final report is captioned "2023-01 onward." |

**Confirmed data quirks (Phase 0), handled defensively in `src/orderflow/etl.py`:**
- Header-row presence is **not** constant across eras: present in files sampled
  from 2025-03, **absent** in files from 2022-07-01 (same column order). ETL
  sniffs the first line of every file (numeric vs. alphabetic first field)
  rather than assuming a header state.
- Timestamps are milliseconds-epoch throughout the full 2022-07→2026-06 window
  for `futures/um` (checked at both ends of the period); still sniffed
  defensively by digit-count per file rather than hardcoded, since the brief
  correctly notes this is not guaranteed for all Binance archive families.
- Every ingested zip's sha256 is recorded in `data/manifest.json` alongside its
  source URL and the date it was ingested, so a re-published Binance file is
  detectable on re-run.

**Manifest / checksum policy:** every `.zip` is verified against its
accompanying `.CHECKSUM` file before parsing; a checksum mismatch halts
ingestion of that file and is logged, not silently retried. `data/manifest.json`
is the single append-only ledger of every file ever ingested (URL, sha256,
byte size, ingestion timestamp); it is the one file under `data/` that is not
gitignored.

**Size-estimate caveat (recorded here per Phase-0 review):** the ~54 GB total
download estimate in `DATA_AUDIT.md` was built from a 16-month (BTC) /
14-month (ETH) spread sample, not a single day — but activity is materially
non-stationary: high-activity months (2022 H2, early/late 2024) ran 2–3× the
size of quiet months (e.g. 2023-07, ~330 MB) in the same sample. The 54 GB
figure is a mean-based estimate, and the true total could plausibly land
40–70% higher. This has **no bearing on feasibility** given 984 GB free
locally, but is recorded here (not just in the Phase 0 report) so that anyone
consulting the manifest for expected-size sanity checks during Phase 2 ingest
has the caveat in view, since `data/manifest.json` itself carries no prose.
ETHUSDT was sized (§6 of `DATA_AUDIT.md`) but not schema/header-probed in
Phase 0; any surprise there is a first-contact event at Phase 2 ingest and
will be logged in the QA output, not silently absorbed.

---

## 2. Hypotheses H1–H6

Every hypothesis has a long/short mirror pair. Both directions are pooled into
one signed-return distribution per signal (§5), so the tested cell count stays
at **4 signals × 5 horizons = 20** (BTC IS), not 8×5.

### H1 — Delta divergence

**Plain-language claim:** at a new local price high, if aggressive buying
volume (delta) is weaker than it was at the *previous* local high, the rally
is running out of aggressor participation and is more likely to reverse down
(and the mirror at lows, up).

**Operational definition (bearish case):**
```
cumD24[t]  = sum(delta[t-23 .. t])                       # rolling 24-bar (2h) delta sum
sigma[t]   = trailing 8640-bar (30-day) std of cumD24     # see section 5 warm-up note
s          = the most recent bar with s <= t-1 such that
             close[s] == max(close[s-23 .. s])            # "the previous 24-bar price high"
event at t if:
    close[t] == max(close[t-23 .. t])                     # t is itself a new 24-bar high
    AND cumD24[t] < cumD24[s] - 0.5 * sigma[t]
```
**Mirror (bullish case, delta convergence at lows):**
```
event at t if:
    close[t] == min(close[t-23 .. t])
    AND cumD24[t] > cumD24[s] + 0.5 * sigma[t]
    where s = most recent bar s<=t-1 with close[s] == min(close[s-23..s])
```
**Direction:** bearish case → short; bullish case → long.
**Magnitude:** `|cumD24[t] - cumD24[s]| / sigma[t]` (the delta shortfall/surplus z-score).

### H2 — Absorption

**Plain-language claim:** heavy aggressive selling into a price zone that
nonetheless fails to push price through it signals hidden buying interest
("absorption") and favors a bounce (mirror: heavy aggressive buying that fails
to break higher favors a drop).

**Operational definition (bullish case, absorption at lows):**
```
zone[t]  = { bucket_px : bucket_px <= low[t] + 0.20 * (high[t] - low[t]) }   # bottom 20% of bar range
med96(t) = median of the multiset of all nonzero bucket volumes observed
           across every bucket of every bar in the trailing 96 bars
           (one scalar per bar t, pooled cross-sectionally across all buckets
           of all 96 trailing bars — NOT a per-price-level history, since a
           specific bucket_px will often have zero or few observations in its
           own history once price has drifted away from it)
event at t if there exists p in zone[t] such that:
    bucket_volume(t, p) >= 4 * med96(t)
    AND sell_vol(t, p) >= 0.70 * bucket_volume(t, p)
    AND close[t] >= p + Delta                    # price refused to break below the zone
```
**Mirror (bearish case, absorption at highs):**
```
zone[t] = { bucket_px : bucket_px >= high[t] - 0.20 * (high[t]-low[t]) }
event at t if there exists p in zone[t] such that:
    bucket_volume(t,p) >= 4 * med96(t)
    AND buy_vol(t,p) >= 0.70 * bucket_volume(t,p)
    AND close[t] <= p - Delta
```
**Direction:** bullish case → long; bearish case → short.
**Magnitude:** `bucket_volume(t,p) / med96(t)` (the volume multiple), taken at
the qualifying bucket with the largest multiple if more than one bucket in the
zone qualifies in the same bar.

### H3 — Stacked imbalance

**Plain-language claim:** several consecutive diagonally-adjacent price levels
all showing a strong same-direction aggressor imbalance (buy pressure stacked
against the level below it, or sell pressure against the level above) signals
a directional push with follow-through.

**Operational definition (bullish case):**
```
p25_96(t) = 25th percentile of the multiset of all nonzero bucket volumes
            observed across every bucket of every bar in the trailing 96 bars
imbalanced_up(p) at bar t:
    sell_vol(t, p - Delta) >= p25_96(t)                       # anti-div-by-tiny floor on the denominator side
    AND buy_vol(t, p) / sell_vol(t, p - Delta) >= 3.0
event at t if there exist >= 3 consecutive bucket levels p, p+Delta, p+2*Delta, ...
    (or any 3+ run) within bar t that are all imbalanced_up
```
**Mirror (bearish case):**
```
imbalanced_down(p) at bar t:
    buy_vol(t, p + Delta) >= p25_96(t)
    AND sell_vol(t, p) / buy_vol(t, p + Delta) >= 3.0
event at t if there exist >= 3 consecutive bucket levels all imbalanced_down within bar t
```
**Direction:** with the imbalance (bullish run → long; bearish run → short).
**Magnitude:** `stack_length * mean(ratio over the qualifying consecutive buckets)`.
If a bar contains more than one qualifying run in the same direction, the
longest run is used (ties broken by higher mean ratio).

### H6 — Exhaustion

**Plain-language claim:** a volume spike at a fresh high, where the very top
of the bar's own footprint shows aggressive buying drying up (net negative
delta in the top buckets even as price prints the high), signals the rally is
being absorbed by sellers into strength and is exhaustion-prone.

**Operational definition (bearish case, exhaustion at highs):**
```
P95_2016[t] = 95th percentile of bar volume over the trailing 2016 bars (1 week)
top2(t)     = the 2 highest populated (nonzero-volume) buckets of bar t
event at t if:
    volume[t] >= P95_2016[t]
    AND close[t] == max(close[t-23 .. t])                 # 24-bar close high
    AND (delta of top2(t), summed) < 0
```
**Mirror (bullish case, exhaustion at lows / capitulation reversal):**
```
bottom2(t) = the 2 lowest populated buckets of bar t
event at t if:
    volume[t] >= P95_2016[t]
    AND close[t] == min(close[t-23 .. t])
    AND (delta of bottom2(t), summed) > 0
```
**Direction:** bearish case → short (reversal); bullish case → long (reversal).
**Magnitude:** `(volume[t] / P95_2016[t]) * |combined delta of the extreme 2 buckets|`
— concretized as a volume-multiple-of-threshold (consistent with H2's
magnitude style) rather than a rank-percentile, since the brief's "volume
percentile" was descriptive, not formulaic (flagged in Appendix A).

### Falsification statements (apply identically to H1/H2/H3/H6)

For each signal, exactly one of four outcomes is reported — never a
positive-only narrative:

- **(a) Informational null:** the signal fails the BH-FDR gate (§6.3) —
  pooled signed forward returns are statistically indistinguishable from zero,
  after multiplicity correction, at the required horizon combination. This
  means the footprint pattern, as operationally defined here, carries no
  detectable information at this sample size. Reported as: *"no confirmable
  edge, informational null."*
- **(b) Economic null:** the signal clears BH-FDR (real, non-zero information
  content) but fails gate 3 (the eligible-horizon set E(signal) is empty — no
  FDR-significant, ≥30m horizon reaches 1.5× round-trip cost) or gate 4 (sign
  flips in ≥2 of 3 IS segments at the promoted horizon h*, §6.5). This is a
  *stronger and more interesting* failure mode than (a): information exists,
  but it is too small, too inconsistent, or too fragile to survive real
  trading frictions or regime change. Reported as: *"real but uneconomic /
  unstable edge."*
- **(c) Underpowered:** fewer than 300 deduplicated IS events. No promotion
  decision can be responsibly made either way at this sample size. Reported as
  *"insufficient events to evaluate,"* explicitly not conflated with (a) or (b).
- **(d) Promoted:** clears all four gates in §6.5 → proceeds to the Phase 4
  confirmatory backtest, where OOS and ETH are the actual out-of-family tests
  of whether the IS finding replicates (§7).

---

## 3. DATA-BLOCKED register — H4, H5

**H4 — Liquidity wall** (large resting limit orders as support/resistance) and
**H5 — Liquidity pull** (rapid cancellation of resting size ahead of price) both
require historical full-depth L2 order book data.

**Why blocked:** the official Binance historical archive contains no
full-depth L2 snapshot/diff history (only `bookDepth`, an aggregated
±1/2/3/5/10% notional summary — insufficient to detect individual wall
placement or cancellation). Third-party vendors (e.g. Tardis) sell full L2
history; their free tier only exposes the 1st calendar day of each month,
which is structurally insufficient for a confirmatory event study requiring
hundreds of independent events spread across the full sample period. Using
only 1st-of-month samples would silently convert this into a
severely-underpowered, non-representative test — explicitly against the
falsification-first mandate.

**Resolution for v1:** H4 and H5 are marked `DATA-BLOCKED`. No confirmatory
claim, backtest, or event study is produced for either hypothesis anywhere in
this study. **No claim of "no edge" is made for H4/H5 either** — absence of a
test is not evidence of absence, and this document is explicit that H4/H5
remain simply untested.

**Deliverable in lieu:** `collector/depth_recorder.py` — a websocket
`@depth@100ms` diff-stream recorder with snapshot resync, restart-safe,
writing parquet — so that live L2 collection can begin now and accumulate
toward a future v1.5 in which H4/H5 can be tested confirmatorily on
self-recorded data. This is a collection tool only; it does not itself
constitute or enable any confirmatory claim in v1.

---

## 4. Bar / footprint construction

- **Bars:** 5-minute, UTC epoch-aligned (`:00, :05, :10, ...`). Persisted keyed
  by `bar_ts` = bar **open** time (per the ETL schema below). A signal detected
  using bar t's completed data is only knowable as of that bar's **close**
  time (`bar_ts + 5min`) — this is what "completed bar" means for look-ahead
  purposes, and is enforced jointly with the next-bar-open execution rule
  (§7): a bar is never used by any detector until it is fully closed.
- **Bar close price** = price of the last trade in the bar. A bar with zero
  trades **forward-fills** its OHLC from the previous bar's close (open = high
  = low = close = prior close) and carries zero volume / zero delta / no
  footprint buckets. Such bars contribute a `0` to any trailing-volume
  percentile computation (H6) and simply contribute no observations to any
  trailing nonzero-bucket-volume pool (H2, H3) — no special-casing is needed
  beyond this, but the ETL truncation-invariance test (Phase 2) explicitly
  includes a synthetic zero-trade-bar fixture to confirm this.
- **Footprint buckets — absolute grid, not per-bar-relative:**
  `bucket_px = floor(price / Delta) * Delta`, where `Delta = 25 USDT` (BTC),
  `Delta = 1 USDT` (ETH). Using an absolute grid (rather than re-bucketing
  relative to each bar's own range) means the same price always maps to the
  same bucket across bars, which is required for the trailing
  nonzero-bucket-volume pooling used in H2/H3.
- **Bucket delta** = `buy_vol - sell_vol`, where buy = aggressor buy =
  `is_buyer_maker == false` (i.e., the taker lifted the offer); sell =
  `is_buyer_maker == true`.
- **Persisted parquet schema** (per brief §2.4, restated): one row per
  `(bar_ts, bucket_px)` with `buy_vol, sell_vol, trade_count`, plus one row per
  `bar_ts` with bar-level aggregates `open, high, low, close, volume, delta,
  cumulative_delta`. All downstream signal/event code reads only this parquet
  store; raw ticks are parsed exactly once during Phase 2 ETL.

---

## 5. Event hygiene

- **Deduplication:** within a single signal, events of the **same direction**
  occurring within 6 bars of a prior kept event are dropped (keep the first).
  Different signals never suppress each other — each of the 4 hypotheses is
  evaluated and deduplicated independently.
- **Warm-up — corrected from the original brief (Phase-1 adjustment, pre-PnL):**
  the brief specified discarding the first 2016 bars (1 week) as warm-up. This
  is insufficient: H1's divergence z-score depends on `sigma[t]`, a trailing
  **8640-bar (30-day)** standard deviation of the rolling 24-bar delta sum.
  Evaluating H1 on any bar before 8640 completed bars exist would use a
  partially-populated, non-stationary-length σ window, which is both a
  methodological inconsistency (the same statistic computed over different
  window lengths depending on how early in the sample the event falls) and
  arguably a soft look-ahead-adjacent issue (the variance estimate has not
  "settled"). The correct warm-up is the **maximum lookback required by any
  of the four testable signals** — H1's 8640 bars dominates H6's 2016-bar and
  H2/H3's 96-bar requirements. **Locked warm-up: the first 8640 bars of each
  universe's series are discarded** (no event, of any signal, is emitted for
  `bar_index < 8640`). Since OOS begins 2025-01-01 — far more than 8640 bars
  (30 days) after the 2022-07-01 series start — this correction only affects
  the first ~30 calendar days of the IS period; it does not touch the IS/OOS
  boundary or OOS itself.
- **Segment-boundary purging:** admission is **per-event**, not
  per-event-per-horizon (see Appendix A for why this reading was chosen over
  the alternative). An event at bar t is only admitted into a segment's (IS or
  OOS) statistics if its **longest tested horizon's forward window (48 bars)**
  closes entirely within that same segment — i.e., `t + 1 + 48` must not cross
  the IS/OOS boundary or the sample end. If it qualifies, the event
  contributes an observation to **all 5** horizon cells (h=1,3,6,12,48) of its
  signal within that segment; if it does not qualify, it is dropped from
  **all 5** horizon cells for that segment (not selectively kept for shorter
  horizons). This keeps `N_events` identical across the 5 horizons of a given
  signal × segment cell, so cross-horizon comparisons within a cell are never
  confounded by a shifting event set. No forward window ever crosses a
  segment boundary under this rule, by construction.

---

## 6. Statistical plan

### 6.1 Forward return definition

```
r(h) = direction * log( open[t+1+h] / open[t+1] ),   h in {1, 3, 6, 12, 48} bars
     = {5m, 15m, 30m, 1h, 4h}
```
Entry reference is the **next bar's open** after the event bar closes — this
is execution-realistic (no same-bar fill) and consistent with the
look-ahead-prevention truncation-invariance requirement (brief §0.3): the
event is only known as of bar t's close, and the earliest tradeable price is
bar t+1's open.

### 6.2 Per-cell estimators

For each of the **4 signals × 5 horizons = 20 BTC in-sample cells**:
- Mean signed forward return, standard t-statistic (descriptive; not the
  inference basis — see 6.3).
- **Day-cluster bootstrap p-value** (the concrete implementation of the
  brief's "stationary block bootstrap... to respect overlap/serial
  dependence"): resample **calendar days** with replacement, restricted to the
  set of calendar days that contain ≥1 event of this cell; for each of 10,000
  resamples, pool all events falling on the resampled days and recompute the
  mean signed forward return; the two-sided p-value is the percentile rank of
  0 in this resampled distribution of means. This respects intraday event
  clustering and serial dependence by resampling at the day level rather than
  the event level.
- **Spearman IC** between event magnitude (§2, per-signal magnitude measure)
  and forward signed return, with a day-cluster bootstrap 95% CI (same
  resampling mechanic as above, applied to the Spearman statistic).
  Informational only — never a gating criterion.

### 6.3 Multiplicity — FDR family definition

**The FDR family is exactly the 20 BTC in-sample cells** (4 signals × 5
horizons). Benjamini-Hochberg at **q = 0.10** is applied across exactly these
20 p-values, no more and no fewer.

OOS results and the ETH replication are **not** members of this FDR family —
they are confirmatory follow-up tests, run only for signals that already
cleared discovery (BH-FDR + the other 3 gates) on BTC IS. Each is reported
with its own day-cluster bootstrap 95% CI, but without further multiplicity
correction, because the family of hypotheses being tested there was already
fixed and narrowed by the IS discovery stage — testing a single pre-specified
signal once on a single pre-specified confirmation sample is not a
multiple-comparisons scenario in the same sense as the 20-cell discovery
sweep. (This is the standard discovery-vs-confirmation separation: multiplicity
correction controls the false-discovery rate of the *search*, not of a single
replication check of an already-selected finding.)

### 6.4 Year-consistency gate (operationalized)

The brief's "≥2 of the ≥2.5 in-sample calendar years" is operationalized as
three discrete IS segments: **2022 H2** (2022-07-01 to 2022-12-31, a half-year
segment), **2023** (full year), **2024** (full year). The gate requires the
**same sign** of the mean signed return in at least **2 of the 3** segments,
evaluated at the signal's promoted horizon **h\*** — h\* is defined in §6.5
(its definition depends on gate 3, the economic-materiality gate, so it
cannot be stated before that gate).

### 6.5 Promotion gates (all four required)

A signal is promoted to Phase 4 backtest iff **all** of:
1. **≥ 300** deduplicated IS events (else outcome (c), §2, underpowered).
2. BH-FDR significant (q < 0.10, within the 20-cell family) at **≥ 2**
   horizons, **at least one of which is ≥ 30 minutes** (i.e., h ∈ {6, 12, 48}).
3. **Economic materiality — eligible horizon set.** Define
   ```
   E(signal) := { h : h is BH-FDR significant (q < 0.10) in-sample
                      AND h >= 30m                    (h in {6, 12, 48})
                      AND mean signed gross return at h >= 18 bp   (1.5x round-trip cost) }
   ```
   Gate 3 passes iff **E(signal) is non-empty**. This is a gate on whether the
   set is empty or not — it does not itself pick a horizon.
4. **Year-consistency**, evaluated at the promoted horizon h\* (defined
   immediately below): same sign of mean signed return in ≥ 2 of the 3 IS
   segments (§6.4).

**Promoted horizon selection (h\*).** For any signal that passes gates 1–3:
```
h* := argmax over h in E(signal) of the day-cluster-bootstrap t-statistic at h,
      i.e. | mean signed gross return at h | / bootstrap standard error at h
      (ties broken toward the longer horizon)
```
h\* is a **deterministic function of E(signal)** — never a free choice made at
write-up time after seeing the results table. It is the single horizon used
for: gate 4's year-consistency check (§6.4), the Phase 4 confirmatory
backtest's exit horizon, the OOS confirmation, and the ETH replication (§7).
No other horizon is used anywhere downstream of promotion.

This structure deliberately decouples *whether an economic edge exists*
(gate 3, a test of set non-emptiness) from *which horizon is traded*
(h\* selection, a deterministic rule with no discretion) — removing what
would otherwise be the last post-hoc degree of freedom in the promotion
process (see Appendix A, resolution 2).

Any signal failing any gate is reported per the applicable falsification
statement in §2 and does **not** proceed to Phase 4.

### 6.6 Cost model

- **Taker fee:** 5.0 bp per side (Binance USD-M VIP0, no BNB discount —
  deliberately conservative, not the user's actual fee tier).
- **Slippage:** half-spread (1 tick = 0.1 USDT for BTC, negligible) + 1.0 bp
  impact buffer, per side.
- **Round trip ≈ 12 bp total.** This is the dominant null-generating force for
  short-horizon order-flow signals and is stated prominently in every report
  that shows a gross number.
- **Funding:** for any position open across a funding timestamp (00:00, 08:00,
  16:00 UTC), apply `funding_pnl = -position_side * funding_rate_t * notional`,
  where `position_side = +1` for long, `-1` for short — i.e., a long position
  pays when the historical funding rate is positive (matching real Binance
  mechanics: longs pay shorts when funding > 0), and receives when negative.

### 6.7 Deflated Sharpe Ratio — trial count declaration

```
N_trials = 20   (BTC in-sample cells: 4 signals x 5 horizons)
         + 20   (BTC out-of-sample cells: same 4 signals x 5 horizons, confirmatory)
         + 20   (ETH replication cells: same 4 signals x 5 horizons)
         + 80   (sensitivity grid: 4 alternate configs x 20 cells; see section 8)
         --------
         = 140
```
Any promoted strategy's Deflated Sharpe Ratio (and Probabilistic Sharpe Ratio,
reported alongside it) uses **N = 140** as the declared total trial count —
the full universe of cells this protocol ever computes, not just the cells
that happened to look interesting.

---

## 7. Confirmatory backtest (promoted signals only)

- **Entry:** next bar open after the event bar closes (same reference as the
  event study, §6.1).
- **Exit:** the fixed **promoted horizon h\*** (§6.5) selected during IS
  discovery. h\* is **not** re-selected or re-optimized at backtest time; it
  is carried forward frozen from discovery.
- **Position management:** max 1 concurrent position per signal; if a new
  event fires while a position from an earlier event of the same signal is
  still open, the new event is **skipped** (not queued) — pre-registered, not
  a post-hoc convenience.
- **Sizing:** constant notional per trade.
- **Net PnL** = gross signed return − taker fees (both sides) − slippage (both
  sides) − funding accrued over the holding period, per §6.6.
- **Walk-forward structure:** purge = h\*'s bar length;
  embargo = 1 day (288 bars), applied between any IS-derived rolling
  threshold (e.g. the trailing volume/bucket percentiles used inside the
  detectors) and the evaluation window. Because every detector parameter is a
  fixed convention value (never fit to data), the primary confirmation channel
  is the **IS → OOS split itself**, not a rolling re-fit: the OOS
  (2025-01-01 → 2026-06-30) net result must independently show a **positive
  95% CI lower bound** on the per-trade signed net return (day-cluster
  bootstrap, 10,000 reps, over OOS trades only), and OOS net Sharpe is
  reported with a bootstrap CI (stationary block bootstrap on daily PnL,
  block length = 5 days, 10,000 reps, per brief §4.4).
- **DSR / PSR:** computed with N = 140 (§6.7).
- **ETH replication:** identical frozen pipeline and identical h\* (not
  re-optimized for ETH), Δ = 1 USDT bucket grid, promoted signals only.
  Reported as an independent confirmation-or-failure with its
  own day-cluster bootstrap CI — outside the FDR family (§6.3), a single
  pre-specified replication check.

---

## 8. Sensitivity grid (report-only, never gating)

One-factor-at-a-time grid, BTC only, over the 4 testable signals × 5 horizons
(20 cells per config):

| Factor | Alternate values |
|---|---|
| Bucket size Δ | 10 USDT, 50 USDT (baseline: 25 USDT) |
| Bar length | 3 minutes, 15 minutes (baseline: 5 minutes) |

4 alternate configs × 20 cells = **80 cells**, reported purely as descriptive
plateau evidence (does the signal's apparent edge survive nearby parameter
choices, or is it a knife-edge artifact of the exact baseline convention).
These 80 cells are never used to select, tune, or promote any signal — they
are counted in the DSR trial declaration (§6.7) precisely because they were
computed, even though they play no role in the promotion decision.

---

## 9. Deviations policy

Per the brief's non-negotiable principle #1: after this document is signed
off ("prereg approved"), **no definition in it may change**. Any unavoidable
deviation discovered during Phases 2–5 (e.g., a data quirk that breaks an
assumption here) is recorded in [`preregistration/DEVIATIONS.md`](DEVIATIONS.md)
with a plain-language justification, and is explicitly flagged in the final
report (`README.md`). Silent re-runs or silent redefinition are not permitted
under any circumstance.

The warm-up correction in §5 (2016 → 8640 bars) is **not** a
`DEVIATIONS.md` entry: it is a correction made during this same Phase 1,
before sign-off and before any forward return or PnL has been computed, so it
is simply the locked definition in this document, with its rationale
recorded inline for transparency. `DEVIATIONS.md` is reserved for changes
that happen *after* the "prereg approved" reply.

`preregistration/DEVIATIONS.md` is created alongside this document (currently
empty, ready to receive entries).

---

## Appendix A — Ambiguity resolutions (reviewed and ratified 2026-07-02)

Four places in the source instructions admitted more than one literal
reading. Each was resolved to a single deterministic rule, surfaced for
review before sign-off, and reviewed. Resolutions 1, 3, and 4 were ratified
as originally drafted; resolution 2 required a substantive rewrite, since its
original form was promotion-affecting, not cosmetic. Both are recorded below
with their final rationale.

1. **Segment-boundary purging granularity (§5). RATIFIED — per-event
   admission.** "An event only enters IS statistics if its entire longest
   forward window (48 bars) completes within IS... dropped for the affected
   horizons" admitted two readings: (a) per-event admission gated by the
   longest horizon, extended to all 5 horizons once admitted, or (b)
   per-event-per-horizon admission, where a boundary-crossing event could
   still contribute to shorter horizons. The "dropped for the affected
   horizons" phrasing that suggested (b) was a leftover drafting artifact from
   an earlier version of the instruction, not a competing operative rule —
   the governing clause is the 48-bar whole-window admission test. **(a) is
   correct**, for a substantive reason beyond just resolving the drafting
   inconsistency: gate 2 ("BH-FDR significant at ≥2 horizons") is only
   cleanly interpretable when all 5 horizon cells of a signal share an
   identical event set — otherwise a horizon could appear significant partly
   because it drew on a systematically different (e.g. more boundary-adjacent)
   sample of events than its neighbors. The cost of per-event admission is
   losing at most one 48-bar window's worth of events (~4 hours) at each of
   the 2 segment boundaries (IS/OOS split and sample end) — negligible against
   a multi-year sample.
2. **"Best FDR-significant horizon" (§6.5 gate 3, §7 backtest horizon).
   REVISED — replaced with an explicit eligible-set-then-deterministic-h\*
   rule.** The original resolution ("the FDR-significant, ≥30m-eligible
   horizon with the highest mean signed gross return") was reviewed and found
   to be promotion-affecting, not merely a documentation nicety: different
   defensible tie-break rules (argmax mean return vs. argmin FDR q-value vs.
   argmax t-statistic) can select different horizons for the *same* results
   table, and gate 3 as originally phrased ("mean return at the best horizon
   ≥ 18bp") would then pass or fail depending on which tie-break rule was
   used — a real post-hoc degree of freedom, exactly what a pre-registration
   exists to eliminate. **Current rule (§6.5):** gate 3 is restructured to
   test only whether the eligible horizon set `E(signal)` — every horizon that
   is simultaneously FDR-significant, ≥30m, and ≥18bp — is non-empty. Set
   non-emptiness does not depend on any tie-break rule, so gate 3's pass/fail
   is no longer sensitive to horizon-choice at all. A separate, fully
   deterministic rule then selects the promoted horizon **h\*** = argmax over
   `E(signal)` of the day-cluster-bootstrap t-statistic, ties toward the
   longer horizon — used only for gate 4 (year-consistency) and the
   downstream backtest/OOS/ETH exit horizon, both of which unavoidably need
   *some* single horizon and so cannot be made tie-break-free the way gate 3
   was. This is the strictly stronger fix: it removes the degree of freedom
   where removal is possible (gate 3) and makes it fully mechanical where a
   choice is unavoidable (h\*).
3. **H6 magnitude ("volume percentile × |extreme-bucket delta|"). RATIFIED —
   non-gating.** The brief describes this narratively rather than as a
   formula. Resolved as `(volume[t] / P95_2016[t]) * |combined delta of
   extreme 2 buckets|` — a volume-multiple-of-threshold, consistent with H2's
   magnitude style. Confirmed low-stakes: magnitude only feeds the
   non-gating Spearman IC and never affects a promotion decision.
4. **H2's "median bucket volume of the trailing 96 bars" (§2, H2). RATIFIED —
   cross-sectional pooled scalar, matching H3's P25 convention.** This was
   the intended reading: a per-price-level history would frequently be
   near-empty once price has drifted away from a given bucket over an 8-hour
   window, making that reading ill-defined in practice; pooling every
   bucket's volume across every bar in the trailing 96-bar window (as H3's
   `p25_96(t)` already unambiguously did) is the internally consistent choice.

Resolutions 1, 3, and 4 do not affect which signals could be promoted — they
govern exact event admission at segment edges (1), a detector threshold (4),
or a non-gating descriptive statistic (3). Resolution 2's *original* form
could have changed a promotion outcome; its *current* form (§6.5) removes
that sensitivity from gate 3 by construction, while h\*'s fully deterministic
selection still governs gate 4 and the traded horizon, because those two
uses inherently require picking one specific horizon.

## Appendix B — Cross-reference: brief → this document

Every operational value in brief §3–§4 is transcribed above with no
unstated changes, **except**:
- the warm-up correction (§5 of this document, brief said 2016 bars / 1 week;
  corrected to 8640 bars / 30 days);
- the sensitivity-grid Δ values (§8 of this document locks Δ=10/50 USDT
  exactly, a minor rounding of the brief's "×0.5/×2" formula against the
  25 USDT baseline, which would give 12.5/50 — the round-number values were
  specified directly in the Phase 1 task and are adopted as given); and
- gate 3 / promoted-horizon selection (§6.5 of this document): the brief's
  "mean signed gross return at the best FDR-significant horizon" is
  formalized into the eligible-set test `E(signal) != {}` plus a fully
  deterministic h\* = argmax-bootstrap-t-statistic rule, per Appendix A
  resolution 2. This is a formalization of an underspecified brief phrase,
  not a substantive change of intent.
