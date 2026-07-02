# Deviations from Pre-Registration

This log records any change to a locked definition in
[`PREREGISTRATION.md`](PREREGISTRATION.md) made **after** it was signed off
("prereg approved"). Each entry states what changed, why it was unavoidable,
and what would have happened if the original definition had been kept. Every
entry here must also be flagged in the final `README.md`.

No entries.

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
