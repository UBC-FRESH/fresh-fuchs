"""MC convergence study (P5.2): how many scenarios stabilize CVaR.

Runs the scenario -> inner-LP pipeline on the public-safe synthetic
instance at increasing catalogue sizes and records the CVaR(0.95) and
E[NPV] convergence of the unconstrained-policy NPV distribution. The
recorded curve is transcribed into `planning/validation-report.md`.
"""

from __future__ import annotations

from pathlib import Path

from fresh_fuchs.economy import interior_surface
from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.instance.synthetic import (
    SYNTHETIC_ZONE_BURN_RATES,
    SYNTHETIC_ZONE_BY_AU,
    build_synthetic_model,
    synthetic_species_by_dtk,
)
from fresh_fuchs.outer import conditional_value_at_risk, expected_npv
from fresh_fuchs.scenario.distributions import (
    DistributionFamily,
    ParameterDistribution,
    UncertaintyDimension,
    UncertaintyVector,
)
from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY
from fresh_fuchs.scenario.pipeline import run_scenario_pipeline
from fresh_fuchs.scenario.records import ScenarioGenerationParams, generate_scenarios

P = Provenance(source="test", as_of="T0", units="multiplier", basis="MC convergence")

NS = (5, 10, 20, 40, 80, 160, 320)


def _npv_samples(config, n: int) -> list[float]:
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
        n_scenarios=n,
        master_seed=42,
        horizon=config.horizon,
        period_length=config.period_length,
        zone_burn_rates=dict(SYNTHETIC_ZONE_BURN_RATES),
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=P,
    )
    scenarios = generate_scenarios(params)
    record = run_scenario_pipeline(
        scenarios=scenarios,
        config=config,
        surface=interior_surface(),
        species_by_dtk=synthetic_species_by_dtk(),
        zone_by_au=dict(SYNTHETIC_ZONE_BY_AU),
        max_initial_age=300,
    )
    return [s.npv for s in record.scenarios]


def _convergence_curve(tmp_path: Path) -> list[tuple[int, float, float]]:
    config, _ = build_synthetic_model(tmp_path, horizon=2)
    curve = []
    for n in NS:
        npvs = _npv_samples(config, n)
        curve.append((n, expected_npv(npvs), conditional_value_at_risk(npvs, 0.95)))
    return curve


def test_mc_cvar_converges(tmp_path: Path) -> None:
    curve = _convergence_curve(tmp_path)
    reference = curve[-1]  # n = 320
    ref_npv, ref_cvar = reference[1], reference[2]
    assert ref_cvar <= ref_npv

    # By n >= 40 the CVaR estimate is stable to < 0.5% of the n=320 value.
    tail = [row for row in curve if row[0] >= 40]
    for n, _npv, cvar in tail:
        assert abs(cvar - ref_cvar) / abs(ref_cvar) < 0.005, (
            f"CVaR at n={n} deviates {abs(cvar - ref_cvar) / abs(ref_cvar):.3%} from n=320"
        )
    # E[NPV] is stable to < 0.5% across the whole ladder.
    for n, npv, _cvar in curve:
        assert abs(npv - ref_npv) / abs(ref_npv) < 0.005

    # The whole CVaR ladder spans < 0.5% (the synthetic tail is thin: fire is
    # a low-probability event at horizon 2 on two zones, so even the smallest
    # catalogue already captures the worst tail to ~0.3%).
    cvars = [row[2] for row in curve]
    assert (max(cvars) - min(cvars)) / abs(ref_cvar) < 0.005


def test_mc_convergence_curve_deterministic(tmp_path: Path) -> None:
    # Seed-fixed catalogues reproduce the curve exactly.
    first = _convergence_curve(tmp_path / "a")
    second = _convergence_curve(tmp_path / "b")
    assert first == second
