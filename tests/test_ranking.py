"""Policy ranking and report tests (P4.4): reproducibility, sensitivity, files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.outer import (
    PolicyRanking,
    RankingCriterion,
    build_report,
    rank_policies,
    risk_report,
    write_report,
)
from fresh_fuchs.outer.records import PolicyRecord

P = Provenance(source="test", as_of="T0", units="NPV", basis="test ranking")


def _policy(name: str, npv: float, vol: float = 10.0) -> PolicyRecord:
    return PolicyRecord(name=name, composition_targets=(), harvest_policy=None, provenance=P)


def _report(name: str, npv: float, vol: float = 10.0):
    from numpy.random import default_rng

    rng = default_rng(abs(hash(name)) % (2**32))
    samples = rng.normal(npv, vol, 200).tolist()
    return risk_report(_policy(name, npv, vol), samples, alpha=0.95, provenance=P)


def test_rank_policies_lexicographic_expected_then_cvar() -> None:
    # a: high E, high CVaR; b: high E, low CVaR; c: low E
    reports = [
        risk_report(_policy("b", 100.0), [90.0, 92.0, 91.0, 89.0] * 25, alpha=0.95, provenance=P),
        risk_report(_policy("c", 80.0), [70.0, 72.0, 71.0, 69.0] * 25, alpha=0.95, provenance=P),
        risk_report(_policy("a", 100.0), [95.0, 96.0, 94.0, 97.0] * 25, alpha=0.95, provenance=P),
    ]
    ranking = rank_policies(reports, provenance=P)
    assert [r.policy.name for r in ranking.rankings] == ["a", "b", "c"]
    assert ranking.recommended.policy.name == "a"
    assert ranking.recommended.rank == 1


def test_rank_policies_mean_cvar_score() -> None:
    # hi_mean: high E[NPV] but a bad worst tail; hi_cvar: tight distribution
    reports = [
        risk_report(
            _policy("hi_mean", 105.0),
            [150.0] * 50 + [60.0] * 50,
            alpha=0.95,
            provenance=P,
        ),
        risk_report(
            _policy("hi_cvar", 95.0),
            [95.0] * 100,
            alpha=0.95,
            provenance=P,
        ),
    ]
    # weight 1.0 -> pure E[NPV]: hi_mean first; weight 0.0 -> pure CVaR: hi_cvar first
    by_mean = rank_policies(reports, criterion=RankingCriterion.MEAN_CVAR, weight=1.0, provenance=P)
    assert by_mean.recommended.policy.name == "hi_mean"
    by_cvar = rank_policies(reports, criterion=RankingCriterion.MEAN_CVAR, weight=0.0, provenance=P)
    assert by_cvar.recommended.policy.name == "hi_cvar"


def test_rank_policies_reproducible() -> None:
    reports = [
        _report("p1", 100.0, 20.0),
        _report("p2", 105.0, 30.0),
        _report("p3", 98.0, 8.0),
    ]
    first = rank_policies(reports, provenance=P)
    second = rank_policies(reports, provenance=P)
    assert [r.policy.name for r in first.rankings] == [r.policy.name for r in second.rankings]
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_rank_policies_requires_reports() -> None:
    with pytest.raises(ValueError):
        rank_policies([], provenance=P)


def test_build_report_sensitivity() -> None:
    coarse_reports = [
        risk_report(_policy("x", 100.0), [90.0] * 50, alpha=0.95, provenance=P),
        risk_report(_policy("y", 80.0), [75.0] * 50, alpha=0.95, provenance=P),
    ]
    fine_reports = [
        risk_report(_policy("y", 200.0), [190.0] * 50, alpha=0.95, provenance=P),
        risk_report(_policy("x", 100.0), [90.0] * 50, alpha=0.95, provenance=P),
    ]
    coarse = rank_policies(coarse_reports, provenance=P)
    fine = rank_policies(fine_reports, provenance=P)
    report = build_report(coarse, name="g", fine_ranking=fine, provenance=P)
    assert report.recommended == "x"
    assert report.sensitivity is not None
    assert report.sensitivity.coarse_top_policy == "x"
    assert report.sensitivity.fine_top_policy == "y"
    assert report.sensitivity.top_rank_stable is False
    assert report.sensitivity.expected_npv_delta == pytest.approx(100.0)
    assert report.sensitivity.cvar_delta == pytest.approx(100.0)


def test_write_report_emits_files(tmp_path: Path) -> None:
    reports = [
        risk_report(_policy("a", 100.0), [95.0] * 40, alpha=0.95, provenance=P),
        risk_report(_policy("b", 90.0), [85.0] * 40, alpha=0.95, provenance=P),
    ]
    ranking = rank_policies(reports, provenance=P)
    report = build_report(ranking, name="g", provenance=P)
    out = tmp_path / "report"
    written = write_report(report, out)
    assert (out / "ranking.csv").exists()
    assert (out / "ranking.json").exists()
    assert (out / "report.json").exists()
    assert all(path.exists() for path in written)
    lines = (out / "ranking.csv").read_text().splitlines()
    assert len(lines) == 3  # header + 2 policies
    assert lines[0].startswith("rank,policy")
    payload = json.loads((out / "report.json").read_text())
    assert payload["recommended"] == "a"


def test_rank_from_grid_summary_roundtrip(tmp_path: Path) -> None:
    from fresh_fuchs.outer import CompositionGridAxis, run_grid
    from fresh_fuchs.outer.grid import write_grid_record
    from tests.test_grid import _grid, _run_kw  # reuse synthetic grid helper

    kw = _run_kw(tmp_path)
    grid = _grid(
        composition_axes=(
            CompositionGridAxis(
                species="PL",
                values=(0.85, 0.9),
                tolerance=0.05,
                provenance=P,
            ),
        )
    )
    record = run_grid(grid=grid, **kw)
    out = tmp_path / "grid"
    write_grid_record(record, out)
    summary = out / "grid_summary.json"

    from fresh_fuchs.outer import rank_from_grid_summary

    ranking = rank_from_grid_summary(summary, provenance=P)
    assert isinstance(ranking, PolicyRanking)
    assert ranking.recommended.policy.name in {r.policy.name for r in record.results}
    assert len(ranking.rankings) == record.n_policies
