# Deviations from Pre-Registration

This log records any change to a locked definition in
[`PREREGISTRATION.md`](PREREGISTRATION.md) made **after** it was signed off
("prereg approved"). Each entry states what changed, why it was unavoidable,
and what would have happened if the original definition had been kept. Every
entry here must also be flagged in the final `README.md`.

## Entry 1 (2026-07-03): Day-cluster bootstrap rep count precision amendment

**What changed:** `preregistration/PREREGISTRATION.md` section 6.2 locks the
day-cluster bootstrap at "10,000" resamples. `orderflow.config.BOOTSTRAP_REPS`
was raised to **2,000,000** for the primary 20-cell BTC in-sample event
study (`runners/phase3_event_study.py`) and nowhere else - the 80-cell
sensitivity grid (section 8, always report-only/uncorrected) stays at its
original 10,000, as does the Spearman IC bootstrap (see scope note below).

**Why:** requested explicitly to reduce Monte Carlo error in the p-values
and confidence intervals that drive the BH-FDR classification - the exact
statistic gate 2 depends on. Same day-cluster bootstrap method, same
resampling unit (calendar days), same seeding mechanism
(`orderflow.stats.stable_seed`); only the rep count changed.

**What would have happened at the original value:** nothing different
qualitatively. At 10,000 reps the primary result was already 0/20 BH-FDR
significant; at 2,000,000 reps it is still 0/20. The two cells closest to
conventional significance (H1 h=6, raw p=0.0106->0.0100; H1 h=12, raw
p=0.0124->0.0109) moved slightly but neither was ever BH-significant at
either rep count, and BH-FDR q=0.10 over the 20-cell family requires more
than marginal raw-p movement to flip an outcome.

**Verification (not assumed, checked):** the full 20-cell family was
independently re-computed at 2,000,000 reps under 2 further seed labels
(`BTC-IS-seedB`, `BTC-IS-seedC`). Both produced an empty BH-significant set,
identical to the primary seed's empty set - seed-invariance HOLDS. Full
table in `reports/event_study_btc.md`'s "Seed invariance" section.

**Scope note:** the Spearman IC bootstrap (`orderflow.config.IC_BOOTSTRAP_REPS`
= 10,000, unchanged) was deliberately left out of this amendment - it is an
unvectorized per-rep computation (unlike the now-batched, vectorized mean
bootstrap), and preregistration section 6.2 itself states it is
"informational only - never a gating criterion," so the precision this
amendment targets (protecting a gating decision from Monte Carlo noise)
does not apply to it. `eventstudy.cell_stats`'s new `ic_n_reps` parameter
implements this decoupling; existing call sites that omit it are unaffected
(`ic_n_reps` defaults to `n_reps`, the prior behavior).

## Entry 2 (2026-07-03): Circular-shift placebo (additive, non-gating supplement)

**What was added:** for each signal's deduplicated BTC in-sample event set,
a circular-shift placebo test (`orderflow.stats.circular_shift_placebo`,
K=10,000 shifts per signal, seeded deterministically) - one random offset
per shift applied to all of that signal's event bar-indices simultaneously,
wrapping within the IS bar range, offset uniform over
{2016, ..., N_IS_bars-2016} to forbid near-identity alignment. Full
methodology in `reports/event_study_btc.md`'s "Circular-shift placebo"
section.

**Why:** circular shifting preserves the entire return series, so
unconditional drift (e.g. bull-market beta) sits inside the null - this
tests event-return *alignment* net of market beta, a failure channel the
multiplicity-corrected day-cluster bootstrap does not isolate by itself.

**Does not affect:** gates, promotion, or BH-FDR, which remain frozen on
the day-cluster bootstrap table in section "Cells" of
`reports/event_study_btc.md`. Not counted in the DSR trial count N=140
(`reports/FINAL_REPORT.md` section 3) - it is a post-hoc diagnostic over an
already-fixed, already-not-promoted event set, not a draw from the
promotion search DSR corrects for.

**Placebo-vs-bootstrap agreement, reported verbatim per instruction (not
reconciled, not reinterpreted, not re-run):** most cells show placebo p
broadly consistent with bootstrap raw p (both small or both large
together). Two cells disagree qualitatively - bootstrap raw p comfortably
non-significant while placebo p crosses the conventional (uncorrected,
non-gating) 0.05 line:

| Signal | Horizon (bars) | Bootstrap raw p | Placebo p |
|---|---|---|---|
| H6 | 6 | 0.1980 | 0.0168 |
| H6 | 12 | 0.3121 | 0.0371 |

Two further cells show the same direction of disagreement without crossing
0.05 on either side (both already in the "smallest p in the table"
neighborhood on both tests): H1 h=6 (bootstrap 0.0100 vs placebo 0.0047)
and H1 h=12 (bootstrap 0.0109 vs placebo 0.0058). Neither disagreement
changes any gate, promotion, or BH-FDR outcome - both remain non-gating,
uncorrected, single-cell readings. No explanation for the H6 divergence
specifically is offered here, per instruction; a hypothesis-generating
observation for a future pre-registered study, not a finding of this one.

**Final sweep (Phase 5, after Phase 3 + sensitivity grid completed):**
confirmed no locked definition in PREREGISTRATION.md changed after
sign-off. Several process items surfaced during Phase 2 QA and the Phase
3 review round that might look deviation-adjacent at a glance are
deliberately NOT logged here, because none of them altered a frozen
statistical or signal definition:

- The warm-up-funnel question raised during review (why exactly 10
  events were cut at the bar_index>=8640 boundary) confirmed the warm-up
  rule was applied correctly and uniformly; no event before bar_index
  8640 reached the final event set. Investigation and explanation are in
  `reports/event_study_btc.md`'s "Warm-up clarification" note, not here,
  because nothing was changed.
- The AGG_PARTIAL_GAP -> AGG_STALE_REVISION relabeling in
  `reports/QA_SUMMARY.md` was a label correction for an already-accurate
  repair (the underlying data fix was correct from the start; only its
  root-cause description was wrong). Data-hygiene documentation, not a
  study-definition change.
- The quarantine mechanism (`src/orderflow/quarantine.py`) handles a data
  anomaly (a confirmed exchange-side gap on 2022-09-06) that the original
  prereg did not anticipate by name, but implements exactly the prereg's
  own look-ahead-prevention and "signals use only completed bars"
  principles applied to a case the general rule already covered. It does
  not change any signal formula, gate, horizon, or threshold.
- The reproducibility fix to the bootstrap seed (`orderflow.stats.
  stable_seed`, replacing Python's per-process-randomized `hash()`)
  changed the exact p-value/CI of every cell by a small amount (bootstrap
  noise), but did not change any pre-registered statistical METHOD - the
  day-cluster bootstrap procedure itself is unchanged, only its
  previously-nondeterministic seed. No qualitative conclusion changed
  (0 of 20 cells were BH-significant before and after the fix).

All four are documented in detail in `reports/QA_SUMMARY.md`,
`reports/event_study_btc.md`, and this project's commit history, per the
"honest reporting" principle - just not here, since DEVIATIONS.md is
specifically reserved for changes to locked pre-registered definitions,
and none occurred.
