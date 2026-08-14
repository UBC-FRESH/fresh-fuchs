"""Full-MC scenario engine.

Generates disturbance (fire) scenarios — occurrence/extent/severity from
MFRI-by-zone burn rates — and, later, correlated wood-price realizations.
Distribution registry (Gaussian first; empirical bootstrap via nemora
later) with seed control for reproducibility. Produces
``DisturbanceScenario`` records.

Phase 3 scope. Stub in Phase 0.
"""

from __future__ import annotations

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

__all__ = [
    "ANNUAL_BURN_RATE_BY_ZONE",
    "DEFAULT_BURNED_DECAY_RATE",
    "DEFAULT_SEVERITY",
    "MFRI_YEARS_BY_ZONE",
    "SEVERITY_TO_BURNED_FRAC",
    "FireDynamicsError",
    "FireYearState",
    "UnknownBurnRateError",
    "annual_burn_rate",
    "annual_burn_rate_for_stratum",
    "bec_zone_from_stratum",
    "burn_influx",
    "burned_volume_after",
    "live_volume_after",
    "load_burn_rate_by_au",
    "period_burn_probability",
    "salvageable_volume",
    "severity_burned_fraction",
    "simulate_cohort_years",
]
