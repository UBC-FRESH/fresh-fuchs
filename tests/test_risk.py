"""Risk metrics tests (P4.3): analytic checks, monotonicity, records."""

from __future__ import annotations

import math

import numpy as np
import pytest

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.outer import (
    GaussianComparison,
    PolicyGrid,
    RiskReport,
    conditional_value_at_risk,
    expected_npv,
    gaussian_tail_metrics,
    npv_volatility,
    risk_report,
    risk_reports_from_grid,
    run_grid,
    shortfall_probability,
    value_at_risk,
)

P = Provenance(source="test", as_of="T0", units="multiplier", basis="test risk")


def test_expected_and_volatility_analytic() -> None:
    sample = [1.0, 2.0, 3.0, 4.0]
    assert expected_npv(sample) == pytest.approx(2.5)
    # sample std, ddof=1
    assert npv_volatility(sample) == pytest.approx(math.sqrt(5.0 / 3.0))


def test_value_at_risk_inverted_cdf_analytic() -> None:
    sample = list(range(1, 101))  # 1..100
    assert value_at_risk(sample, 0.95) == pytest.approx(95.0)
    assert value_at_risk(sample, 0.5) == pytest.approx(50.0)
    assert value_at_risk(sample, 0.05) == pytest.approx(5.0)


def test_conditional_value_at_risk_worst_tail_analytic() -> None:
    sample = list(range(1, 101))  # 1..100
    # alpha=0.95 -> worst floor(0.05*100)=5 observations: mean(1..5) = 3.0
    assert conditional_value_at_risk(sample, 0.95) == pytest.approx(3.0)
    # alpha=0.99 -> worst 1 observation: 1.0
    assert conditional_value_at_risk(sample, 0.99) == pytest.approx(1.0)


def test_cvar_floor_one_on_small_samples() -> None:
    sample = [10.0, 20.0]
    assert conditional_value_at_risk(sample, 0.95) == pytest.approx(10.0)


def test_shortfall_probability_analytic() -> None:
    sample = list(range(1, 101))  # 1..100
    assert shortfall_probability(sample, 10.0) == pytest.approx(0.09)
    assert shortfall_probability(sample, 1.0) == pytest.approx(0.0)
    assert shortfall_probability(sample, 101.0) == pytest.approx(1.0)


def test_cvar_monotone_in_alpha_and_below_expectation() -> None:
    rng = np.random.default_rng(0)
    sample = rng.normal(100.0, 20.0, 500).tolist()
    mean = expected_npv(sample)
    previous = math.inf
    for alpha in (0.80, 0.90, 0.95, 0.99):
        cvar = conditional_value_at_risk(sample, alpha)
        assert cvar <= previous  # tighter tail -> lower mean (non-increasing)
        assert cvar <= mean
        previous = cvar


def test_var_cvar_gaussian_analytic() -> None:
    sample = list(range(1, 101))  # mean 50.5, sample std ddof=1 = 29.0115...
    comparison = gaussian_tail_metrics(sample, 0.95, provenance=P)
    assert comparison.fitted_mean == pytest.approx(50.5)
    assert comparison.fitted_std == pytest.approx(29.011491975882016)
    from fresh_fuchs.outer.risk import _normal_quantile

    z = _normal_quantile(0.95)
    assert z == pytest.approx(1.6448536269514722, rel=1e-9)
    phi_z = math.exp(-(z**2) / 2.0) / math.sqrt(2.0 * math.pi)
    assert comparison.value_at_risk == pytest.approx(50.5 + 29.011491975882016 * z)
    assert comparison.conditional_value_at_risk == pytest.approx(
        50.5 - 29.011491975882016 * phi_z / (1.0 - 0.95)
    )


def test_risk_report_record_shape() -> None:
    from fresh_fuchs.outer import PolicyRecord

    policy = PolicyRecord(
        name="p",
        composition_targets=(),
        harvest_policy=None,
        provenance=P,
    )
    report = risk_report(
        policy,
        [100.0, 90.0, 110.0, 80.0],
        alpha=0.95,
        shortfall_threshold=85.0,
        provenance=P,
    )
    assert isinstance(report, RiskReport)
    assert isinstance(report.gaussian, GaussianComparison)
    assert report.n == 4
    assert report.alpha == 0.95
    assert report.metrics.expected_npv == pytest.approx(95.0)
    assert report.metrics.shortfall_probability == pytest.approx(0.25)  # {80} < 85
    assert report.policy.name == "p"


def test_risk_reports_from_grid(tmp_path) -> None:
    from fresh_fuchs.economy import interior_surface
    from fresh_fuchs.instance import InstanceConfig
    from fresh_fuchs.instance.species import SpeciesClass
    from fresh_fuchs.instance.woodstock import write_woodstock_files
    from fresh_fuchs.outer import CompositionGridAxis
    from fresh_fuchs.scenario.distributions import (
        DistributionFamily,
        ParameterDistribution,
        UncertaintyDimension,
        UncertaintyVector,
    )
    from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY
    from fresh_fuchs.scenario.records import ScenarioGenerationParams, generate_scenarios
    from tests.conftest import build_synthetic_areas, build_synthetic_yields

    config = InstanceConfig(
        model_name="synthetic",
        model_path=tmp_path,
        horizon=2,
        period_length=10,
        max_age=300,
        min_harvest_age=60,
    )
    write_woodstock_files(
        areas=build_synthetic_areas(), yields=build_synthetic_yields(), config=config
    )
    species_by_dtk = {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }
    vector = UncertaintyVector(
        distributions={
            UncertaintyDimension.FIRE_BURN_RATE: ParameterDistribution(
                name="burn_rate_multiplier",
                family=DistributionFamily.GAUSSIAN,
                provenance=P,
                mean=1.0,
                std=0.2,
            ),
            UncertaintyDimension.PRICE: ParameterDistribution(
                name="price_factor",
                family=DistributionFamily.FIXED,
                provenance=P,
                value=1.0,
            ),
        }
    )
    params = ScenarioGenerationParams(
        n_scenarios=3,
        master_seed=7,
        horizon=2,
        period_length=10,
        zone_burn_rates={"IDF": 0.005, "SBPS": 0.01},
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=P,
    )
    grid = PolicyGrid(
        name="g",
        composition_axes=(
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.85,),
                tolerance=0.05,
                provenance=P,
            ),
        ),
        include_unconstrained=True,
        provenance=P,
    )
    record = run_grid(
        grid=grid,
        scenarios=generate_scenarios(params),
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au={1: "SBPS", 2: "IDF"},
        max_initial_age=300,
    )
    reports = risk_reports_from_grid(record, alpha=0.95, shortfall_threshold=1e6, provenance=P)
    assert len(reports) == record.n_policies
    for report in reports:
        assert report.n == 3
        assert report.metrics.alpha == 0.95
        assert report.metrics.expected_npv > 0
        assert report.metrics.conditional_value_at_risk <= report.metrics.expected_npv
        assert report.metrics.conditional_value_at_risk <= report.metrics.value_at_risk
