Architecture
============

(Under construction — Phase 0.)

Module map (see ``planning/v0.1.0a1-plan.md`` section 2 for the data flow
and per-phase scope):

- ``fresh_fuchs.instance`` — femic tsa29mini bundle -> extended ws3 model
  (Phase 1).
- ``fresh_fuchs.economy`` — NPV surface: revenue, harvest costs (fhops),
  replanting costs, salvage economics, discounting (Phase 2).
- ``fresh_fuchs.scenario`` — full-MC fire/price scenario engine with a
  distribution registry (Phase 3).
- ``fresh_fuchs.inner`` — per-scenario Model I LP (NPV max) and the
  oldest-first heuristic baseline (Phases 2-3).
- ``fresh_fuchs.outer`` — policy config, grid search, NPV-distribution risk
  metrics (Phase 4).
- ``fresh_fuchs.orchestration`` — freshforge workflows/matrices and evidence
  (Phase 5).

Design invariants:

- Reuse, never re-implement: ws3, femic, fhops, nemora, freshforge,
  fresh-salvage anchors.
- CLI commands are thin wrappers over Python APIs.
- Typed records at boundaries; linear inner problem (continuous LP).
- Provenance on every input, formulation, seed, and result.
