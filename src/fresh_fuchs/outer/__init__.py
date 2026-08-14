"""Outer policy layer (Phase 4).

Policy configuration (species/development-type composition targets, AAC as
f(development type, rotation age)), grid-search driver, and risk-sensitive
evaluation of NPV distributions (expected NPV, CVaR, shortfall). Ranks
policies and produces the recommendation.
"""

from __future__ import annotations

from .grid import (
    CompositionGridAxis,
    GridRunRecord,
    HarvestGridAxis,
    PolicyGrid,
    PolicyGridResult,
    run_grid,
    write_grid_record,
)
from .policy import (
    apply_rotation_constraints,
    policy_cgen_data,
    policy_coeff_funcs,
)
from .ranking import (
    PolicyRanking,
    RankedPolicy,
    RankingCriterion,
    rank_policies,
)
from .records import (
    CompositionTarget,
    HarvestPolicy,
    HarvestPolicyMode,
    PolicyRecord,
)
from .report import (
    PolicyReport,
    SensitivityResult,
    build_report,
    rank_from_grid_summary,
    write_report,
)
from .risk import (
    GaussianComparison,
    RiskMetrics,
    RiskReport,
    conditional_value_at_risk,
    expected_npv,
    gaussian_tail_metrics,
    npv_volatility,
    risk_report,
    risk_reports_from_grid,
    shortfall_probability,
    value_at_risk,
)

__all__ = [
    "CompositionGridAxis",
    "CompositionTarget",
    "GaussianComparison",
    "GridRunRecord",
    "HarvestGridAxis",
    "HarvestPolicy",
    "HarvestPolicyMode",
    "PolicyGrid",
    "PolicyGridResult",
    "PolicyRanking",
    "PolicyRecord",
    "PolicyReport",
    "RankedPolicy",
    "RankingCriterion",
    "RiskMetrics",
    "RiskReport",
    "SensitivityResult",
    "apply_rotation_constraints",
    "build_report",
    "conditional_value_at_risk",
    "expected_npv",
    "gaussian_tail_metrics",
    "npv_volatility",
    "policy_cgen_data",
    "policy_coeff_funcs",
    "rank_from_grid_summary",
    "rank_policies",
    "risk_report",
    "risk_reports_from_grid",
    "run_grid",
    "shortfall_probability",
    "value_at_risk",
    "write_grid_record",
    "write_report",
]
