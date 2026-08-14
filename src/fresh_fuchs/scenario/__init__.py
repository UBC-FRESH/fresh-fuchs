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
    "MFRI_YEARS_BY_ZONE",
    "MissingDependencyError",
    "ParameterDistribution",
    "SEVERITY_TO_BURNED_FRAC",
    "ScenarioGenerationParams",
    "UncertaintyDimension",
    "UncertaintyVector",
    "UnknownBurnRateError",
    "FireDynamicsError",
    "FireYearState",
    "annual_burn_rate",
    "annual_burn_rate_for_stratum",
    "bec_zone_from_stratum",
    "build_scenario",
    "burn_influx",
    "burned_volume_after",
    "draw_vector",
    "generate_scenarios",
    "live_volume_after",
    "load_burn_rate_by_au",
    "nemora_sample_distribution",
    "period_burn_probability",
    "salvageable_volume",
    "sample_distribution",
    "severity_burned_fraction",
    "simulate_cohort_years",
    "write_scenario_catalogue",
]
