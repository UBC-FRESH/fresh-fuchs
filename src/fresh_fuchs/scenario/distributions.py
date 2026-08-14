"""Distribution framework for scenario parameters (Phase 3, P3.2).

A small registry of parameter distributions with seed control for
reproducibility. Fixed (deterministic) and Gaussian families are built in;
empirical sampling is a first-class family that draws from a provided array
(the array source is nemora in Phase 4 — ``bootstrap_inventory`` /
``pdf_to_cdf`` / ``sample_distribution``), wired through an optional-import
helper so the core module stays importable without nemora.

Scenario parameters are a vector over uncertainty dimensions (fire + price)
per the notes' "combination of disturbance and wood price" requirement; only
fire is active in v0.1.0a1.

Bit-stability: all sampling funnels through ``numpy.default_rng`` seeded per
call (or from a master seed for a full vector draw), and dimensions are
drawn in a fixed documented order.
"""

from __future__ import annotations

from enum import StrEnum

import numpy as np
from pydantic import BaseModel, Field, model_validator

from fresh_fuchs.economy.types import Provenance


class MissingDependencyError(RuntimeError):
    """Raised when an optional source dependency is not importable."""


class DistributionFamily(StrEnum):
    """Sampling family of a scenario parameter distribution."""

    FIXED = "fixed"
    GAUSSIAN = "gaussian"
    EMPIRICAL = "empirical"


class UncertaintyDimension(StrEnum):
    """Uncertainty dimensions of a scenario parameter vector.

    Only fire is active in v0.1.0a1; the price dimension is carried so the
    vector meets the notes' fire + price requirement.
    """

    FIRE_BURN_RATE = "fire_burn_rate"
    PRICE = "price"


class ParameterDistribution(BaseModel):
    """One parameter distribution, named and validated per family.

    Families:

    - ``fixed``: ``value`` returned deterministically.
    - ``gaussian``: ``mean``/``std`` -> ``rng.normal(mean, std)``.
    - ``empirical``: ``samples`` drawn uniformly with replacement.
    """

    name: str = Field(description="Dimension/parameter name (e.g. 'burn_rate_multiplier').")
    family: DistributionFamily
    provenance: Provenance
    value: float | None = Field(default=None, description="Deterministic value (fixed family).")
    mean: float | None = Field(default=None, description="Mean (gaussian family).")
    std: float | None = Field(
        default=None, ge=0, description="Standard deviation (gaussian family)."
    )
    samples: tuple[float, ...] | None = Field(
        default=None, description="Empirical array drawn with replacement (empirical family)."
    )

    @model_validator(mode="after")
    def _validate_family_fields(self) -> ParameterDistribution:
        if self.family is DistributionFamily.FIXED:
            if self.value is None:
                raise ValueError(f"fixed distribution {self.name!r} requires 'value'")
        elif self.family is DistributionFamily.GAUSSIAN:
            if self.mean is None or self.std is None:
                raise ValueError(f"gaussian distribution {self.name!r} requires 'mean' and 'std'")
        elif self.family is DistributionFamily.EMPIRICAL:
            if not self.samples:
                raise ValueError(
                    f"empirical distribution {self.name!r} requires non-empty 'samples'"
                )
        return self


class UncertaintyVector(BaseModel):
    """Scenario parameter vector over uncertainty dimensions.

    Each dimension maps to one parameter distribution; dimensions are drawn
    in a fixed documented order (declaration order) for bit-stability.
    """

    distributions: dict[UncertaintyDimension, ParameterDistribution] = Field(
        description="Dimension -> parameter distribution."
    )

    def sample(self, seed: int | None = None) -> dict[UncertaintyDimension, float]:
        """Draw one value per dimension under a seeded generator."""
        rng = np.random.default_rng(seed)
        return {dim: sample_distribution(dist, rng=rng) for dim, dist in self.distributions.items()}


def sample_distribution(
    distribution: ParameterDistribution,
    rng: np.random.Generator | None = None,
) -> float:
    """Draw a single value from a :class:`ParameterDistribution`.

    Pass an existing generator to draw multiple distributions from one seed
    (``UncertaintyVector.sample``); otherwise a fresh default generator is
    used (non-reproducible unless the caller seeds).
    """
    rng = rng or np.random.default_rng()
    family = distribution.family
    if family is DistributionFamily.FIXED:
        return float(distribution.value)
    if family is DistributionFamily.GAUSSIAN:
        return float(rng.normal(distribution.mean, distribution.std))
    if family is DistributionFamily.EMPIRICAL:
        samples = np.asarray(distribution.samples, dtype=float)
        return float(rng.choice(samples))
    raise ValueError(f"unsupported family {family!r}")  # pragma: no cover


def draw_vector(
    vector: UncertaintyVector, seed: int | None = None
) -> dict[UncertaintyDimension, float]:
    """Draw the full uncertainty vector under one seed (bit-stable)."""
    return vector.sample(seed=seed)


def nemora_sample_distribution(
    distribution: str,
    params: dict[str, float],
    size: int,
    seed: int | None = None,
) -> np.ndarray:
    """Sample an empirical/fitted distribution through nemora (optional).

    Delegates to ``nemora.sampling.sample_distribution`` with a seeded
    ``numpy.random.Generator``. Requires the ``nemora`` package; raises
    :class:`MissingDependencyError` when it is not importable.
    """
    try:
        from nemora.sampling import sample_distribution as nemora_sample
    except ImportError as exc:  # pragma: no cover - exercised via optional extra
        raise MissingDependencyError(
            "nemora is required to sample an empirical distribution; install "
            "the 'nemora' dependency or use the fixed/gaussian families."
        ) from exc
    rng = np.random.default_rng(seed)
    return nemora_sample(distribution, params, size, random_state=rng)


__all__ = [
    "DistributionFamily",
    "MissingDependencyError",
    "ParameterDistribution",
    "UncertaintyDimension",
    "UncertaintyVector",
    "draw_vector",
    "nemora_sample_distribution",
    "sample_distribution",
]
