"""Instance and model integration (Phase 1).

Builds the extended ws3 ``ForestModel`` from a femic bundle: bundle tables ->
Woodstock sections (``femic.fmg.woodstock``) + retention split -> ws3
``ForestModel``, and runs the deterministic baselines (volume-max even-flow
LP and oldest-first heuristic) that anchor later phases.

Reference implementation: the tsa29mini demo notebook and
``profile_ws3_evenflow.py`` in the ``femic-tsa29mini-instance`` bundle.
"""

from __future__ import annotations

import ws3.forest

from .baseline import (
    add_even_flow_problem,
    run_oldest_first_heuristic,
    solve_even_flow,
    summarize,
)
from .bundle import (
    MissingDependencyError,
    age_to_midpoint,
    apply_retention_split,
    build_woodstock_tables,
    load_bundle_context,
    load_fragments,
    managed_area_ha,
)
from .types import BaselineConfig, InstanceConfig
from .woodstock import bootstrap_model, prepare_optimization, write_woodstock_files

__all__ = [
    "BaselineConfig",
    "InstanceConfig",
    "MissingDependencyError",
    "add_even_flow_problem",
    "age_to_midpoint",
    "apply_retention_split",
    "build_model",
    "build_woodstock_tables",
    "bootstrap_model",
    "load_bundle_context",
    "load_fragments",
    "managed_area_ha",
    "prepare_optimization",
    "run_oldest_first_heuristic",
    "solve_even_flow",
    "summarize",
    "write_woodstock_files",
]


def build_model(config: InstanceConfig) -> tuple[ws3.forest.ForestModel, dict[str, object]]:
    """Build the ws3 ``ForestModel`` from a real bundle end-to-end.

    Requires ``config.fragments_path``. Returns the bootstrapped model and a
    provenance/summary dictionary (table row counts, managed land base).
    """
    if config.fragments_path is None or config.bundle_dir is None:
        raise ValueError(
            "InstanceConfig.bundle_dir and InstanceConfig.fragments_path are "
            "required to build from a bundle"
        )

    context = load_bundle_context(bundle_dir=config.bundle_dir, tsa_list=config.tsa_list)
    tables = build_woodstock_tables(context=context)
    fragments = load_fragments(config.fragments_path)
    areas = apply_retention_split(fragments, ageclass_width=config.ageclass_width)

    written = write_woodstock_files(areas=areas, yields=tables["yields"], config=config)
    model = bootstrap_model(config)

    return model, {
        "analysis_units": len(context.analysis_units),
        "curves": len(context.curves_by_id),
        "yield_rows": len(tables["yields"]),
        "area_records": len(areas),
        "fragments": len(fragments),
        "distinct_initial_ages": int(areas["age"].nunique()),
        "max_initial_age": int(areas["age"].max()),
        "total_area_ha": float(model.inventory(period=0)),
        "managed_area_ha": managed_area_ha(areas),
        "files": [str(path) for path in written],
        "horizon": config.horizon,
    }
