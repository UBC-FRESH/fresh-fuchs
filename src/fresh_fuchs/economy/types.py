"""Typed economic surface records with provenance on every constant.

Phase 2 (economic valuation layer): the NPV surface the inner LP maximizes.
All monetary constants carry a :class:`Provenance` (source, as-of, units,
basis, assumption flag). The default :class:`EconomicSurface` is greenfield
but anchored to the fresh-salvage economics calibration
(``fresh-salvage/planning/economics-calibration.md``, reference only -- no
import) and the BC Interior Log Market Report Q4-2023 price levels.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from fresh_fuchs.instance.species import SpeciesClass

INTERIOR_PRICE_SOURCE = (
    "BC Interior Log Market Report Q4-2023 (market report); sawlog-basis "
    "flat price used by the v0.1.0a1 LP objective (grade/peeler premia reserved)"
)
SALVAGE_CALIBRATION_SOURCE = (
    "fresh-salvage planning/economics-calibration.md (reference only, no "
    "import); grade-transition erratum fixed 2026-08-13"
)


class NpvConfig(BaseModel):
    """Specification of the NPV-max inner LP.

    Mirrors :class:`fresh_fuchs.instance.types.BaselineConfig` (same volume
    even-flow band, the AAC proxy) but the objective maximizes discounted net
    revenue instead of harvest volume.
    """

    name: str = Field(default="npv-max-managed")
    sense: Literal["maximize"] = "maximize"
    flow_coefficient: float = Field(default=0.05, gt=0.0)
    mask: tuple[str, str, str, str, str] = Field(default=("?", "managed", "?", "?", "?"))
    product: str = Field(default="totvol")
    action_codes: tuple[str, str] = Field(default=("null", "harvest"))
    workers: int = Field(default=1, ge=1)


class Provenance(BaseModel):
    """Provenance fields attached to every economic constant.

    ``source`` names the record/publication/calibration; ``as_of`` the
    vintage (period or date); ``units`` the price/cost basis; ``basis`` a
    one-line description of how the number was derived; ``assumption`` is
    True when the value is an explicitly flagged assumption with no direct
    measurement (per the calibration's "DERIVED"/"ASSUMPTION" convention).
    """

    source: str = Field(description="Source record, publication, or calibration reference.")
    as_of: str = Field(
        default="Q4-2023", description="Vintage: period or date the value applies to."
    )
    units: str = Field(default="CAD", description="Currency/units basis.")
    basis: str = Field(description="How the value was derived.")
    assumption: bool = Field(
        default=False,
        description="True when the value is a flagged assumption, not a measurement.",
    )
    notes: str | None = Field(default=None, description="Optional caveats.")


class Product(StrEnum):
    """Log products used by the price records (grade-based, reserved for later work)."""

    PEELER = "peeler"
    SAWLOG = "sawlog"
    PULPWOOD = "pulpwood"


class PriceGroup(StrEnum):
    """Species price groups (fresh-salvage calibration grouping)."""

    SPF = "spf"
    DFLARCH = "df_larch"
    HEMBAL = "hembal"
    CEDAR = "cedar"
    OTHER = "other"


def price_group_for_species(species: SpeciesClass) -> PriceGroup:
    """Map a :class:`SpeciesClass` to its interior price group.

    Spruce and lodgepole pine price as SPF; Douglas-fir prices as the
    Df-Larch group; everything else as the mixed-secondary basket.
    """
    if species is SpeciesClass.DOUGLAS_FIR:
        return PriceGroup.DFLARCH
    if species in (SpeciesClass.SPRUCE, SpeciesClass.LODGEPOLE_PINE):
        return PriceGroup.SPF
    return PriceGroup.OTHER


class PriceRecord(BaseModel):
    """Log price per m3 by product and price group, with provenance."""

    product: Product = Field(description="Log product grade.")
    price_group: PriceGroup = Field(description="Species price group.")
    price_per_m3: float = Field(gt=0, description="Price in CAD/m3.")
    provenance: Provenance


class HarvestCostRecord(BaseModel):
    """Harvest cost per m3 for a treatment type, with provenance.

    ``basis`` distinguishes a flat recorded cost from a cost derived through
    the fhops machine-rate model (:mod:`fresh_fuchs.economy.fhops_costing`).
    """

    cost_per_m3: float = Field(ge=0, description="Harvest cost in CAD/m3.")
    basis: Literal["flat", "fhops"] = Field(
        default="flat", description="'flat' recorded cost or 'fhops' machine-rate estimate."
    )
    cpi_year: int | None = Field(
        default=None, description="CPI base year the cost is expressed in."
    )
    provenance: Provenance


class ReplantingCostRecord(BaseModel):
    """Flat per-ha regeneration (replanting) cost by species class.

    Covers planting plus free-to-grow establishment. Transition-dependent
    cost (replanting a different species is more expensive) is out of scope
    for v0.1.0a1 (flagged in the roadmap).
    """

    cost_per_ha_by_species: dict[SpeciesClass, float] = Field(
        description="Per-ha replanting cost keyed by species class."
    )
    default_species: SpeciesClass = Field(
        default=SpeciesClass.OTHER,
        description="Species class used when an AU/species is unknown.",
    )
    provenance: Provenance

    def cost_per_ha(self, species: SpeciesClass | None = None) -> float:
        """Per-ha replanting cost for ``species`` (or the default class)."""
        species = species if species is not None else self.default_species
        return self.cost_per_ha_by_species.get(
            species, self.cost_per_ha_by_species[self.default_species]
        )


class SalvageRecord(BaseModel):
    """Salvage economics constants for burned volume (Phase 3 fire pools).

    Calibrated constants from the fresh-salvage prompt-salvage regime
    (reference only). Grade transition rows are downgrade-only (Peel > Saw >
    Pulp; fire never upgrades grade) and each row sums to 1, so burned volume
    is conserved.
    """

    burned_price_discount: float = Field(
        default=0.65,
        ge=0,
        le=1,
        description="Fire-damaged timber realizes ~65% of green value.",
    )
    burned_harvest_premium: float = Field(
        default=0.25,
        ge=0,
        description="Fractional add-on over the green harvest cost for prompt (year 1-3) salvage.",
    )
    burned_transport_per_m3: float = Field(
        default=38.0,
        ge=0,
        description="Burned haul cost in CAD/m3 (+25% over green 30).",
    )
    burned_stumpage_per_m3: float = Field(
        default=0.25,
        ge=0,
        description="Fire-damaged timber stumpage floor in CAD/m3 (BC Table 6-4a).",
    )
    grade_transition: dict[Product, dict[Product, float]] = Field(
        description="Source product -> {target product: share}; downgrade-only rows summing to 1."
    )
    volume_decay_rate: float = Field(
        default=0.85,
        gt=0,
        le=1,
        description="Yearly retention of unsalvaged burned volume (volume-decay semantics).",
    )
    provenance: Provenance


class DiscountRate(BaseModel):
    """Annual discount rate with provenance and period convention."""

    annual_rate: float = Field(default=0.03, ge=0, le=1, description="Annual rate (default 3%).")
    convention: Literal["end_of_period", "mid_period"] = Field(
        default="end_of_period",
        description="Cash flows discounted from end-of-period (default) or period midpoint.",
    )
    provenance: Provenance

    def discount_factor(self, period: int, *, period_length: int) -> float:
        """Discount factor for a cash flow realized in ``period`` (1-based).

        ``end_of_period``: cash flow at ``period * period_length`` years from
        now; ``mid_period``: at ``(period - 0.5) * period_length``.
        """
        if period < 1:
            raise ValueError(f"period must be >= 1, got {period}")
        years = (
            period * period_length
            if self.convention == "end_of_period"
            else (period - 0.5) * period_length
        )
        return (1.0 + self.annual_rate) ** (-years)


class EconomicSurface(BaseModel):
    """Composed economic surface: the single source for inner-LP cash flows.

    ``prices`` is a flat list of :class:`PriceRecord`; helpers index it by
    (group, product). The v0.1.0a1 LP objective uses a flat sawlog-basis net
    revenue per m3 (:meth:`net_revenue_per_m3`); grade/peeler premia are
    reserved for later log-grade work (the coast price matrix in
    ``femic/resources/patchworks/log_grade_price_matrices.yaml`` is the
    reserved template).
    """

    prices: list[PriceRecord] = Field(default_factory=list)
    harvest_cost: HarvestCostRecord
    transport_per_m3: float = Field(default=30.0, ge=0, description="Green haul cost in CAD/m3.")
    stumpage_per_m3: float = Field(default=15.0, ge=0, description="Green stumpage in CAD/m3.")
    replant_cost: ReplantingCostRecord
    salvage: SalvageRecord
    discount: DiscountRate
    charge_replant_in_npv: bool = Field(
        default=False,
        description=(
            "When False (default) the per-ha replant cost is not charged in "
            "the LP objective: the default $45/m3 harvest cost already carries "
            "a silviculture allocation, so charging replant would double-count. "
            "Flip on when using a silviculture-exclusive harvest cost."
        ),
    )

    def price(self, group: PriceGroup, product: Product) -> float:
        """Price in CAD/m3 for a price group and product."""
        for record in self.prices:
            if record.price_group is group and record.product is product:
                return record.price_per_m3
        raise KeyError(f"no price record for {group.value}/{product.value}")

    def sawlog_price(self, group: PriceGroup) -> float:
        """Sawlog-basis price for a price group (the flat LP basis)."""
        return self.price(group, Product.SAWLOG)

    def net_revenue_per_m3(self, group: PriceGroup) -> float:
        """Green sawlog-basis net revenue in CAD/m3 (price - harvest - haul - stumpage)."""
        return (
            self.sawlog_price(group)
            - self.harvest_cost.cost_per_m3
            - self.transport_per_m3
            - self.stumpage_per_m3
        )

    def net_revenue_per_m3_for_species(self, species: SpeciesClass | None = None) -> float:
        """Green net revenue for a species class (via its price group)."""
        group = price_group_for_species(species) if species is not None else PriceGroup.OTHER
        return self.net_revenue_per_m3(group)

    def discount_factor(self, period: int, *, period_length: int) -> float:
        """Discount factor for ``period`` using the surface discount rate."""
        return self.discount.discount_factor(period, period_length=period_length)

    def replant_cost_per_ha(self, species: SpeciesClass | None = None) -> float:
        """Per-ha replanting cost for ``species``."""
        return self.replant_cost.cost_per_ha(species)


def _default_prices() -> list[PriceRecord]:
    """Q4-2023 BC Interior price records (fresh-salvage calibration anchors)."""
    base = Provenance(
        source=INTERIOR_PRICE_SOURCE, as_of="Q4-2023", units="CAD/m3", basis="market report"
    )
    values = {
        PriceGroup.SPF: {Product.PEELER: 146.0, Product.SAWLOG: 127.0, Product.PULPWOOD: 55.0},
        PriceGroup.DFLARCH: {Product.PEELER: 118.0, Product.SAWLOG: 103.0, Product.PULPWOOD: 55.0},
        PriceGroup.HEMBAL: {Product.PEELER: 138.0, Product.SAWLOG: 120.0, Product.PULPWOOD: 55.0},
        PriceGroup.CEDAR: {Product.PEELER: 166.0, Product.SAWLOG: 144.0, Product.PULPWOOD: 55.0},
        PriceGroup.OTHER: {Product.SAWLOG: 90.0},
    }
    records: list[PriceRecord] = []
    for group, products in values.items():
        for product, price in products.items():
            records.append(
                PriceRecord(
                    product=product,
                    price_group=group,
                    price_per_m3=price,
                    provenance=base.model_copy(),
                )
            )
    return records


def _default_replant() -> ReplantingCostRecord:
    """Default per-ha replanting costs by species (flagged assumptions).

    Per-ha planting + free-to-grow establishment costs. The LP does NOT
    charge these by default because the default harvest cost ($45/m3) already
    carries a silviculture allocation (see :func:`interior_surface`); this
    record enables the future transition-dependent replant phase.
    """
    provenance = Provenance(
        source="fresh-fuchs assumption (no direct measurement); interior planting/regen practice",
        as_of="2024",
        units="CAD/ha",
        basis="flat per-ha planting + free-to-grow establishment",
        assumption=True,
        notes=(
            "not charged in the default LP (silviculture inside the $45/m3 "
            "harvest cost); FD above PL/SX for stocking risk; verify against "
            "a femic/fhops source before release."
        ),
    )
    return ReplantingCostRecord(
        cost_per_ha_by_species={
            SpeciesClass.LODGEPOLE_PINE: 2200.0,
            SpeciesClass.SPRUCE: 2400.0,
            SpeciesClass.DOUGLAS_FIR: 2600.0,
            SpeciesClass.OTHER: 2200.0,
        },
        provenance=provenance,
    )


def _default_salvage() -> SalvageRecord:
    """Prompt-salvage constants (fresh-salvage calibration, reference only)."""
    provenance = Provenance(
        source=SALVAGE_CALIBRATION_SOURCE,
        as_of="2026-08-13",
        units="CAD/m3",
        basis="prompt-salvage (year 1-3) regime; grade-transition erratum applied",
    )
    return SalvageRecord(
        burned_price_discount=0.65,
        burned_harvest_premium=0.25,
        burned_transport_per_m3=38.0,
        burned_stumpage_per_m3=0.25,
        grade_transition={
            Product.PEELER: {Product.PEELER: 0.55, Product.SAWLOG: 0.35, Product.PULPWOOD: 0.10},
            Product.SAWLOG: {Product.SAWLOG: 0.80, Product.PULPWOOD: 0.20},
            Product.PULPWOOD: {Product.PULPWOOD: 1.0},
        },
        volume_decay_rate=0.85,
        provenance=provenance,
    )


def interior_surface() -> EconomicSurface:
    """Default interior (TSA29) economic surface anchored to the calibration.

    Harvest cost is the fresh-salvage $45/m3 total (tree-to-truck $30-40 plus
    road/admin/silviculture allocation), so every green and salvage margin
    reconciles to the calibration. The per-ha replant record is NOT charged
    by the LP by default: its silviculture is already inside the $45, and
    charging both would double-count. ``charge_replant_in_npv`` exists so a
    later phase can switch to a silviculture-exclusive $/m3 harvest cost and
    flip replant charging on.
    """
    harvest = HarvestCostRecord(
        cost_per_m3=45.0,
        basis="flat",
        cpi_year=2024,
        provenance=Provenance(
            source="fresh-salvage economics calibration (GREEN_HARVEST_COST), reference only",
            as_of="2026-08-12",
            units="CAD/m3",
            basis=(
                "tree-to-truck ($30-40/m3 range) plus road/admin/silviculture "
                "allocation; fhops machine-rate estimate (P2.2) is an "
                "alternative basis"
            ),
            assumption=True,
        ),
    )
    discount = DiscountRate(
        annual_rate=0.03,
        provenance=Provenance(
            source="fresh-salvage calibration (predecessor default retained)",
            as_of="2026-08-12",
            units="fraction/yr",
            basis="annual rate",
        ),
    )
    return EconomicSurface(
        prices=_default_prices(),
        harvest_cost=harvest,
        transport_per_m3=30.0,
        stumpage_per_m3=15.0,
        replant_cost=_default_replant(),
        salvage=_default_salvage(),
        discount=discount,
    )


__all__ = [
    "DiscountRate",
    "EconomicSurface",
    "HarvestCostRecord",
    "INTERIOR_PRICE_SOURCE",
    "NpvConfig",
    "PriceGroup",
    "PriceRecord",
    "Product",
    "Provenance",
    "ReplantingCostRecord",
    "SALVAGE_CALIBRATION_SOURCE",
    "SalvageRecord",
    "interior_surface",
    "price_group_for_species",
]
