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

Remaining stubs land with their roadmap phases:

- ``scenario-run`` — generate full-MC scenarios (Phase 3).
- ``inner-run`` — solve the inner Model I LP (Phases 2-3).
- ``outer-run`` — evaluate policies on NPV distributions (Phase 4).
- ``pipeline-run`` — run the end-to-end pipeline (Phase 5).

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
