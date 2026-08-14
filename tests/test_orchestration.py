"""Orchestration tests (P5.1): freshforge provider, workflow, matrix, evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("freshforge")

from freshforge.records import RunStatus, WorkflowNode

from fresh_fuchs.orchestration import (
    PROVIDER_ID,
    FuchsOrchestrationProvider,
    fuchs_registry,
    fuchs_workflow_spec,
    load_fuchs_matrix,
    run_fuchs_matrix,
    run_fuchs_workflow,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_provider_metadata_and_registry() -> None:
    provider = FuchsOrchestrationProvider()
    metadata = provider.metadata()
    assert metadata.id == PROVIDER_ID
    assert {nt.id for nt in metadata.node_types} == {
        "build_model",
        "scenario_run",
        "policy_grid",
        "policy_rank",
    }
    registry = fuchs_registry()
    for node_type in ("build_model", "scenario_run", "policy_grid", "policy_rank"):
        resolution = registry.resolve(f"{PROVIDER_ID}.{node_type}")
        assert resolution.provider_available
        assert resolution.node_type_available


def test_workflow_spec_topology() -> None:
    spec = fuchs_workflow_spec(horizon=2, n_scenarios=3)
    assert spec.id == "fuchs_pipeline"
    ids = [n.id for n in spec.nodes]
    assert ids == ["build_model", "scenario_run", "policy_grid", "policy_rank"]
    by_id = {n.id: n for n in spec.nodes}
    assert by_id["scenario_run"].needs == ("build_model",)
    assert by_id["policy_grid"].needs == ("build_model",)
    assert by_id["policy_rank"].needs == ("policy_grid",)


def test_validate_node_missing_grid() -> None:
    provider = FuchsOrchestrationProvider()
    node_type = next(nt for nt in provider.metadata().node_types if nt.id == "policy_grid")
    node = WorkflowNode(id="g", provider=f"{PROVIDER_ID}.policy_grid")
    diagnostics = provider.validate_node(node, node_type, location="nodes.g")
    assert any(d.code == "node.parameters.missing" for d in diagnostics)
    # With the grid parameter present, validation is clean.
    ok_node = WorkflowNode(
        id="g",
        provider=f"{PROVIDER_ID}.policy_grid",
        parameters={"grid": {"name": "g"}},
    )
    assert provider.validate_node(ok_node, node_type, location="nodes.g") == ()


def test_run_fuchs_workflow_end_to_end(tmp_path: Path) -> None:
    spec = fuchs_workflow_spec(horizon=2, n_scenarios=3, master_seed=7)
    evidence = tmp_path / "evidence.json"
    result = run_fuchs_workflow(spec, workdir=tmp_path, evidence_path=evidence)
    assert result.ok
    assert result.status is RunStatus.SUCCESS
    assert {n.id for n in result.nodes} == {
        "build_model",
        "scenario_run",
        "policy_grid",
        "policy_rank",
    }
    rank = next(n for n in result.nodes if n.id == "policy_rank")
    assert "recommended" in rank.outputs

    manifest = json.loads(evidence.read_text())
    assert manifest["manifest_version"] == "freshforge.workflow-run-evidence.v1"
    assert manifest["workflow_id"] == "fuchs_pipeline"
    assert manifest["status"] == "success"
    # Artifacts landed under the workdir.
    assert (tmp_path / "policy_grid" / "grid_summary.json").exists()
    assert (tmp_path / "policy_rank" / "ranking.csv").exists()


def test_run_fuchs_workflow_reproducible(tmp_path: Path) -> None:
    spec = fuchs_workflow_spec(horizon=2, n_scenarios=3, master_seed=11)
    first = run_fuchs_workflow(spec, workdir=tmp_path / "a")
    second = run_fuchs_workflow(spec, workdir=tmp_path / "b")
    # NPV means per scenario_run node must match bit-for-bit (seed-fixed).
    first_run = next(n for n in first.nodes if n.id == "scenario_run")
    second_run = next(n for n in second.nodes if n.id == "scenario_run")
    assert first_run.outputs["npv_mean"] == second_run.outputs["npv_mean"]


def test_load_fuchs_matrix_and_run(tmp_path: Path) -> None:
    matrix, diagnostics = load_fuchs_matrix(EXAMPLES / "fuchs_matrix.yaml")
    assert matrix.id == "fuchs_grid_matrix"
    evidence = tmp_path / "matrix_evidence.json"
    result = run_fuchs_matrix(matrix, workdir=tmp_path, evidence_path=evidence)
    assert result.ok
    summary = result.summary()
    assert summary.case_count == 2
    assert summary.succeeded_count == 2
    # Each case ran the full pipeline in its own namespace.
    for case in result.cases:
        assert case.run is not None and case.run.ok
        rank = next(n for n in case.run.nodes if n.id == "policy_rank")
        assert rank.outputs["recommended"].startswith("fuchs_matrix_PL_")
        case_dir = tmp_path / case.namespace
        assert (case_dir / "policy_grid" / "grid_summary.json").exists()
        assert (case_dir / "policy_rank" / "ranking.csv").exists()
    manifest = json.loads(evidence.read_text())
    assert manifest["manifest_version"] == "freshforge.matrix-run-evidence.v1"
    assert manifest["matrix_id"] == "fuchs_grid_matrix"
    assert manifest["status"] == "success"


def test_load_fuchs_matrix_rejects_invalid(tmp_path: Path) -> None:
    import pytest

    bad = tmp_path / "bad.yaml"
    bad.write_text("matrix:\n  id: 123_NOT_SLUG\n  workflow_template: x.yaml\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid FUCHS matrix document"):
        load_fuchs_matrix(bad)
