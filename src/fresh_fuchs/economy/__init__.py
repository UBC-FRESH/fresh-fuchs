"""Economic valuation layer (Phase 2).

Typed economic-surface records with provenance on every constant
(:mod:`fresh_fuchs.economy.types`), cash-flow/NPV functions
(:mod:`fresh_fuchs.economy.cashflow`), the fhops machine-rate harvest cost
estimator (:mod:`fresh_fuchs.economy.fhops_costing`), and the NPV objective
wiring for the inner LP (:mod:`fresh_fuchs.economy.npv`).
"""

from __future__ import annotations

from .cashflow import (
    burned_harvest_cost_per_m3,
    discounted_harvest_npv,
    green_net_revenue,
    harvest_cash_flow,
    sawlog_basis_salvage_margin,
    transition_mix_burned_price,
)
from .fhops_costing import (
    HarvestCostModel,
    MissingDependencyError,
    StandAttributes,
    default_clearcut_stand,
)
from .npv import add_npv_problem, solve_npv, species_by_dtk_from_areas
from .types import (
    DiscountRate,
    EconomicSurface,
    HarvestCostRecord,
    NpvConfig,
    PriceGroup,
    PriceRecord,
    Product,
    Provenance,
    ReplantingCostRecord,
    SalvageRecord,
    interior_surface,
    price_group_for_species,
)

__all__ = [
    "DiscountRate",
    "EconomicSurface",
    "HarvestCostModel",
    "HarvestCostRecord",
    "MissingDependencyError",
    "NpvConfig",
    "PriceGroup",
    "PriceRecord",
    "Product",
    "Provenance",
    "ReplantingCostRecord",
    "SalvageRecord",
    "StandAttributes",
    "add_npv_problem",
    "burned_harvest_cost_per_m3",
    "default_clearcut_stand",
    "discounted_harvest_npv",
    "green_net_revenue",
    "harvest_cash_flow",
    "interior_surface",
    "price_group_for_species",
    "sawlog_basis_salvage_margin",
    "solve_npv",
    "species_by_dtk_from_areas",
    "transition_mix_burned_price",
]
