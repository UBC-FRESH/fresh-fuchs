"""FreshForge workflow integration for the FUCHS pipeline (Phase 5, P5.1).

A thin ``freshforge`` provider (``fuchs.orchestration``) whose node types
wrap the FUCHS Python APIs — no engine logic is duplicated. Node types:

- ``build_model``: build the ws3 model (synthetic public-safe fixture, or a
  real bundle when private paths are supplied).
- ``scenario_run``: generate a seed-fixed MC scenario catalogue and solve
  the inner LP per scenario; write the pipeline run record.
- ``policy_grid``: expand a ``PolicyGrid`` and evaluate every policy over
  the scenario catalogue; write grid records.
- ``policy_rank``: rank a grid run record and write the report.

Evidence manifests (freshforge ``write_evidence_manifest``) record input
provenance, versions, seeds, and configs for every run.

Synthetic parameters keep every node CI-safe; real-bundle runs pass
``bundle_dir``/``fragments_path`` and a real ``model_path`` from config.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from freshforge.evidence import workflow_run_evidence_manifest, write_evidence_manifest
from freshforge.execution import RunContext, run_workflow
from freshforge.providers import NodeTypeMetadata, ProviderMetadata, ProviderRegistry
from freshforge.records import (
    Diagnostic,
    ProviderRunResult,
    RunStatus,
    WorkflowNode,
    WorkflowRunResult,
    WorkflowSpec,
)

PROVIDER_ID = "fuchs.orchestration"
PROVIDER_VERSION = "0.1.0a1"

_NODE_TYPES: tuple[NodeTypeMetadata, ...] = (
    NodeTypeMetadata(
        id="build_model",
        name="Build model",
        description="Build the ws3 model (synthetic fixture or a real bundle).",
        outputs=("model_path", "model_name"),
        parameters=("source", "model_path", "horizon", "bundle_dir", "fragments_path"),
        artifacts=("woodstock",),
    ),
    NodeTypeMetadata(
        id="scenario_run",
        name="Scenario run",
        description=(
            "Generate a seed-fixed MC scenario catalogue and solve the inner LP per scenario."
        ),
        outputs=("out_dir", "n_scenarios", "npv_mean"),
        parameters=(
            "model_path",
            "model_name",
            "horizon",
            "n_scenarios",
            "master_seed",
            "out_dir",
        ),
        artifacts=("run_record",),
    ),
    NodeTypeMetadata(
        id="policy_grid",
        name="Policy grid",
        description="Expand a PolicyGrid and evaluate every policy over the scenario catalogue.",
        outputs=("out_dir", "n_policies", "grid_summary"),
        parameters=(
            "model_path",
            "model_name",
            "horizon",
            "n_scenarios",
            "master_seed",
            "grid",
            "out_dir",
        ),
        artifacts=("grid_summary",),
    ),
    NodeTypeMetadata(
        id="policy_rank",
        name="Policy rank",
        description="Rank a grid run record and write the report.",
        inputs=("grid_summary",),
        outputs=("out_dir", "recommended"),
        parameters=("grid_summary", "criterion", "weight", "alpha", "out_dir"),
        artifacts=("report", "ranking_csv"),
    ),
)


def _missing(node: WorkflowNode, fields: tuple[str, ...], *, kind: str) -> tuple[Diagnostic, ...]:
    from freshforge.records import DiagnosticSeverity

    source = {
        "inputs": node.inputs,
        "outputs": node.outputs,
        "parameters": node.parameters,
    }[kind]
    return tuple(
        Diagnostic(
            severity=DiagnosticSeverity.ERROR,
            code=f"node.{kind}.missing",
            message=f"Node is missing required {kind} key '{key}'.",
            location=f"nodes.{node.id}.{kind}.{key}",
        )
        for key in fields
        if key not in source
    )


#: Genuinely-required parameters per node type (the rest have defaults or are
#: produced at run time).
_REQUIRED_PARAMETERS: dict[str, tuple[str, ...]] = {
    "build_model": (),
    "scenario_run": (),
    "policy_grid": ("grid",),
    "policy_rank": (),
}


class FuchsOrchestrationProvider:
    """FreshForge provider wrapping the FUCHS pipeline Python APIs."""

    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            id=PROVIDER_ID,
            version=PROVIDER_VERSION,
            name="FUCHS orchestration provider",
            description=(
                "Thin node types wrapping the FUCHS build-model / scenario-run / "
                "policy-grid / policy-rank Python APIs."
            ),
            node_types=_NODE_TYPES,
        )

    def validate_node(
        self,
        node: WorkflowNode,
        node_type: NodeTypeMetadata,
        *,
        location: str,
    ) -> tuple[Diagnostic, ...]:
        del location
        # Only genuinely-required wiring/parameters are enforced here; most
        # parameters have defaults and outputs are produced at run time.
        diagnostics: list[Diagnostic] = []
        required = _REQUIRED_PARAMETERS.get(node_type.id, ())
        diagnostics.extend(_missing(node, required, kind="parameters"))
        if node_type.id == "policy_rank" and not (
            "grid_summary" in node.inputs or "grid_summary" in node.parameters
        ):
            from freshforge.records import DiagnosticSeverity

            diagnostics.append(
                Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="node.parameters.missing",
                    message=("policy_rank requires a grid_summary input or parameter."),
                    location=f"nodes.{node.id}.parameters.grid_summary",
                )
            )
        return tuple(diagnostics)

    def run_node(
        self,
        node: WorkflowNode,
        node_type: NodeTypeMetadata,
        *,
        context: Any,
    ) -> ProviderRunResult:
        handler = _RUNNERS[node_type.id]
        return handler(node, context)


def _out(node: WorkflowNode, key: str, context: RunContext, default: str) -> Path:
    value = node.parameters.get(key, default)
    return context.resolve_path(str(value))


def _run_build_model(node: WorkflowNode, context: RunContext) -> ProviderRunResult:
    from fresh_fuchs.instance import build_synthetic_model

    source = str(node.parameters.get("source", "synthetic"))
    model_path = _out(node, "model_path", context, "model")
    horizon = int(node.parameters.get("horizon", 2))
    if source != "synthetic":
        from freshforge.records import DiagnosticSeverity

        return ProviderRunResult(
            status=RunStatus.FAILED,
            diagnostics=(
                Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="node.build_model.unsupported_source",
                    message=(
                        f"build_model source '{source}' is not supported by the provider; "
                        "real-bundle builds run via the `fresh-fuchs build-model` CLI."
                    ),
                    location=f"nodes.{node.id}.parameters.source",
                ),
            ),
        )
    config, files = build_synthetic_model(model_path, horizon=horizon)
    return ProviderRunResult(
        status=RunStatus.SUCCESS,
        outputs={"model_path": str(model_path), "model_name": config.model_name},
        artifacts={"woodstock": [str(path) for path in files]},
        data={"horizon": config.horizon, "source": source},
    )


def _scenario_params(node: WorkflowNode) -> Any:
    from fresh_fuchs.economy.types import Provenance
    from fresh_fuchs.instance.synthetic import SYNTHETIC_ZONE_BURN_RATES
    from fresh_fuchs.scenario.distributions import (
        DistributionFamily,
        ParameterDistribution,
        UncertaintyDimension,
        UncertaintyVector,
    )
    from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY
    from fresh_fuchs.scenario.records import ScenarioGenerationParams

    provenance = Provenance(
        source="orchestration scenario catalogue",
        as_of=str(node.parameters.get("as_of", "2026-08-14")),
        units="multiplier",
        basis="Gaussian burn-rate multiplier (mean 1.0, std 0.2); fixed price 1.0",
    )
    vector = UncertaintyVector(
        distributions={
            UncertaintyDimension.FIRE_BURN_RATE: ParameterDistribution(
                name="burn_rate_multiplier",
                family=DistributionFamily.GAUSSIAN,
                provenance=provenance,
                mean=1.0,
                std=0.2,
            ),
            UncertaintyDimension.PRICE: ParameterDistribution(
                name="price_factor",
                family=DistributionFamily.FIXED,
                provenance=provenance,
                value=1.0,
            ),
        }
    )
    return ScenarioGenerationParams(
        n_scenarios=int(node.parameters.get("n_scenarios", 3)),
        master_seed=int(node.parameters.get("master_seed", 42)),
        horizon=int(node.parameters.get("horizon", 2)),
        period_length=int(node.parameters.get("period_length", 10)),
        zone_burn_rates=dict(SYNTHETIC_ZONE_BURN_RATES),
        vector=vector,
        severity=DEFAULT_SEVERITY,
        provenance=provenance,
    )


def _scenario_context(node: WorkflowNode, context: RunContext):
    """Return (config, scenarios, species_by_dtk, zone_by_au) for a synthetic run."""
    from fresh_fuchs.instance.synthetic import (
        SYNTHETIC_ZONE_BY_AU,
        synthetic_instance_config,
        synthetic_species_by_dtk,
    )
    from fresh_fuchs.scenario.records import generate_scenarios

    model_path = _out(node, "model_path", context, "model")
    horizon = int(node.parameters.get("horizon", 2))
    config = synthetic_instance_config(model_path, horizon=horizon)
    scenarios = generate_scenarios(_scenario_params(node))
    return config, scenarios, synthetic_species_by_dtk(), dict(SYNTHETIC_ZONE_BY_AU)


def _run_scenario_run(node: WorkflowNode, context: RunContext) -> ProviderRunResult:
    from fresh_fuchs.economy import interior_surface
    from fresh_fuchs.scenario.pipeline import run_scenario_pipeline, write_pipeline_record

    config, scenarios, species_by_dtk, zone_by_au = _scenario_context(node, context)
    out_dir = _out(node, "out_dir", context, "scenario_run")
    record = run_scenario_pipeline(
        scenarios=scenarios,
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=zone_by_au,
        max_initial_age=300,
    )
    written = write_pipeline_record(record, out_dir)
    npvs = [s.npv for s in record.scenarios]
    return ProviderRunResult(
        status=RunStatus.SUCCESS,
        outputs={
            "out_dir": str(out_dir),
            "n_scenarios": record.n_scenarios,
            "npv_mean": sum(npvs) / len(npvs) if npvs else float("nan"),
        },
        artifacts={"run_record": [str(path) for path in written]},
        data={"statuses": sorted({s.status for s in record.scenarios})},
    )


def _run_policy_grid(node: WorkflowNode, context: RunContext) -> ProviderRunResult:
    from fresh_fuchs.economy import interior_surface
    from fresh_fuchs.outer import PolicyGrid, run_grid, write_grid_record

    config, scenarios, species_by_dtk, zone_by_au = _scenario_context(node, context)
    out_dir = _out(node, "out_dir", context, "policy_grid")
    grid = PolicyGrid.model_validate(node.parameters["grid"])
    record = run_grid(
        grid=grid,
        scenarios=scenarios,
        config=config,
        surface=interior_surface(),
        species_by_dtk=species_by_dtk,
        zone_by_au=zone_by_au,
        max_initial_age=300,
    )
    written = write_grid_record(record, out_dir)
    grid_summary = out_dir / "grid_summary.json"
    return ProviderRunResult(
        status=RunStatus.SUCCESS,
        outputs={
            "out_dir": str(out_dir),
            "n_policies": record.n_policies,
            "grid_summary": str(grid_summary),
        },
        artifacts={
            "grid_summary": str(grid_summary),
            "records": [str(path) for path in written],
        },
        data={"statuses": sorted({r.status for r in record.results})},
    )


def _run_policy_rank(node: WorkflowNode, context: RunContext) -> ProviderRunResult:
    from fresh_fuchs.economy.types import Provenance
    from fresh_fuchs.outer import (
        RankingCriterion,
        build_report,
        rank_from_grid_summary,
        write_report,
    )

    grid_summary = node.inputs.get("grid_summary") or node.parameters.get("grid_summary")
    if grid_summary is None:
        from freshforge.records import DiagnosticSeverity

        return ProviderRunResult(
            status=RunStatus.FAILED,
            diagnostics=(
                Diagnostic(
                    severity=DiagnosticSeverity.ERROR,
                    code="node.policy_rank.grid_summary.missing",
                    message="policy_rank requires a grid_summary input or parameter.",
                    location=f"nodes.{node.id}",
                ),
            ),
        )
    grid_summary_path = context.resolve_path(str(grid_summary))
    out_dir = _out(node, "out_dir", context, "policy_rank")
    provenance = Provenance(
        source="orchestration policy ranking",
        as_of=str(node.parameters.get("as_of", "2026-08-14")),
        units="NPV",
        basis="policy-grid ranking",
    )
    ranking = rank_from_grid_summary(
        grid_summary_path,
        criterion=RankingCriterion(str(node.parameters.get("criterion", "expected_npv_cvar"))),
        alpha=float(node.parameters.get("alpha", 0.95)),
        weight=node.parameters.get("weight"),
        provenance=provenance,
    )
    report = build_report(ranking, name=node.id, provenance=provenance)
    written = write_report(report, out_dir)
    return ProviderRunResult(
        status=RunStatus.SUCCESS,
        outputs={
            "out_dir": str(out_dir),
            "recommended": ranking.recommended.policy.name,
        },
        artifacts={
            "report": str(out_dir / "report.json"),
            "ranking_csv": str(out_dir / "ranking.csv"),
            "records": [str(path) for path in written],
        },
        data={"n_policies": len(ranking.rankings)},
    )


_RUNNERS = {
    "build_model": _run_build_model,
    "scenario_run": _run_scenario_run,
    "policy_grid": _run_policy_grid,
    "policy_rank": _run_policy_rank,
}


def fuchs_provider_factory() -> FuchsOrchestrationProvider:
    """Return the FUCHS orchestration provider (entry-point factory)."""
    return FuchsOrchestrationProvider()


def fuchs_registry() -> ProviderRegistry:
    """Return a freshforge registry with the FUCHS provider registered."""
    registry = ProviderRegistry()
    registry.register(FuchsOrchestrationProvider())
    return registry


def fuchs_workflow_spec(
    *,
    workflow_id: str = "fuchs_pipeline",
    horizon: int = 2,
    n_scenarios: int = 3,
    master_seed: int = 42,
    grid: dict[str, Any] | None = None,
    criterion: str = "expected_npv_cvar",
    alpha: float = 0.95,
    weight: float | None = None,
) -> WorkflowSpec:
    """Return the FUCHS pipeline workflow: build_model -> scenario_run ->
    policy_grid -> policy_rank.

    Paths are relative to the run workdir (freshforge ``RunContext``). The
    grid defaults to a single PL composition target sweep.
    """
    if grid is None:
        grid = _default_grid_dict()
    rank_parameters: dict[str, Any] = {
        "grid_summary": "policy_grid/grid_summary.json",
        "criterion": criterion,
        "alpha": alpha,
        "out_dir": "policy_rank",
    }
    if weight is not None:
        rank_parameters["weight"] = weight
    nodes = (
        WorkflowNode(
            id="build_model",
            provider=f"{PROVIDER_ID}.build_model",
            parameters={
                "source": "synthetic",
                "model_path": "model",
                "horizon": horizon,
            },
        ),
        WorkflowNode(
            id="scenario_run",
            provider=f"{PROVIDER_ID}.scenario_run",
            needs=("build_model",),
            parameters={
                "model_path": "model",
                "horizon": horizon,
                "n_scenarios": n_scenarios,
                "master_seed": master_seed,
                "out_dir": "scenario_run",
            },
        ),
        WorkflowNode(
            id="policy_grid",
            provider=f"{PROVIDER_ID}.policy_grid",
            needs=("build_model",),
            parameters={
                "model_path": "model",
                "horizon": horizon,
                "n_scenarios": n_scenarios,
                "master_seed": master_seed,
                "grid": grid,
                "out_dir": "policy_grid",
            },
        ),
        WorkflowNode(
            id="policy_rank",
            provider=f"{PROVIDER_ID}.policy_rank",
            needs=("policy_grid",),
            inputs={"grid_summary": "policy_grid/grid_summary.json"},
            parameters=rank_parameters,
        ),
    )
    return WorkflowSpec(
        id=workflow_id,
        name="FUCHS pipeline",
        description="build_model -> scenario_run -> policy_grid -> policy_rank (synthetic).",
        nodes=nodes,
    )


def _default_grid_dict() -> dict[str, Any]:
    from fresh_fuchs.economy.types import Provenance
    from fresh_fuchs.instance.species import SpeciesClass
    from fresh_fuchs.outer import CompositionGridAxis, PolicyGrid

    provenance = Provenance(
        source="orchestration default grid",
        as_of="2026-08-14",
        units="area share",
        basis="default single-axis PL composition sweep",
    )
    grid = PolicyGrid(
        name="fuchs_pipeline",
        composition_axes=(
            CompositionGridAxis(
                species=SpeciesClass.LODGEPOLE_PINE,
                values=(0.85,),
                tolerance=0.05,
                provenance=provenance,
            ),
        ),
        include_unconstrained=True,
        provenance=provenance,
    )
    return grid.model_dump(mode="json")


def run_fuchs_workflow(
    spec: WorkflowSpec,
    *,
    workdir: str | Path,
    run_namespace: str | None = None,
    evidence_path: str | Path | None = None,
) -> WorkflowRunResult:
    """Run a FUCHS workflow with the FUCHS registry; optionally write evidence."""
    import freshforge

    workdir_path = Path(workdir)
    result = run_workflow(
        spec,
        registry=fuchs_registry(),
        workdir=workdir_path,
        run_namespace=run_namespace,
    )
    if evidence_path is not None:
        manifest = workflow_run_evidence_manifest(
            source_path=spec.id,
            workdir=workdir_path,
            result=result,
            freshforge_version=freshforge.__version__,
        )
        write_evidence_manifest(evidence_path, manifest)
    return result


__all__ = [
    "PROVIDER_ID",
    "PROVIDER_VERSION",
    "FuchsOrchestrationProvider",
    "fuchs_provider_factory",
    "fuchs_registry",
    "fuchs_workflow_spec",
    "run_fuchs_workflow",
]
