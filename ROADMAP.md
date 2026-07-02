# Roadmap

v1 tested four classic order-flow footprint signals (H1 delta divergence,
H2 absorption, H3 stacked imbalance, H6 exhaustion) on BTCUSDT perpetual
futures under a pre-registered falsification protocol. None survived
BH-FDR at q=0.10; H3 and H6 were additionally underpowered at convention
parameters. Two hypotheses (H4 liquidity wall, H5 liquidity pull) were
DATA-BLOCKED for the entire study - the official Binance archive carries
no full-depth L2 history, and third-party vendors' free tiers are too
sparse (1st-of-month-only) for confirmatory inference. See
`preregistration/PREREGISTRATION.md` section 3 and `README.md`.

## v1.1 (candidate) - single-shot confirmatory test of two placebo-flagged patterns

A single-shot, pre-registered confirmatory test of the two placebo-flagged,
hypothesis-generating patterns from v1 - the H1 event-return alignment and
the reversed-H6 (exhaustion-fade) direction - on the reserved, never-opened
OOS segment (2025-01 to 2026-06). Spec frozen before the segment is
opened; one attempt; both patterns remain economically immaterial at v1's
observed magnitudes (~2bp and ~5-7bp gross vs. the 18bp bar), so the
test's value is methodological (does the alignment replicate?) rather
than a path to a tradable edge. Origin as a post-hoc diagnostic is
disclosed by construction - see `preregistration/DEVIATIONS.md` entry 2
and `reports/event_study_btc.md`'s circular-shift placebo section for
where these two patterns came from.

## v1.5 - H4/H5 on self-recorded L2

The blocker for H4/H5 was data availability, not signal design - both
hypotheses are already formally specified in the prereg, DATA-BLOCKED
rather than untested-by-choice. `collector/depth_recorder.py` ships in
this repo now (smoke-tested against the live BTCUSDT `@depth@100ms`
stream) so recording can start immediately; it is not itself a v1.5
deliverable, it is the prerequisite for one.

**Honest timeline note:** the collector was smoke-tested for seconds, not
run continuously. A confirmatory H4/H5 study needs the same rigor as v1 -
hundreds of deduplicated events, day-cluster bootstrap inference, BH-FDR
across whatever cell family gets pre-registered - which means accumulating
genuinely long-running, gap-monitored recording (the collector logs but
does not auto-resync on a stream gap in v1; see the module docstring)
before a single statistic can be computed. Realistically this is a
multi-month data-accumulation phase, not a next-sprint item. Do not begin
any H4/H5 event-study code until that recording history exists and a v1.5
pre-registration (event definitions, cell family, gates) is written and
signed off - the same pre-registration-before-PnL discipline as v1,
applied to a new dataset.

Known v1.5 hardening items already visible from the v1 collector:
- Auto-resync on a detected `pu` gap (v1 logs and continues; a production
  recorder should re-run the snapshot+sync procedure).
- Multi-day file rotation / retention policy for the recorded parquet.
- A second symbol (ETHUSDT) if BTC recording proves out, for the same
  replication-only role ETH played in v1.

## v2 - options-flow x order-flow fusion

Exploratory only; data feasibility is not yet established. The idea: fuse
order-flow footprint signals (this repo) with options-derived positioning
signals (e.g. Deribit options open interest / flow) to see whether either
adds information conditional on the other. Before any pre-registration:

- Confirm a free or affordably-licensed source of historical Deribit (or
  equivalent) options flow/OI at sufficient granularity and history depth
  to match the BTC/ETH perp study period - not yet checked.
- If a source exists, v2 follows the identical falsification-first
  process as v1: Phase 0 data audit, pre-registration before any PnL,
  no parameter search, full cost modeling, multiplicity correction.

No further scoping until data feasibility is confirmed. This is a
placeholder for future work, not a committed deliverable.
