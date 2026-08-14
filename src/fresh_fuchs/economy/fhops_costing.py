"""Harvest cost per m3 via the fhops machine-rate model (P2.2).

Consumes ``fhops.costing.estimate_unit_cost_from_stand`` (Lahrsen
productivity + rental-rate costing) to derive a clearcut harvest cost in
CAD/m3 from stand attributes. fhops is an optional dependency: the economy
core records import without it, and this module raises an explicit
diagnostic when fhops is missing.

Provenance: the machine rental rates come from fhops' bundled machine-rate
table (FPInnovations OpCost-inspired), CPI-adjusted by fhops to its
``TARGET_YEAR`` (2024); productivity is the fhops Lahrsen model prediction.
The resulting cost is a machine-based tree-to-truck estimate and is an
ALTERNATIVE basis to the default flat $45/m3 calibration cost (which includes
road/admin/silviculture allocations).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from .types import HarvestCostRecord, Provenance

if TYPE_CHECKING:
    from fhops.costing.machines import MachineCostEstimate


class MissingDependencyError(RuntimeError):
    """Raised when the optional fhops dependency is not importable."""


class StandAttributes(BaseModel):
    """Stand-average attributes driving the Lahrsen productivity prediction."""

    avg_stem_size_m3: float = Field(gt=0, description="Mean stem volume in m3/stem.")
    volume_per_ha: float = Field(gt=0, description="Merchantable volume in m3/ha.")
    stem_density_per_ha: float = Field(gt=0, description="Stems per ha.")
    ground_slope_pct: float = Field(ge=0, description="Average ground slope in percent.")


def default_clearcut_stand() -> StandAttributes:
    """Default interior clearcut stand attributes (tsa29mini-ish, assumption).

    Representative interior spruce/lodgepole clearcut: 0.3 m3 stems, ~180
    m3/ha operable volume, ~2000 stems/ha, 25% slope. Flagged assumption; a
    real run should use fragment-derived attributes.
    """
    return StandAttributes(
        avg_stem_size_m3=0.3,
        volume_per_ha=180.0,
        stem_density_per_ha=2000.0,
        ground_slope_pct=25.0,
    )


class HarvestCostModel(BaseModel):
    """fhops-driven clearcut harvest cost estimator.

    ``role`` selects the fhops machine role (default ``feller_buncher``).
    When ``rental_rate_smh`` is None the rental rate is composed from the
    bundled machine-rate table for ``role``; ``utilisation`` defaults to the
    machine rate's default utilisation.
    """

    role: str = Field(
        default="feller_buncher",
        description="fhops machine-role label for the rental-rate table.",
    )
    rental_rate_smh: float | None = Field(
        default=None,
        description="Explicit rental rate in $/SMH; None composes from the fhops table.",
    )
    utilisation: float | None = Field(
        default=None,
        description="Realised utilisation fraction in (0, 1]; None uses the machine-rate default.",
    )
    cpi_year: int = Field(
        default=2024,
        description="CPI base year of the fhops cost (matches fhops TARGET_YEAR).",
    )

    def estimate(self, stand: StandAttributes | None = None) -> HarvestCostRecord:
        """Estimate the clearcut harvest cost for ``stand`` (default interior).

        Uses the machine role in :attr:`role` (default ``feller_buncher``) --
        a SINGLE machine pass (felling). This is a lower bound of the
        tree-to-truck cost; see :meth:`system_estimate` for the full machine
        chain.
        """
        try:
            from fhops.costing.machine_rates import (
                compose_default_rental_rate_for_role,
                get_machine_rate,
            )
            from fhops.costing.machines import estimate_unit_cost_from_stand
        except ImportError as exc:
            raise MissingDependencyError(
                "fhops is required for machine-rate harvest costing; install "
                "the 'fhops' extra (pip install 'fresh-fuchs[fhops]') or add "
                "fhops to the environment."
            ) from exc

        stand = stand if stand is not None else default_clearcut_stand()

        rental_rate: float
        breakdown: dict[str, float] | None = None
        if self.rental_rate_smh is not None:
            rental_rate = self.rental_rate_smh
        else:
            composed = compose_default_rental_rate_for_role(self.role)
            if composed is None:
                raise MissingDependencyError(f"fhops has no machine rate for role {self.role!r}")
            rental_rate, breakdown = composed

        utilisation = self.utilisation
        machine_source: str | None = None
        if utilisation is None:
            rate = get_machine_rate(self.role)
            if rate is None:
                raise MissingDependencyError(f"fhops has no machine rate for role {self.role!r}")
            utilisation = rate.default_utilization
            machine_source = rate.source

        estimate: MachineCostEstimate
        estimate, _ = estimate_unit_cost_from_stand(
            rental_rate_smh=rental_rate,
            utilisation=utilisation,
            avg_stem_size=stand.avg_stem_size_m3,
            volume_per_ha=stand.volume_per_ha,
            stem_density=stand.stem_density_per_ha,
            ground_slope=stand.ground_slope_pct,
            rental_rate_breakdown=breakdown,
        )

        import fhops

        notes = (
            f"fhops {fhops.__version__}; role={self.role} (single machine pass); "
            f"stand={stand.model_dump()}; util={utilisation:.2f}; "
            f"productivity={estimate.productivity_m3_per_pmh:.1f} m3/PMH"
        )
        if machine_source:
            notes += f"; machine rate source: {machine_source}"
        return HarvestCostRecord(
            cost_per_m3=estimate.cost_per_m3,
            basis="fhops",
            cpi_year=self.cpi_year,
            provenance=Provenance(
                source=f"fhops {fhops.__version__} costing machine model (Lahrsen productivity)",
                as_of=str(self.cpi_year),
                units="CAD/m3",
                basis=(
                    "machine-rate estimate; single-pass felling only, a lower "
                    "bound of tree-to-truck; alternative to the flat "
                    "calibration cost"
                ),
                assumption=True,
                notes=notes,
            ),
        )

    def system_estimate(
        self,
        stand: StandAttributes | None = None,
        *,
        roles: tuple[str, ...] = ("feller_buncher", "processor", "grapple_skidder", "loader"),
    ) -> HarvestCostRecord:
        """Estimate the clearcut cost for a full machine chain (felling + process + skid + load).

        Sums per-pass costs for ``roles`` on the same stand attributes. Each
        pass reuses the stand's productivity prediction, so this is a
        first-order tree-to-truck machine cost (no road/admin/silviculture);
        on the default interior stand it lands near the $30-40/m3 tree-to-truck
        range.
        """
        try:
            from fhops.costing.machine_rates import (
                compose_default_rental_rate_for_role,
                get_machine_rate,
            )
            from fhops.costing.machines import estimate_unit_cost_from_stand
        except ImportError as exc:
            raise MissingDependencyError(
                "fhops is required for machine-rate harvest costing; install "
                "the 'fhops' extra (pip install 'fresh-fuchs[fhops]') or add "
                "fhops to the environment."
            ) from exc

        stand = stand if stand is not None else default_clearcut_stand()
        import fhops

        total = 0.0
        parts: list[str] = []
        for role in roles:
            composed = compose_default_rental_rate_for_role(role)
            if composed is None:
                raise MissingDependencyError(f"fhops has no machine rate for role {role!r}")
            rental_rate, breakdown = composed
            rate = get_machine_rate(role)
            utilisation = (
                self.utilisation if self.utilisation is not None else rate.default_utilization
            )
            estimate, _ = estimate_unit_cost_from_stand(
                rental_rate_smh=rental_rate,
                utilisation=utilisation,
                avg_stem_size=stand.avg_stem_size_m3,
                volume_per_ha=stand.volume_per_ha,
                stem_density=stand.stem_density_per_ha,
                ground_slope=stand.ground_slope_pct,
                rental_rate_breakdown=breakdown,
            )
            total += estimate.cost_per_m3
            parts.append(f"{role}={estimate.cost_per_m3:.2f}")
        return HarvestCostRecord(
            cost_per_m3=total,
            basis="fhops",
            cpi_year=self.cpi_year,
            provenance=Provenance(
                source=f"fhops {fhops.__version__} costing machine model (Lahrsen productivity)",
                as_of=str(self.cpi_year),
                units="CAD/m3",
                basis=(
                    "machine-rate system estimate: felling+process+skid+load "
                    "sum; no road/admin/silviculture; alternative to the flat "
                    "calibration cost"
                ),
                assumption=True,
                notes=f"per-pass CAD/m3: {'; '.join(parts)}; stand={stand.model_dump()}",
            ),
        )


__all__ = [
    "HarvestCostModel",
    "MissingDependencyError",
    "StandAttributes",
    "default_clearcut_stand",
]
