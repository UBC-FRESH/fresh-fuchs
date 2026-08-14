"""FreshForge matrix integration for the FUCHS policy grid (Phase 5, P5.1).

A ``WorkflowMatrixSpec`` expands the pipeline workflow template over the
policy-grid axes (e.g., composition-target values, AAC levels) via
``${matrix.<var>}`` substitution, and ``run_fuchs_matrix`` executes every
case with the FUCHS provider registry and writes a matrix evidence
manifest.
"""

from __future__ import annotations

from pathlib import Path

from freshforge.evidence import matrix_run_evidence_manifest, write_evidence_manifest
from freshforge.matrix import (
    WorkflowMatrixRunResult,
    WorkflowMatrixSpec,
    load_workflow_matrix,
    run_workflow_matrix,
)
from freshforge.records import Diagnostic

from fresh_fuchs.orchestration.workflow import fuchs_registry


def load_fuchs_matrix(path: str | Path) -> tuple[WorkflowMatrixSpec, tuple[Diagnostic, ...]]:
    """Load and validate a FUCHS matrix document; raise on error diagnostics."""
    from freshforge.validation import has_error_diagnostics

    matrix, diagnostics = load_workflow_matrix(path)
    if matrix is None or has_error_diagnostics(diagnostics):
        messages = "; ".join(f"{d.code}: {d.message}" for d in diagnostics)
        raise ValueError(f"invalid FUCHS matrix document '{path}': {messages}")
    return matrix, tuple(diagnostics)


def run_fuchs_matrix(
    matrix: WorkflowMatrixSpec | str | Path,
    *,
    workdir: str | Path,
    evidence_path: str | Path | None = None,
    fail_fast: bool = False,
) -> WorkflowMatrixRunResult:
    """Run every case of a FUCHS matrix with the FUCHS provider registry.

    Accepts a ``WorkflowMatrixSpec`` or a path to a matrix YAML/JSON document.
    Writes a matrix evidence manifest when ``evidence_path`` is given.
    """
    import freshforge

    if isinstance(matrix, (str, Path)):
        source_path = Path(matrix)
        spec, diagnostics = load_fuchs_matrix(source_path)
    else:
        source_path = matrix.source_path or matrix.id
        spec = matrix
        diagnostics = ()

    workdir_path = Path(workdir)
    result = run_workflow_matrix(
        spec,
        diagnostics=diagnostics,
        registry=fuchs_registry(),
        workdir=workdir_path,
        fail_fast=fail_fast,
    )
    if evidence_path is not None:
        manifest = matrix_run_evidence_manifest(
            source_path=source_path,
            workdir=workdir_path,
            result=result,
            freshforge_version=freshforge.__version__,
        )
        write_evidence_manifest(evidence_path, manifest)
    return result


__all__ = [
    "load_fuchs_matrix",
    "run_fuchs_matrix",
]
