"""Policy ranking report (Phase 4, P4.4).

Deterministic report over a ``PolicyRanking``: ranking table (JSON/CSV),
recommended policy, and — when a fine-resolution ranking is supplied — a
coarse-vs-fine grid-resolution sensitivity record. A PNG trade-off plot
(expected NPV vs CVaR) is written only when matplotlib is importable; it
is an optional diagnostic, never a required artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.outer.ranking import PolicyRanking, RankingCriterion, rank_policies
from fresh_fuchs.outer.risk import RiskReport, risk_report


class SensitivityResult(BaseModel):
    """Coarse-vs-fine grid-resolution comparison of the top rank."""

    model_config = ConfigDict(frozen=True)

    coarse_top_policy: str
    fine_top_policy: str
    top_rank_stable: bool = Field(
        description="True when the coarse and fine grids agree on the top policy."
    )
    coarse_top_expected_npv: float
    fine_top_expected_npv: float
    coarse_top_cvar: float
    fine_top_cvar: float
    expected_npv_delta: float = Field(description="Fine minus coarse E[NPV] of the top policy.")
    cvar_delta: float = Field(description="Fine minus coarse CVaR of the top policy.")


class PolicyReport(BaseModel):
    """The ranking report for one grid: ranking, recommendation, sensitivity."""

    model_config = ConfigDict(frozen=True)

    name: str
    criterion: RankingCriterion
    alpha: float
    rankings: dict[str, Any] = Field(description="PolicyRanking JSON payload.")
    recommended: str = Field(description="Name of the recommended (rank-1) policy.")
    sensitivity: SensitivityResult | None = None
    provenance: Provenance


def build_report(
    ranking: PolicyRanking,
    *,
    name: str = "policy_ranking",
    fine_ranking: PolicyRanking | None = None,
    provenance: Provenance,
) -> PolicyReport:
    """Assemble the report; ``fine_ranking`` triggers the sensitivity record."""
    sensitivity = None
    if fine_ranking is not None:
        coarse_top = ranking.recommended
        fine_top = fine_ranking.recommended
        sensitivity = SensitivityResult(
            coarse_top_policy=coarse_top.policy.name,
            fine_top_policy=fine_top.policy.name,
            top_rank_stable=coarse_top.policy.name == fine_top.policy.name,
            coarse_top_expected_npv=coarse_top.report.metrics.expected_npv,
            fine_top_expected_npv=fine_top.report.metrics.expected_npv,
            coarse_top_cvar=coarse_top.report.metrics.conditional_value_at_risk,
            fine_top_cvar=fine_top.report.metrics.conditional_value_at_risk,
            expected_npv_delta=(
                fine_top.report.metrics.expected_npv - coarse_top.report.metrics.expected_npv
            ),
            cvar_delta=(
                fine_top.report.metrics.conditional_value_at_risk
                - coarse_top.report.metrics.conditional_value_at_risk
            ),
        )
    return PolicyReport(
        name=name,
        criterion=ranking.criterion,
        alpha=ranking.alpha,
        rankings=ranking.model_dump(mode="json"),
        recommended=ranking.recommended.policy.name,
        sensitivity=sensitivity,
        provenance=provenance,
    )


def _ranking_table(ranking: PolicyRanking) -> pd.DataFrame:
    rows = []
    for ranked in ranking.rankings:
        m = ranked.report.metrics
        g = ranked.report.gaussian
        rows.append(
            {
                "rank": ranked.rank,
                "policy": ranked.policy.name,
                "score": ranked.score,
                "expected_npv": m.expected_npv,
                "npv_volatility": m.npv_volatility,
                "value_at_risk": m.value_at_risk,
                "conditional_value_at_risk": m.conditional_value_at_risk,
                "shortfall_probability": m.shortfall_probability,
                "gaussian_value_at_risk": g.value_at_risk,
                "gaussian_conditional_value_at_risk": g.conditional_value_at_risk,
            }
        )
    return pd.DataFrame(rows)


def write_report(report: PolicyReport, out_dir: Path) -> list[Path]:
    """Write ranking CSV + JSON and the report JSON.

    A ``tradeoff.png`` (expected NPV vs CVaR, annotated by policy) is
    written only when matplotlib is importable; otherwise the report is
    written without it (the PNG is an optional diagnostic).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    ranking = PolicyRanking.model_validate(report.rankings)
    table = _ranking_table(ranking)
    csv_path = out_dir / "ranking.csv"
    table.to_csv(csv_path, index=False)
    written.append(csv_path)

    ranking_json = out_dir / "ranking.json"
    ranking_json.write_text(json.dumps(report.rankings, indent=2, sort_keys=True))
    written.append(ranking_json)

    report_json = out_dir / "report.json"
    report_json.write_text(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    written.append(report_json)

    plot_path = _write_tradeoff_plot(ranking, out_dir)
    if plot_path is not None:
        written.append(plot_path)
    return written


def _write_tradeoff_plot(ranking: PolicyRanking, out_dir: Path) -> Path | None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    points = [
        (r.report.metrics.expected_npv, r.report.metrics.conditional_value_at_risk, r.policy.name)
        for r in ranking.rankings
    ]
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(
        [p[0] for p in points],
        [p[1] for p in points],
        s=40,
    )
    for expected, cvar, label in points:
        ax.annotate(label, (expected, cvar), textcoords="offset points", xytext=(6, 6), fontsize=7)
    ax.set_xlabel("Expected NPV (CAD)")
    ax.set_ylabel(f"CVaR({ranking.alpha:.0%}) (CAD)")
    ax.set_title("Policy trade-off: expected NPV vs CVaR")
    fig.tight_layout()
    path = out_dir / "tradeoff.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def rank_from_grid_summary(
    grid_summary_path: Path,
    *,
    criterion: RankingCriterion = RankingCriterion.E_NPV_CVAR,
    alpha: float = 0.95,
    weight: float | None = None,
    shortfall_threshold: float | None = None,
    provenance: Provenance,
) -> PolicyRanking:
    """Recompute a ranking from a ``policy-grid`` ``grid_summary.json``.

    The summary stores each grid point's policy spec and NPV samples, so
    the ranking is fully reproducible without re-running the grid.
    """
    from fresh_fuchs.outer.records import PolicyRecord

    payload = json.loads(grid_summary_path.read_text())
    reports: list[RiskReport] = []
    for entry in payload["results"]:
        if entry["status"] != "ok" or not entry["npv_samples"]:
            continue
        policy = PolicyRecord.model_validate(entry["policy"])
        reports.append(
            risk_report(
                policy,
                entry["npv_samples"],
                alpha=alpha,
                shortfall_threshold=shortfall_threshold,
                provenance=provenance,
            )
        )
    return rank_policies(
        reports,
        criterion=criterion,
        alpha=alpha,
        weight=weight,
        provenance=provenance,
    )


__all__ = [
    "PolicyReport",
    "SensitivityResult",
    "build_report",
    "rank_from_grid_summary",
    "write_report",
]
