Architecture
============

Module map (see ``planning/v0.1.0a1-plan.md`` section 2 for the data flow
and per-phase scope):

- ``fresh_fuchs.instance`` — femic tsa29mini bundle -> extended ws3 model:
  bundle context and Woodstock tables via ``femic.fmg``, the Patchworks
  retention split, Woodstock-format section writer, ws3 ``ForestModel``
  bootstrap (null action, horizon-long operability), and the deterministic
  baselines (volume-max even-flow LP and oldest-first heuristic).
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

The ``instance`` bridge in detail
---------------------------------

``build-model`` and the ``instance`` API follow the reference tsa29mini
pipeline (``profile_ws3_evenflow.py`` and the demo notebook in the
``femic-tsa29mini-instance`` bundle):

1. ``fresh_fuchs.instance.bundle.load_bundle_context`` builds the femic
   analysis-unit / curve context from the bundle CSVs.
2. ``fresh_fuchs.instance.bundle.build_woodstock_tables`` produces the
   long-format yields/actions/transitions frames via
   ``femic.fmg.woodstock``.
3. ``fresh_fuchs.instance.bundle.apply_retention_split`` mirrors the
   Patchworks proportional-retention split (managed fragment area is split
   ``1 - RETENTION`` managed / ``RETENTION`` unmanaged).
4. ``fresh_fuchs.instance.woodstock.write_woodstock_files`` writes the
   ``.lan/.are/.yld/.act/.trn`` sections; ``bootstrap_model`` loads them
   into ``ws3.forest.ForestModel`` (base 2026, 30 x 10-yr, max age 300,
   min harvest age 60).
5. ``fresh_fuchs.instance.woodstock.prepare_optimization`` adds the null
   action with operability extended to ``max_initial_age +
   horizon * period_length`` so unharvested stands age through the full
   horizon.
6. ``fresh_fuchs.instance.baseline`` defines the volume-max even-flow LP
   (per-period harvest volume within 5% of period 1, managed land base) and
   the oldest-first priority-queue heuristic.

Only the femic source dependency is required for real-bundle builds;
synthetic fixtures exercise the same path without femic/geopandas.

