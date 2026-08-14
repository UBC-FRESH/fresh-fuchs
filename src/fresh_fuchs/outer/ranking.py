"""Policy ranking over risk reports (Phase 4, P4.4).

Reproducible ranking rule over ``RiskReport``\\ s: lexicographic on
(expected NPV, CVaR(alpha)) or a weighted mean-CVaR score; volatility
breaks ties. ``PolicyRanking`` records the criterion, weights, per-policy
ranks, and the recommended (top-ranked) policy.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.outer.records import PolicyRecord
from fresh_fuchs.outer.risk import RiskReport


class RankingCriterion(StrEnum):
    """Ranking rule over per-policy risk metrics.

    - ``E_NPV_CVAR``: lexicographic — maximize expected NPV, then CVaR.
    - ``MEAN_CVAR``: maximize the weighted score
      ``weight * E[NPV] + (1 - weight) * CVaR(alpha)``.
    """

    E_NPV_CVAR = "expected_npv_cvar"
    MEAN_CVAR = "mean_cvar"


def _sort_key(report: RiskReport, criterion: RankingCriterion, weight: float) -> tuple:
    metrics = report.metrics
    if criterion is RankingCriterion.E_NPV_CVAR:
        score = None
        primary = (-metrics.expected_npv, -metrics.conditional_value_at_risk)
    else:
        score = weight * metrics.expected_npv + (1.0 - weight) * metrics.conditional_value_at_risk
        primary = (-score,)
    return (*primary, metrics.npv_volatility)


class RankedPolicy(BaseModel):
    """One ranked policy with its risk report."""

    model_config = ConfigDict(frozen=True)

    rank: int = Field(ge=1)
    policy: PolicyRecord
    report: RiskReport
    score: float | None = Field(default=None, description="Criterion score (MEAN_CVAR only).")


class PolicyRanking(BaseModel):
    """The ranking of a set of policies under one criterion."""

    model_config = ConfigDict(frozen=True)

    criterion: RankingCriterion
    alpha: float
    weight: float | None = Field(
        default=None, description="E[NPV] weight for MEAN_CVAR; None for E_NPV_CVAR."
    )
    rankings: tuple[RankedPolicy, ...]
    recommended: RankedPolicy
    provenance: Provenance

    @model_validator(mode="after")
    def _validate(self) -> PolicyRanking:
        if self.criterion is RankingCriterion.MEAN_CVAR and self.weight is None:
            raise ValueError("MEAN_CVAR requires an E[NPV] weight in [0, 1]")
        if self.rankings and self.recommended.rank != 1:
            raise ValueError("recommended policy must be the rank-1 policy")
        return self


def rank_policies(
    reports: list[RiskReport] | tuple[RiskReport, ...],
    *,
    criterion: RankingCriterion = RankingCriterion.E_NPV_CVAR,
    alpha: float = 0.95,
    weight: float | None = None,
    provenance: Provenance,
) -> PolicyRanking:
    """Rank policies by ``criterion``; ties broken by NPV volatility.

    Rank order is deterministic (stable sort on a total order). All reports
    must share the same ``alpha``.
    """
    if not reports:
        raise ValueError("no reports to rank")
    if criterion is RankingCriterion.MEAN_CVAR and weight is None:
        weight = 0.5
    if weight is not None and not 0.0 <= weight <= 1.0:
        raise ValueError("weight must lie in [0, 1]")
    ordered = sorted(reports, key=lambda r: _sort_key(r, criterion, weight or 0.0))
    ranked: list[RankedPolicy] = []
    for i, report in enumerate(ordered, start=1):
        metrics = report.metrics
        score = None
        if criterion is RankingCriterion.MEAN_CVAR:
            score = (weight or 0.0) * metrics.expected_npv + (1.0 - (weight or 0.0)) * (
                metrics.conditional_value_at_risk
            )
        ranked.append(RankedPolicy(rank=i, policy=report.policy, report=report, score=score))
    return PolicyRanking(
        criterion=criterion,
        alpha=alpha,
        weight=weight,
        rankings=tuple(ranked),
        recommended=ranked[0],
        provenance=provenance,
    )


__all__ = [
    "PolicyRanking",
    "RankedPolicy",
    "RankingCriterion",
    "rank_policies",
]
