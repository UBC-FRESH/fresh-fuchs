Quickstart
==========

The fastest end-to-end path is a smoke build and baseline run on the tsa29mini
bundle (3 periods instead of the production 30)::

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

The build prints the development-type count, total area (~90,499 ha), and the
managed land base after the retention split (35,083.0 ha). The baseline run
solves the volume-max even-flow LP on the managed land base and runs the
oldest-first heuristic, writing per-period results when ``--out`` is given.

Swap ``--horizon 30`` for the production run (slow; tens of minutes to a few
hours depending on the machine). Outputs land under ``outputs/`` and are
git-ignored working material.
