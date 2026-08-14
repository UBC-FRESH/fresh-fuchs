"""Full-MC scenario engine.

Generates disturbance (fire) scenarios — occurrence/extent/severity from
MFRI-by-zone burn rates — and, later, correlated wood-price realizations.
Distribution registry (Gaussian first; empirical bootstrap via nemora
later) with seed control for reproducibility. Produces
``DisturbanceScenario`` records.

Phase 3 scope.
"""

from __future__ import annotations

from .distributions import (
    DistributionFamily,
    MissingDependencyError,
    ParameterDistribution,
    UncertaintyDimension,
    UncertaintyVector,
    draw_vector,
    nemora_sample_distribution,
    sample_distribution,
)
from .fire import (
    ANNUAL_BURN_RATE_BY_ZONE,
    DEFAULT_BURNED_DECAY_RATE,
    DEFAULT_SEVERITY,
    MFRI_YEARS_BY_ZONE,
    SEVERITY_TO_BURNED_FRAC,
    FireDynamicsError,
    FireYearState,
    UnknownBurnRateError,
    annual_burn_rate,
    annual_burn_rate_for_stratum,
    bec_zone_from_stratum,
    burn_influx,
    burned_volume_after,
    live_volume_after,
    load_burn_rate_by_au,
    period_burn_probability,
    salvageable_volume,
    severity_burned_fraction,
    simulate_cohort_years,
)
from .fire_lp import (
    FireLpConfig,
    FirePathStep,
    add_fire_problem,
    add_salvage_action,
    apply_salvage_operability,
    build_burn_prob_lookup,
    path_fire_steps,
    salvage_volumes_from_solution,
    solve_fire_lp,
)
from .pipeline import (
    PipelineRunRecord,
    ScenarioRunPeriod,
    ScenarioRunRecord,
    run_scenario_lp,
    run_scenario_pipeline,
    write_pipeline_record,
)
from .records import (
    DisturbanceScenario,
    FireEvent,
    ScenarioGenerationParams,
    build_scenario,
    generate_scenarios,
    write_scenario_catalogue,
)

__all__ = [
    "ANNUAL_BURN_RATE_BY_ZONE",
    "DEFAULT_BURNED_DECAY_RATE",
    "DEFAULT_SEVERITY",
    "DisturbanceScenario",
    "DistributionFamily",
    "FireEvent",
    "FireLpConfig",
    "FirePathStep",
    "MFRI_YEARS_BY_ZONE",
    "MissingDependencyError",
    "ParameterDistribution",
    "PipelineRunRecord",
    "SEVERITY_TO_BURNED_FRAC",
    "ScenarioGenerationParams",
    "ScenarioRunPeriod",
    "ScenarioRunRecord",
    "UncertaintyDimension",
    "UncertaintyVector",
    "UnknownBurnRateError",
    "FireDynamicsError",
    "FireYearState",
    "add_fire_problem",
    "add_salvage_action",
    "annual_burn_rate",
    "annual_burn_rate_for_stratum",
    "apply_salvage_operability",
    "bec_zone_from_stratum",
    "build_burn_prob_lookup",
    "build_scenario",
    "burn_influx",
    "burned_volume_after",
    "draw_vector",
    "generate_scenarios",
    "live_volume_after",
    "load_burn_rate_by_au",
    "nemora_sample_distribution",
    "path_fire_steps",
    "period_burn_probability",
    "run_scenario_lp",
    "run_scenario_pipeline",
    "salvage_volumes_from_solution",
    "salvageable_volume",
    "sample_distribution",
    "severity_burned_fraction",
    "simulate_cohort_years",
    "solve_fire_lp",
    "write_pipeline_record",
    "write_scenario_catalogue",
]
