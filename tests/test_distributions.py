"""Distribution-framework tests (P3.2): families, seeding, bit-stability."""

from __future__ import annotations

import pytest

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.scenario.distributions import (
    DistributionFamily,
    MissingDependencyError,
    ParameterDistribution,
    UncertaintyDimension,
    UncertaintyVector,
    draw_vector,
    nemora_sample_distribution,
    sample_distribution,
)

P = Provenance(source="test", as_of="T0", units="multiplier", basis="test vector")


def _dist(name: str, **kwargs) -> ParameterDistribution:
    return ParameterDistribution(name=name, provenance=P, **kwargs)


def test_fixed_family_is_deterministic() -> None:
    d = _dist("x", family=DistributionFamily.FIXED, value=1.25)
    assert sample_distribution(d) == pytest.approx(1.25)
    assert sample_distribution(d, __import__("numpy").random.default_rng(1)) == 1.25


def test_fixed_requires_value() -> None:
    with pytest.raises(ValueError):
        _dist("x", family=DistributionFamily.FIXED)


def test_gaussian_requires_mean_and_std() -> None:
    with pytest.raises(ValueError):
        _dist("x", family=DistributionFamily.GAUSSIAN, mean=1.0)
    with pytest.raises(ValueError):
        _dist("x", family=DistributionFamily.GAUSSIAN, std=0.1)
    with pytest.raises(ValueError):
        _dist("x", family=DistributionFamily.GAUSSIAN, mean=1.0, std=-1.0)


def test_empirical_requires_samples() -> None:
    with pytest.raises(ValueError):
        _dist("x", family=DistributionFamily.EMPIRICAL)
    d = _dist("x", family=DistributionFamily.EMPIRICAL, samples=(1.0, 2.0, 3.0))
    value = sample_distribution(d)
    assert value in (1.0, 2.0, 3.0)


def test_gaussian_seed_reproducibility() -> None:
    d = _dist("x", family=DistributionFamily.GAUSSIAN, mean=10.0, std=2.0)
    a = sample_distribution(d, __import__("numpy").random.default_rng(42))
    b = sample_distribution(d, __import__("numpy").random.default_rng(42))
    assert a == b
    c = sample_distribution(d, __import__("numpy").random.default_rng(43))
    assert a != c


def test_draw_vector_bit_stable_under_seed() -> None:
    vector = UncertaintyVector(
        distributions={
            UncertaintyDimension.FIRE_BURN_RATE: _dist(
                "burn_multiplier", family=DistributionFamily.FIXED, value=1.0
            ),
            UncertaintyDimension.PRICE: _dist(
                "price_factor", family=DistributionFamily.GAUSSIAN, mean=1.0, std=0.05
            ),
        }
    )
    first = draw_vector(vector, seed=7)
    second = draw_vector(vector, seed=7)
    assert first == second
    other = draw_vector(vector, seed=8)
    assert first != other
    assert first[UncertaintyDimension.FIRE_BURN_RATE] == pytest.approx(1.0)
    assert isinstance(first[UncertaintyDimension.PRICE], float)


def test_nemora_optional_diagnostic() -> None:
    with pytest.raises(MissingDependencyError):
        nemora_sample_distribution("gaussian", {"mean": 0.0, "std": 1.0}, 10, seed=1)
