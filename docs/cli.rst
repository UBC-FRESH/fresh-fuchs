Command Line Reference
======================

The CLI is a thin wrapper over the Python APIs. Commands that have landed:

- ``version`` — print the package version (Phase 0).
- ``build-model`` — build the extended ws3 model from a femic bundle
  (Phase 1).
- ``baseline-run`` — run the volume-max even-flow LP and the oldest-first
  heuristic baselines on a built model (Phase 1).
- ``species-composition`` — report the managed-land-base species composition
  by static primary-species class (Phase 1, re-scoped P1.3).
- ``economy-run`` — solve the NPV-max even-flow LP on a built model using the
  interior economic surface (Phase 2).
- ``scenario-run`` — generate a seed-fixed full-MC scenario catalogue and
  solve the inner LP once per scenario (Phase 3).
- ``policy-grid`` — run the outer policy grid search over the scenario
  catalogue (Phase 4).
- ``policy-rank`` — rank a grid run record by the risk criterion and write
  the report (Phase 4).

Reserved stubs (post-v0.1.0a1; see ``ROADMAP.md``):

- ``inner-run`` — solve a single inner Model I LP (superseded by
  ``scenario-run``/``policy-grid``, which already solve the inner LP per
  scenario).
- ``outer-run`` — single-policy evaluation (superseded by ``policy-grid``).
- ``pipeline-run`` — convenience end-to-end wrapper (superseded by the
  freshforge workflow/matrix orchestration in ``fresh_fuchs.orchestration``).

``build-model``
---------------

Build the ws3 ``ForestModel`` from a femic bundle: reads the bundle tables
(``au_table.csv``, ``curve_table.csv``, ``curve_points_table.csv``) and the
fragment shapefile, applies the Patchworks proportional-retention split, and
writes Woodstock-format sections before loading them into ws3.

.. code-block:: bash

   fresh-fuchs build-model \
     --bundle-dir <bundle>/data/model_input_bundle \
     --fragments <bundle>/output/patchworks_tsa29mini/fragments/fragments.shp \
     --model-path outputs/tsa29mini/ws3_woodstock_bootstrap_model \
     --horizon 30

Options:

- ``--bundle-dir`` — directory with the bundle CSV tables (required).
- ``--fragments`` — fragments shapefile path (required).
- ``--model-path`` — output directory for the Woodstock-format sections.
- ``--horizon`` — number of periods (default 30).

Exit status is nonzero if ``femic``/``geopandas`` are unavailable or any
required input is missing.

``baseline-run``
----------------

Run the deterministic baselines on an already-built model directory: the
volume-max even-flow LP (harvest volume per period within 5% of period 1 on
the managed land base) and the oldest-first priority-queue heuristic.

.. code-block:: bash

   fresh-fuchs baseline-run \
     --model-path outputs/tsa29mini/ws3_woodstock_bootstrap_model \
     --max-initial-age 436 \
     --horizon 30 \
     --out outputs/tsa29mini/baseline_30.csv

Options:

- ``--model-path`` — directory with the Woodstock-format sections.
- ``--model-name`` — model name used as the section-file prefix.
- ``--max-initial-age`` — oldest initial stand age in the bundle (drives
  null-action operability across the full horizon).
- ``--horizon`` — number of periods.
- ``--out`` — optional CSV of per-period results for both baselines.

``species-composition``
-----------------------

Report the managed-land-base species composition by static primary-species
class. Species classes come from each AU's ``canfi_species`` code in
``au_table.csv`` (tsa29mini: 100 = spruce ``SX``, 204 = lodgepole pine
``PL``, 500 = Douglas-fir ``FD``; unknown codes map to ``OT``). The ws3 model
itself stays species-free (five themes); composition is computed from the
post-split area records.

.. code-block:: bash

   fresh-fuchs species-composition \
     --bundle-dir <bundle>/data/model_input_bundle \
     --fragments <bundle>/output/patchworks_tsa29mini/fragments/fragments.shp

Options:

- ``--bundle-dir`` — directory with the bundle CSV tables (required).
- ``--fragments`` — fragments shapefile path (required).
- ``--ageclass-width`` — age-class width for midpoint bucketing (default 10).

``economy-run``
---------------

Solve the NPV-max even-flow LP on an already-built model directory. The
objective maximizes discounted net revenue (sawlog-basis green net revenue
per m3 by species price group; per-ha replant cost not charged by default
because the $45/m3 harvest cost carries the silviculture allocation) subject
to the same harvest-volume even-flow band as the volume-max baseline. Prints
the LP status, harvest anchors, and the SPF/Df-Larch salvage-margin anchors
(zero subsidy, sawlog basis). Requires ``femic``/``geopandas`` to derive the
species mapping from the bundle.

.. code-block:: bash

   fresh-fuchs economy-run \
     --bundle-dir <bundle>/data/model_input_bundle \
     --fragments <bundle>/output/patchworks_tsa29mini/fragments/fragments.shp \
     --model-path outputs/tsa29mini/ws3_woodstock_bootstrap_model \
     --max-initial-age 436 \
     --horizon 30 \
     --out outputs/tsa29mini/npv_30.csv

Options:

- ``--bundle-dir`` — directory with the bundle CSV tables (required).
- ``--fragments`` — fragments shapefile path (required).
- ``--model-path`` — directory with the Woodstock-format sections.
- ``--model-name`` — model name used as the section-file prefix.
- ``--max-initial-age`` — oldest initial stand age in the bundle.
- ``--horizon`` — number of periods.
- ``--out`` — optional CSV of per-period results.

``scenario-run``
----------------

Generate a seed-fixed full-MC fire/price scenario catalogue from the bundle
zones' MFRI annual burn rates and solve the fire-aware even-flow/NPV LP once
per scenario (full foresight), writing a run record with provenance (JSON +
per-period schedule CSVs + summary).

.. code-block:: bash

   fresh-fuchs scenario-run \
     --bundle-dir <bundle>/data/model_input_bundle \
     --fragments <bundle>/output/patchworks_tsa29mini/fragments/fragments.shp \
     --model-path outputs/tsa29mini/ws3_woodstock_bootstrap_model \
     --max-initial-age 436 \
     --horizon 30 \
     --n-scenarios 10 \
     --master-seed 42 \
     --workers 4 \
     --out-dir outputs/tsa29mini/scenario_run

Options:

- ``--bundle-dir`` / ``--fragments`` — bundle inputs (required).
- ``--model-path`` / ``--model-name`` — built model directory / name.
- ``--max-initial-age`` — oldest initial stand age.
- ``--horizon`` — number of periods.
- ``--n-scenarios`` — catalogue size (default 10).
- ``--master-seed`` — seed fixing the catalogue (default 42); runs are
  bit-reproducible for a fixed seed.
- ``--workers`` — process-pool size for the per-scenario solves (spawn
  start method; parallel results bit-match sequential).
- ``--out-dir`` — directory for the run record.

``policy-grid``
---------------

Run the outer policy grid search (Phase 4): expand a ``PolicyGrid`` JSON
into its Cartesian product (plus an optional unconstrained baseline),
evaluate every policy over the seed-fixed scenario catalogue through the
inner LP with the policy rows applied, and write per-policy run records and
grid summaries. Infeasible grid points are captured as ``status="failed"``
without sinking the grid.

.. code-block:: bash

   fresh-fuchs policy-grid \
     --bundle-dir <bundle>/data/model_input_bundle \
     --fragments <bundle>/output/patchworks_tsa29mini/fragments/fragments.shp \
     --model-path outputs/tsa29mini/ws3_woodstock_bootstrap_model \
     --grid-json examples/policy-grid.tsa29mini.json \
     --max-initial-age 436 \
     --horizon 30 \
     --n-scenarios 10 \
     --master-seed 42 \
     --scenario-workers 4 \
     --policy-workers 2 \
     --out-dir outputs/tsa29mini/policy_grid

Options:

- ``--grid-json`` — ``PolicyGrid`` definition (JSON; see
  ``examples/policy-grid.tsa29mini.json``) (required).
- ``--scenario-workers`` / ``--policy-workers`` — nested process pools.
- ``--out-dir`` — directory for grid records (``grid_summary.csv`` /
  ``grid_summary.json`` + per-policy runs).
- The bundle/model/seed options match ``scenario-run``.

``policy-rank``
---------------

Rank a grid run record by the risk criterion and write the report
(``ranking.csv`` / ``ranking.json`` / ``report.json``, plus ``tradeoff.png``
when matplotlib is importable). Reads a ``grid_summary.json`` from
``policy-grid``; optionally takes a fine-resolution grid for the
coarse-vs-fine sensitivity record.

.. code-block:: bash

   fresh-fuchs policy-rank \
     --grid-summary outputs/tsa29mini/policy_grid/grid_summary.json \
     --criterion expected_npv_cvar \
     --alpha 0.95 \
     --out-dir outputs/tsa29mini/policy_rank

Options:

- ``--grid-summary`` — grid run record from ``policy-grid`` (required).
- ``--fine-grid-summary`` — optional finer grid for the sensitivity record.
- ``--criterion`` — ``expected_npv_cvar`` (lexicographic E[NPV] then CVaR)
  or ``mean_cvar`` (weighted score).
- ``--weight`` — E[NPV] weight for ``mean_cvar`` (default 0.5).
- ``--alpha`` — CVaR/VaR level (default 0.95).
- ``--out-dir`` — directory for the ranking report.

Orchestration (freshforge)
--------------------------

The whole pipeline is also wrapped as a freshforge workflow/matrix with
evidence manifests (Phase 5, ``fresh_fuchs.orchestration``). See
``examples/fuchs_workflow_template.yaml`` and ``examples/fuchs_matrix.yaml``;
the provider runs on the public-safe synthetic instance so it is CI-safe.
This requires the ``orchestration`` extra (``pip install -e
".[orchestration]"``).
