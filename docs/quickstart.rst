Quickstart
==========

Two paths: a **CI-safe synthetic** end-to-end run (no private data) and the
**real-bundle** pipeline on the tsa29mini instance.

Synthetic end-to-end (no private data)
--------------------------------------

The public-safe synthetic instance (``fresh_fuchs.instance.synthetic``)
exercises the whole pipeline — model build, full-MC scenarios, per-scenario
inner LP, policy grid, and CVaR ranking — with no annex bundle:

.. code-block:: bash

   pip install -e ".[dev,orchestration]"

.. code-block:: python

   from fresh_fuchs.orchestration import fuchs_workflow_spec, run_fuchs_workflow

   spec = fuchs_workflow_spec(horizon=2, n_scenarios=3, master_seed=42)
   result = run_fuchs_workflow(spec, workdir="outputs/synthetic", evidence_path="outputs/synthetic/evidence.json")
   assert result.ok
   for node in result.nodes:
       print(node.id, node.status, node.outputs)

Or via the policy API directly (grid -> risk -> ranking):

.. code-block:: python

   from pathlib import Path
   from fresh_fuchs.economy import interior_surface
   from fresh_fuchs.economy.types import Provenance
   from fresh_fuchs.instance.synthetic import (
       SYNTHETIC_ZONE_BY_AU, build_synthetic_model, synthetic_species_by_dtk,
   )
   from fresh_fuchs.outer import (
       CompositionGridAxis, PolicyGrid, rank_policies, risk_reports_from_grid, run_grid,
   )
   from fresh_fuchs.scenario.records import ScenarioGenerationParams, generate_scenarios
   # ... build the synthetic model, generate scenarios, run the grid, rank ...

Real-bundle pipeline
--------------------

The fastest real-bundle path is a smoke build and baseline run on the
tsa29mini bundle (3 periods instead of the production 30)::

   pip install -e ".[dev,bundle]"

   B=/path/to/femic-tsa29mini-instance

   fresh-fuchs build-model \
     --bundle-dir "$B/data/model_input_bundle" \
     --fragments "$B/output/patchworks_tsa29mini/fragments/fragments.shp" \
     --model-path outputs/tsa29mini/ws3_woodstock_bootstrap_model \
     --horizon 3

   fresh-fuchs baseline-run \
     --model-path outputs/tsa29mini/ws3_woodstock_bootstrap_model \
     --max-initial-age 436 \
     --horizon 3 \
     --out outputs/tsa29mini/baseline_smoke.csv

Then the stochastic pipeline (full-MC scenarios -> inner LP per scenario)::

   fresh-fuchs scenario-run \
     --bundle-dir "$B/data/model_input_bundle" \
     --fragments "$B/output/patchworks_tsa29mini/fragments/fragments.shp" \
     --model-path outputs/tsa29mini/ws3_woodstock_bootstrap_model \
     --max-initial-age 436 --horizon 3 \
     --n-scenarios 5 --master-seed 42 --workers 1 \
     --out-dir outputs/tsa29mini/scenario_run

and the outer policy grid + ranking::

   fresh-fuchs policy-grid \
     --bundle-dir "$B/data/model_input_bundle" \
     --fragments "$B/output/patchworks_tsa29mini/fragments/fragments.shp" \
     --model-path outputs/tsa29mini/ws3_woodstock_bootstrap_model \
     --grid-json examples/policy-grid.tsa29mini.json \
     --max-initial-age 436 --horizon 3 \
     --n-scenarios 5 --master-seed 42 \
     --out-dir outputs/tsa29mini/policy_grid

   fresh-fuchs policy-rank \
     --grid-summary outputs/tsa29mini/policy_grid/grid_summary.json \
     --criterion expected_npv_cvar --alpha 0.95 \
     --out-dir outputs/tsa29mini/policy_rank

The build prints the development-type count, total area (~90,499 ha), and the
managed land base after the retention split (35,083.0 ha). The baseline run
solves the volume-max even-flow LP on the managed land base and runs the
oldest-first heuristic, writing per-period results when ``--out`` is given.

Swap ``--horizon 30`` for the production run (slow; tens of minutes to a few
hours depending on the machine, and the per-scenario fire LP scales with the
horizon). Outputs land under ``outputs/`` and are git-ignored working
material. The bundle paths come from config and are never tracked in the repo.
