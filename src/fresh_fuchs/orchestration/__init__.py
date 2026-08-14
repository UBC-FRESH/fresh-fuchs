"""Orchestration and evidence (Phase 5).

Freshforge workflow + matrix definitions for the FUCHS pipeline
(build-model -> scenario-run -> policy-grid -> policy-rank) and the policy
grid, plus evidence manifests and provenance records for every run.
"""

from .matrix import load_fuchs_matrix, run_fuchs_matrix
from .workflow import (
    PROVIDER_ID,
    PROVIDER_VERSION,
    FuchsOrchestrationProvider,
    fuchs_provider_factory,
    fuchs_registry,
    fuchs_workflow_spec,
    run_fuchs_workflow,
)

__all__ = [
    "PROVIDER_ID",
    "PROVIDER_VERSION",
    "FuchsOrchestrationProvider",
    "fuchs_provider_factory",
    "fuchs_registry",
    "fuchs_workflow_spec",
    "load_fuchs_matrix",
    "run_fuchs_matrix",
    "run_fuchs_workflow",
]
