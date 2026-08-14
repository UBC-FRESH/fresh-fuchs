"""Cash-flow and NPV functions over the economic surface.

Converts harvest and regeneration decisions into net revenue and discounted
NPV for the inner LP objective (P2.5) and provides the salvage cash-flow
terms (P2.4) ready for the Phase 3 fire pools. Pure functions: no ws3
dependency, so these are hermetically testable.

Basis notes:

- The v0.1.0a1 LP uses a flat sawlog-basis green net revenue per m3
  (:meth:`EconomicSurface.net_revenue_per_m3`); grade/peeler premia are
  reserved for later log-grade work.
- ``charge_replant_in_npv`` defaults to False because the default $45/m3
  harvest cost already carries a silviculture allocation; see the field
  documentation on :class:`EconomicSurface`.
- Salvage margins follow the fresh-salvage prompt-salvage regime (reference
  only): burned price = green sawlog price x 0.65; burned harvest cost =
  green harvest cost x 1.25; grade transition is downgrade-only and
  conserves volume.
"""

from __future__ import annotations

from fresh_fuchs.instance.species import SpeciesClass

from .types import EconomicSurface, PriceGroup, Product

__all__ = [
    "burned_harvest_cost_per_m3",
    "discounted_harvest_npv",
    "green_net_revenue",
    "harvest_cash_flow",
    "sawlog_basis_salvage_margin",
    "transition_mix_burned_price",
]


def green_net_revenue(surface: EconomicSurface, species: SpeciesClass | None = None) -> float:
    """Green sawlog-basis net revenue in CAD/m3 for a species class."""
    return surface.net_revenue_per_m3_for_species(species)


def burned_harvest_cost_per_m3(surface: EconomicSurface) -> float:
    """Burned (salvage) harvest cost in CAD/m3: green cost x (1 + premium)."""
    return surface.harvest_cost.cost_per_m3 * (1.0 + surface.salvage.burned_harvest_premium)


def sawlog_basis_salvage_margin(surface: EconomicSurface, group: PriceGroup) -> float:
    """Salvage margin in CAD/m3 on a sawlog basis, at zero subsidy.

    ``burned sawlog price - burned harvest - burned transport - burned
    stumpage``. For SPF on the default surface this lands near the
    fresh-salvage sawlog-basis anchor of ~ -11.7 CAD/m3 (the transition-mix
    headline anchor is ~ -21; see :func:`transition_mix_burned_price`).
    """
    burned_price = surface.sawlog_price(group) * surface.salvage.burned_price_discount
    return (
        burned_price
        - burned_harvest_cost_per_m3(surface)
        - surface.salvage.burned_transport_per_m3
        - surface.salvage.burned_stumpage_per_m3
    )


def transition_mix_burned_price(
    surface: EconomicSurface,
    group: PriceGroup,
    *,
    source_product: Product = Product.SAWLOG,
) -> float:
    """Expected burned price in CAD/m3 for a green ``source_product``.

    Prices a green sawlog at its expected post-burn grade distribution:
    ``discount x sum(share x grade price)`` over the grade transition for
    ``source_product``. On the default surface this gives the ~73 CAD/m3 SPF
    figure whose margin is the calibration's headline ~ -21 CAD/m3.
    """
    transition = surface.salvage.grade_transition[source_product]
    expected = sum(share * surface.price(group, target) for target, share in transition.items())
    return surface.salvage.burned_price_discount * expected


def harvest_cash_flow(
    surface: EconomicSurface,
    *,
    volume_m3: float,
    area_ha: float,
    species: SpeciesClass | None = None,
) -> float:
    """Undiscounted net cash flow in CAD for a green harvest.

    ``volume_m3 x net_revenue_per_m3`` minus, when
    ``surface.charge_replant_in_npv`` is True, ``area_ha x replant_cost_per_ha``.
    """
    flow = volume_m3 * green_net_revenue(surface, species)
    if surface.charge_replant_in_npv:
        flow -= area_ha * surface.replant_cost_per_ha(species)
    return flow


def discounted_harvest_npv(
    surface: EconomicSurface,
    *,
    volume_m3: float,
    area_ha: float,
    period: int,
    period_length: int,
    species: SpeciesClass | None = None,
) -> float:
    """Discounted NPV in CAD of a green harvest in ``period`` (1-based)."""
    flow = harvest_cash_flow(surface, volume_m3=volume_m3, area_ha=area_ha, species=species)
    return surface.discount_factor(period, period_length=period_length) * flow
