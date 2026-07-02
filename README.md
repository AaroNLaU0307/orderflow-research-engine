# Order Flow Research Engine v1

A confirmatory quantitative research project testing whether classic
order-flow footprint signals contain exploitable information in Binance
BTCUSDT perpetual futures, under a falsification-first, pre-registered
protocol. This is not a trading bot and ships no live strategy.

## Result

Six classic order-flow signals were in scope. Two - **H4 (liquidity
wall)** and **H5 (liquidity pull)** - are **DATA-BLOCKED** for the entire
study: the official Binance historical archive carries no full-depth L2
order book history, and third-party vendors' free tiers (1st-of-month
samples only) are structurally insufficient for a confirmatory event
study. No claim of "no edge" is made for H4/H5; they are simply untested.
See [`preregistration/PREREGISTRATION.md`](preregistration/PREREGISTRATION.md#3-data-blocked-register--h4-h5)
section 3.

The remaining four - **H1 delta divergence, H2 absorption, H3 stacked
imbalance, H6 exhaustion** - were tested on BTCUSDT in-sample
(2022-07-01 to 2024-12-31) under the pre-registered 20-cell family (4
signals x 5 horizons), Benjamini-Hochberg FDR at q=0.10.

**Zero of 20 cells cleared BH-FDR significance. Zero of four signals were
promoted.** H3 (62 in-sample events) and H6 (286 events) additionally
failed the minimum-event-count gate (>=300) at the pre-registered
convention parameters - underpowered, not merely null.

The most statistically credible cell in the entire table - the
highest-mean cell among those clearing raw p<0.05, before any FDR
correction - was **H1 at the 1-hour horizon, +2.1bp gross**. Against the
pre-registered materiality bar of 18bp (1.5x the ~12bp round-trip cost
floor: 5bp taker fee + slippage, each side), that cell sits roughly
**9x below** the threshold required to call it economically material -
before even factoring in that it does not survive multiplicity
correction. **This is a double null: informational (fails BH-FDR) and
economic (even the best cell falls far short of materiality).**

Because no signal was promoted:
- **The Phase 4 confirmatory backtest was not run.** There is nothing to
  confirm.
- **The out-of-sample segment (2025-01-01 to 2026-06-30) was not
  touched by any event-return statistic** - not descriptively, not for
  completeness. Promotion gates exist precisely to decide what is
  allowed to see OOS data; nothing cleared them, so OOS remains reserved
  and clean for any future pre-registered follow-up.
- **ETH replication was not run** (promoted-signals-only per the
  prereg). The ETH bar store was ingested and passed the same Phase 2 QA
  as BTC.
- **No Deflated Sharpe Ratio is reported for a strategy**, because there
  is no promoted strategy to deflate. The declared trial count (N=140)
  is disclosed anyway, for transparency about the full scope of what was
  computed.

A **report-only sensitivity grid** (4 one-factor-at-a-time configs:
Delta=10, Delta=50, bar=3m, bar=15m; 80 further uncorrected cells) shows
the null is not an artifact of the primary 5-minute/Delta=25 convention:
8 of 80 cells cross |t|>1.96, close to what independent chance alone
would predict at this scale, and none of the pattern is consistent
across configs. See `reports/sensitivity_grid.md` for the full tables
and the mandatory interpretation preamble governing how (and how not) to
read them.

Full numeric detail: [`reports/FINAL_REPORT.md`](reports/FINAL_REPORT.md)
(assembled from the runner-generated artifacts of every phase - nothing
in it is hand-typed).

**This is a clean negative result. It is the intended and fully
acceptable outcome of a falsification-first study**, not a setback. Future
work on these four signals means a new pre-registered study on unseen
data - not a re-run of this one with adjusted thresholds. No gate, window,
or threshold in this repository should be read as a candidate for
loosening; see [`ROADMAP.md`](ROADMAP.md) for what legitimate next steps
look like (new hypotheses, new data, not relaxed rules).

## Methodology

**Pre-registration before PnL.** Every hypothesis, event definition,
parameter, horizon, statistical gate, and cost assumption is frozen in
[`preregistration/PREREGISTRATION.md`](preregistration/PREREGISTRATION.md),
committed before any code touched a forward return or PnL figure. The
document went through one substantive review round before sign-off,
recorded in its own Appendix A rather than as a post-hoc deviation
(the largest change: replacing an underspecified "best horizon" concept
with a fully deterministic two-step rule, below). No definition changed
after sign-off; `preregistration/DEVIATIONS.md` is the log for any that
would have, and is empty.

**Promotion is two decoupled, mechanical steps - built, and never fired
in this study:**
1. **Gate 3 (does an edge exist):** define the eligible-horizon set
   `E(signal)` = every horizon that is simultaneously BH-FDR significant,
   >=30 minutes, and clears the 18bp materiality bar. Gate 3 passes iff
   this set is non-empty. This is a pure existence test with no tie-break
   sensitivity.
2. **h\* selection (which horizon is traded):** for any signal passing
   gates 1-3, `h* = argmax` over `E(signal)` of the day-cluster-bootstrap
   t-statistic, ties toward the longer horizon - fully deterministic, no
   discretion at write-up time. h\* alone then governs the year-consistency
   gate and, had any signal reached it, the Phase 4 backtest exit,
   OOS confirmation, and ETH replication horizon.

Splitting "does an edge exist" from "which horizon" this way removes what
would otherwise be the last post-hoc degree of freedom in the promotion
decision. Neither step ever activated here - every signal failed gate 2
(BH-FDR) before gate 3 was reached - but the machinery is real, tested,
and documented for the next study that might clear it.

**FDR family.** Exactly the 20 BTC in-sample cells (4 signals x 5
horizons), Benjamini-Hochberg at q=0.10. Out-of-sample and ETH cells are
confirmatory follow-ups for already-promoted signals, deliberately outside
this family - standard discovery-vs-confirmation separation, moot here
since discovery produced no promotions.

**Day-cluster bootstrap.** Every p-value and confidence interval resamples
*calendar days* (not individual events) with replacement, 10,000
repetitions, respecting intraday event clustering and serial dependence -
the concrete implementation of a stationary block bootstrap. The
resampling is seeded deterministically
(`orderflow.stats.stable_seed`, a `zlib.crc32`-based seed) after a real
reproducibility bug was found mid-review: Python's built-in `hash()` on a
tuple is randomized per process by default, so an earlier version of this
pipeline silently produced different p-values on every run from identical
data. Two full runs now produce byte-identical output.

**Segment purging.** An event is admitted into a segment's (IS or OOS)
statistics only if its *longest* tested horizon's forward window closes
entirely within that same segment - decided once per event, not once per
horizon, so every horizon of a given signal-cell always shares an
identical event set and no horizon comparison is confounded by a shifting
sample.

**Quarantine.** A confirmed exchange-side data gap on 2022-09-06 (both
BTC and ETH, ending within 10 milliseconds of each other - see the
data-engineering section below) is excluded from event formation, and any
forward-return window overlapping it is nulled
(`src/orderflow/quarantine.py`). This runs *before* deduplication, so a
quarantined event can never have already suppressed a legitimate nearby
one through the 6-bar dedup rule.

**Costs.** 5bp taker fee + slippage (half-spread, negligible for BTC,
plus a 1bp impact buffer) per side, ~12bp round trip; historical funding
applied to any position crossing a funding timestamp, signed by side.
Stated prominently because it is the dominant null-generating force for
short-horizon order-flow signals - see the headline result above.

**Multiplicity.** Deflated Sharpe Ratio trial count N=140 = 20 (BTC
in-sample) + 20 (BTC out-of-sample, would-have-been) + 20 (ETH
replication, would-have-been) + 80 (sensitivity grid). Declared in full
regardless of whether a promoted strategy exists to apply it to.

## Data engineering

Phase 2 QA surfaced three real data-quality issues, each caught by a
check that existed specifically to catch it - worth documenting because
none of them were hypothetical:

**An exchange-side partial-day gap, 2022-09-06.** The daily-vs-klines
volume reconciliation flagged both BTCUSDT and ETHUSDT as short that day.
Investigation traced it to the raw `aggTrades` archive itself - both the
monthly *and* daily Binance archives - not an artifact of ingestion: the
`agg_trade_id` sequence jumps by 31,646 (BTC) and 94,136 (ETH) across a
window that, for BTC, runs 17:14:36-17:20:57 UTC and for ETH,
17:09:34-17:20:57 UTC. Both windows end within **10 milliseconds** of
each other - a strong signature of a shared exchange-side event, not two
independent archive artifacts. Not repairable by re-splicing (the daily
archive has the identical hole), so the affected bars are quarantined
rather than backfilled: excluded from event formation, with any
forward-return window overlapping the gap nulled.

**A monthly-vs-daily same-ID, different-quantity revision.** Ten days in
ETHUSDT 2023-05 reconciled short against klines. The first repair attempt
- concatenate the daily archive onto the monthly trades and deduplicate
by `agg_trade_id` - appeared to succeed but left the reconciliation diff
completely unchanged. Direct comparison showed why: the monthly and daily
archives contained the *exact same* 782,735 trade IDs for one of the
affected days, but disagreed on the reported quantity for those IDs (an
apparent Binance revision between when the two archives were generated).
Deduplicating by ID alone silently kept whichever copy was listed first -
the stale monthly one. Fixed by dropping the target day's monthly-sourced
rows entirely before splicing in the daily archive's values, rather than
merging at the trade level; the daily archive has matched klines almost
exactly in every cross-check run during this audit, so it is treated as
authoritative for any day being repaired. A regression test reproduces
the exact same-ID-different-quantity scenario.

**Ten whole-day monthly-archive gaps.** Five BTC and five ETH months
(clustered in 2022-08 through 2023-05 - an early-archive-era pattern, not
a recurring one across the full 48-month period) had the monthly
`aggTrades` rollup missing specific calendar days entirely, while the
corresponding daily archive files were complete. All ten were backfilled
by splicing in the daily files.

**Provenance.** `data/manifest.json` records the sha256, byte size, and
ingestion timestamp of every file this pipeline ever downloaded,
including both the original monthly zip and any daily backfill zips for
a repaired month. `data/qa_backfill_log.jsonl` and
`data/qa_breach_classification.jsonl` are the per-month and per-day
record of what was found and how it was resolved; both feed directly
into `reports/QA_SUMMARY.md`'s classification table and totals, so the
QA report and the underlying evidence never drift apart.

The reconciliation gate closed as **PASS-WITH-EXCEPTIONS**: every
outstanding breach day resolved to either `KLINES_HOLE` (aggTrades
independently verified complete against its own daily archive; klines
was the deficient source) or the quarantined upstream gap above - zero
`UNEXPLAINED` days. Full per-day table in `reports/QA_SUMMARY.md`.

One further parsing issue was found and fixed, not gating: some
`bookDepth` archive days format the percentage-band column as a float
string (`"-5.00"`) instead of an integer string (`"-5"`), which broke the
original `Int64`-typed reader. `bookDepth` is descriptive-only per the
prereg (never a signal input), so this never blocked confirmatory work;
fixed anyway (`orderflow.etl.read_bookdepth` now reads it as `Float64`
and rounds/casts), with a regression test.

## Repository layout

```
orderflow-research-engine/
├── README.md                  # this file
├── ROADMAP.md
├── docs/BRIEF.md               # verbatim original project brief
├── preregistration/
│   ├── PREREGISTRATION.md      # frozen spec, signed off before any PnL
│   └── DEVIATIONS.md           # empty - no post-approval changes occurred
├── src/orderflow/               # etl, footprint, signals/h1-h6, eventstudy, stats, costs, quarantine
├── collector/depth_recorder.py # v1.5 L2 recorder (see ROADMAP.md)
├── runners/                    # phase runners; each emits reports/ artifacts
├── tests/                      # 90+ tests: unit, truncation-invariance, integration
├── reports/                    # runner-generated, immutable
└── data/                       # gitignored except manifest.json
```

## Reproducing this study

```
python -m venv .venv && .venv/Scripts/activate  # or source .venv/bin/activate
pip install -r requirements.txt
pytest tests/                                    # should show 90 passed
python runners/phase2_etl.py                     # full 48-month, 2-symbol ingest (~1hr, ~54GB download)
python runners/phase2_qa.py                      # QA gate
python runners/phase3_event_study.py             # the 20-cell BTC in-sample study
python runners/phase3_sensitivity_stage.py       # Delta=10 / bar=3m re-staging
python runners/phase3_sensitivity_derive.py      # Delta=50 / bar=15m derivation
python runners/phase3_sensitivity_run.py         # the 80-cell sensitivity grid
python runners/phase5_final_report.py            # assembles reports/FINAL_REPORT.md
```

Every `runners/phase*.py` script is independently re-runnable and
regenerates its `reports/*.md` / `reports/*.csv` output deterministically
from the same input data.
