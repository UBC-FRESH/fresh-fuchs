"""Phase 4 acceptance tests (P4.5): end-to-end outer policy layer.

Full sequence P4.1-P4.4 on the public-safe synthetic bundle: grid
definition -> full-MC evaluation (fire scenarios through the inner LP with
policy rows) -> risk metrics -> ranking/report. Verifies reproducibility,
the CVaR-vs-expected-NPV trade-off across the grid, and the recommended
policy.
"""

from __future__ import annotations

from pathlib import Path

from fresh_fuchs.economy import interior_surface
from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.instance import InstanceConfig
from fresh_fuchs.instance.species import SpeciesClass
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.outer import (
    CompositionGridAxis,
    HarvestGridAxis,
    PolicyGrid,
    RankingCriterion,
    build_report,
    rank_policies,
    risk_reports_from_grid,
    run_grid,
    write_grid_record,
    write_report,
)
from fresh_fuchs.outer.records import HarvestPolicyMode
from fresh_fuchs.scenario.distributions import (
    DistributionFamily,
    ParameterDistribution,
    UncertaintyDimension,
    UncertaintyVector,
)
from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY
from fresh_fuchs.scenario.records import ScenarioGenerationParams, generate_scenarios

P = Provenance(source="test", as_of="T0", units="multiplier", basis="P4 acceptance")

ZONE_RATES = {"IDF": 0.005, "SBPS": 0.01}

ZONE_BY_AU = {1: "SBPS", 2: "IDF"}

MASTER_SEED = 2026
N_SCENARIOS = 5


def _species_map() -> dict:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


def _scenarios() -> list:
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
        n_scenarios=N_SCENARIOS,
        master_seed=MASTER_SEED,
        horizon=2,
        period_length=10,
        zone_burn_rates=ZONE_RATES,
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=P,
    )
    return generate_scenarios(params)


def _model_context(tmp_path: Path):
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
    return config, _species_map()


def _grid() -> PolicyGrid:
    return PolicyGrid(
        name="p4_acceptance",
        composition_axes=(
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.85, 0.9),
                tolerance=0.05,
                provenance=P,
            ),
        ),
        harvest_axis=HarvestGridAxis(
            mode=HarvestPolicyMode.ROTATION_CONSTRAINTS,
            species=SpeciesClass.LODGEPOLE_PINE,
            values=(60.0,),  # non-binding floor (= min_harvest_age); exercises the path
            provenance=P,
        ),
        include_unconstrained=True,
        provenance=P,
    )


def _evaluate(tmp_path: Path):
    config, species_by_dtk = _model_context(tmp_path)
    record = run_grid(
        grid=_grid(),
        scenarios=_scenarios(),
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
    )
    reports = risk_reports_from_grid(record, alpha=0.95, provenance=P)
    ranking = rank_policies(reports, provenance=P)
    return record, reports, ranking


def test_p4_end_to_end_reproducible(tmp_path: Path) -> None:
    """The full grid -> risk -> ranking sequence is seed-fixed reproducible.

    ``run_at``/``environment`` metadata is expected to differ between
    invocations; the NPV samples and the derived ranking must not.
    """
    first_record, _, first_ranking = _evaluate(tmp_path)
    second_record, _, second_ranking = _evaluate(tmp_path)
    for a, b in zip(first_record.results, second_record.results, strict=True):
        assert a.policy == b.policy
        assert a.status == b.status == "ok"
        assert a.npv_samples == b.npv_samples
    assert first_ranking.model_dump(mode="json") == second_ranking.model_dump(mode="json")
    assert first_record.n_policies == 3
    assert all(r.status == "ok" for r in first_record.results)


def test_p4_cvar_expected_tradeoff_and_recommendation(tmp_path: Path) -> None:
    """Tighter PL composition lowers both E[NPV] and CVaR; baseline is top.

    On this grid the constraints monotonically trade off both expected NPV
    and the worst tail away from the unconstrained optimum, so the E_NPV
    ranking is also the CVaR ranking, and CVaR(0.95) <= E[NPV] for every
    policy.
    """
    _record, reports, ranking = _evaluate(tmp_path)
    names = [r.policy.name for r in ranking.rankings]
    assert names[0] == "p4_acceptance_unconstrained"
    assert names[-1] == "p4_acceptance_PL_0.90_PL_floor_60"
    assert ranking.recommended.policy.name == names[0]
    assert ranking.recommended.rank == 1

    expected = [r.report.metrics.expected_npv for r in ranking.rankings]
    cvar = [r.report.metrics.conditional_value_at_risk for r in ranking.rankings]
    assert expected == sorted(expected, reverse=True)
    assert cvar == sorted(cvar, reverse=True)
    for r in ranking.rankings:
        assert r.report.metrics.conditional_value_at_risk <= r.report.metrics.expected_npv
    assert expected[0] > expected[-1]
    assert cvar[0] > cvar[-1]


def test_p4_pure_cvar_ranking_differs_from_expected(tmp_path: Path) -> None:
    """Pure-CVaR (mean-cvar weight 0) ranks by the worst tail."""
    _record, reports, _ranking = _evaluate(tmp_path)
    by_cvar = rank_policies(reports, criterion=RankingCriterion.MEAN_CVAR, weight=0.0, provenance=P)
    ordered = sorted(reports, key=lambda r: r.metrics.conditional_value_at_risk, reverse=True)
    assert [r.policy.name for r in by_cvar.rankings] == [r.policy.name for r in ordered]


def test_p4_reports_and_records_written(tmp_path: Path) -> None:
    """Grid records and the ranking report are written end-to-end."""
    config, species_by_dtk = _model_context(tmp_path)
    record = run_grid(
        grid=_grid(),
        scenarios=_scenarios(),
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=ZONE_BY_AU,
        max_initial_age=300,
    )
    grid_dir = tmp_path / "grid"
    written_grid = write_grid_record(record, grid_dir)
    assert (grid_dir / "grid_summary.csv").exists()
    assert (grid_dir / "grid_summary.json").exists()

    reports = risk_reports_from_grid(record, alpha=0.95, provenance=P)
    ranking = rank_policies(reports, provenance=P)
    report = build_report(ranking, name="p4_acceptance", provenance=P)
    out = tmp_path / "report"
    written_report = write_report(report, out)
    assert (out / "ranking.csv").exists()
    assert (out / "ranking.json").exists()
    assert (out / "report.json").exists()
    assert all(path.exists() for path in written_grid + written_report)
