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
  replanting costs, salvage economics, discounting, and the NPV objective
  wiring for the inner LP (Phase 2).
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
   ``1 - RETENTION`` managed / ``RETENTION`` unmanaged) and smashes initial
   ages to 10-year ageclass midpoints (``ageclass_width`` in
   ``InstanceConfig``) so the Model I LP stays tight.
4. ``fresh_fuchs.instance.woodstock.write_woodstock_files`` writes the
   ``.lan/.are/.yld/.act/.trn`` sections; ``bootstrap_model`` loads them
   into ``ws3.forest.ForestModel`` (base 2026, 30 x 10-yr, max age 300,
   min harvest age 60) and asserts exactly five themes — TSA, IFM, AU,
   ORIGIN, SILV_STATE (no LU/land-use theme).
5. ``fresh_fuchs.instance.woodstock.prepare_optimization`` adds the null
   action with operability extended to ``max_initial_age +
   horizon * period_length`` so unharvested stands age through the full
   horizon.
6. ``fresh_fuchs.instance.baseline`` defines the volume-max even-flow LP
   (per-period harvest volume within 5% of period 1, managed land base) and
   the oldest-first priority-queue heuristic.
7. ``fresh_fuchs.instance.species`` adds a static species classification
   (``SpeciesClass`` per AU from the ``canfi_species`` code in
   ``au_table.csv``); ``fresh_fuchs.instance.composition`` computes the
   managed-land-base species area-share composition and the species class of
   every development type. The ws3 model stays species-free (five themes),
   so the species layer never grows the model — Phase 4 composes species
   targets against this surface. The tsa29mini bundle has no age-varying
   species-proportion curves (re-scoped P1.3).

Only the femic source dependency is required for real-bundle builds;
synthetic fixtures exercise the same path without femic/geopandas.

The ``economy`` layer in detail
-------------------------------

``economy-run`` and the ``economy`` API build the NPV surface the inner LP
maximizes:

1. ``fresh_fuchs.economy.types`` holds the typed records — prices (by
   product and species price group), harvest cost, transport/stumpage,
   replanting cost, salvage economics, discount rate — each constant
   carrying a ``Provenance`` (source, as-of, units, basis, assumption flag).
   ``interior_surface()`` composes the default interior (TSA29) surface
   anchored to the fresh-salvage economics calibration (reference only) and
   the BC Interior Log Market Report Q4-2023 price levels.
2. ``fresh_fuchs.economy.cashflow`` converts harvest decisions to net
   revenue and discounted NPV (flat sawlog-basis green net revenue per m3
   for v0.1.0a1; salvage margins via the burned-price discount, cost
   premiums, and the downgrade-only grade transition).
3. ``fresh_fuchs.economy.fhops_costing`` derives an alternative machine-rate
   clearcut harvest cost through ``fhops.costing`` (Lahrsen productivity +
   rental rates, CPI-adjusted to 2024). fhops is optional: the records
   import without it and the module raises an explicit diagnostic.
4. ``fresh_fuchs.economy.npv`` wires the NPV objective into the ws3 Model I
   LP: the per-prescription objective coefficient is the discounted net
   cash flow along the path (per-period discount factors from the surface),
   while the even-flow band stays on harvest volume (the AAC proxy). With a
   zero discount rate and no price differential across species, the NPV-max
   LP reproduces the volume-max baseline exactly (verified in
   ``tests/test_npv.py``).

The default $45/m3 harvest cost already carries a road/admin/silviculture
allocation, so the per-ha replant cost is NOT charged by default
(``charge_replant_in_npv``); a later phase can switch to a
silviculture-exclusive harvest cost and flip replant charging on.

