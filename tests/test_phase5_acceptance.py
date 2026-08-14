"""Phase 5 acceptance (P5.5): v0.1.0a1 definition-of-done, CI-safe subset.

Asserts the plan section 3 definition of done where it can be checked
without private data: the end-to-end pipeline runs from the Python API and
the freshforge orchestration, seed-fixed runs are bit-stable, the
outer/inner coupling ranks policies with a recommended policy, and the
validation + calibration reports exist. Real-bundle anchors are recorded in
`planning/validation-report.md` (not re-run in CI).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.instance.synthetic import SYNTHETIC_ZONE_BY_AU, synthetic_species_by_dtk

pytest.importorskip("freshforge")

from fresh_fuchs.economy import interior_surface
from fresh_fuchs.instance.synthetic import build_synthetic_model
from fresh_fuchs.orchestration import fuchs_workflow_spec, run_fuchs_workflow
from fresh_fuchs.outer import (
    CompositionGridAxis,
    PolicyGrid,
    rank_policies,
    risk_reports_from_grid,
    run_grid,
)
from fresh_fuchs.scenario.distributions import (
    DistributionFamily,
    ParameterDistribution,
    UncertaintyDimension,
    UncertaintyVector,
)
from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY, SEVERITY_TO_BURNED_FRAC
from fresh_fuchs.scenario.records import ScenarioGenerationParams, generate_scenarios

P = Provenance(source="test", as_of="T0", units="multiplier", basis="P5 acceptance")
REPO = Path(__file__).resolve().parent.parent


def _scenarios(n: int, seed: int = 42) -> list:
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
        master_seed=seed,
        horizon=2,
        period_length=10,
        zone_burn_rates={"SBPS": 0.01, "IDF": 0.005},
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=P,
    )
    return generate_scenarios(params)


def _grid() -> PolicyGrid:
    return PolicyGrid(
        name="p5_acceptance",
        composition_axes=(
            CompositionGridAxis(
                species="PL",
                values=(0.85, 0.9),
                tolerance=0.05,
                provenance=P,
            ),
        ),
        include_unconstrained=True,
        provenance=P,
    )


def test_dod_end_to_end_pipeline_python_api(tmp_path: Path) -> None:
    """Section 3.1 + 3.3: build -> MC -> inner LP -> NPV dist -> grid -> ranking."""
    config, _files = build_synthetic_model(tmp_path / "model", horizon=2)
    scenarios = _scenarios(5)
    record = run_grid(
        grid=_grid(),
        scenarios=scenarios,
        config=config,
        surface=interior_surface(),
        species_by_dtk=synthetic_species_by_dtk(),
        zone_by_au=dict(SYNTHETIC_ZONE_BY_AU),
        max_initial_age=300,
    )
    assert all(r.status == "ok" for r in record.results)
    reports = risk_reports_from_grid(record, alpha=0.95, provenance=P)
    ranking = rank_policies(reports, provenance=P)
    # Outer/inner coupling: a recommended (rank-1) policy is identified and
    # the unconstrained baseline out-ranks the constrained grid points.
    assert ranking.recommended.rank == 1
    assert ranking.recommended.policy.name == "p5_acceptance_unconstrained"
    for r in ranking.rankings:
        assert r.report.metrics.conditional_value_at_risk <= r.report.metrics.expected_npv


def test_dod_seed_fixed_bit_stable(tmp_path: Path) -> None:
    """Section 3.2(b): a seed-fixed MC run produces bit-stable NPVs."""
    config, _ = build_synthetic_model(tmp_path / "model", horizon=2)

    def npvs() -> list[float]:
        record = run_grid(
            grid=_grid(),
            scenarios=_scenarios(5, seed=123),
            config=config,
            surface=interior_surface(),
            species_by_dtk=synthetic_species_by_dtk(),
            zone_by_au=dict(SYNTHETIC_ZONE_BY_AU),
            max_initial_age=300,
        )
        return [s for r in record.results for s in r.npv_samples]

    assert npvs() == npvs()


def test_dod_orchestration_end_to_end(tmp_path: Path) -> None:
    """Section 3.1 + 3.6: the pipeline runs via freshforge with evidence."""
    spec = fuchs_workflow_spec(horizon=2, n_scenarios=3, master_seed=42)
    evidence = tmp_path / "evidence.json"
    result = run_fuchs_workflow(spec, workdir=tmp_path, evidence_path=evidence)
    assert result.ok
    assert evidence.exists()
    assert (tmp_path / "policy_rank" / "ranking.csv").exists()


def test_dod_reports_exist() -> None:
    """Section 3.4 + 3.5: validation and calibration records exist and are
    non-trivial."""
    validation = REPO / "planning" / "validation-report.md"
    calibration = REPO / "planning" / "economics-calibration.md"
    assert validation.exists() and validation.stat().st_size > 1000
    assert calibration.exists() and calibration.stat().st_size > 1000
    text = validation.read_text()
    for anchor in ("35,083.0", "35,451", "33,624.77", "104,462.175"):
        assert anchor in text
    cal = calibration.read_text()
    assert "fresh-salvage" in cal
    assert SEVERITY_TO_BURNED_FRAC is not None  # severity ladder is importable
