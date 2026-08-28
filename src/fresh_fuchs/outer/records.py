"""Typed outer policy records (Phase 4).

A candidate outer policy is a ``PolicyRecord``: landscape composition
targets (area-share per species group, with tolerance) plus a harvest
policy (AAC level in ``aac_proxy`` mode, or per-species rotation-age
windows in ``rotation_constraints`` mode). Constraints enter the inner LP
as general rows (:mod:`fresh_fuchs.outer.policy`).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.instance.species import SpeciesClass


class HarvestPolicyMode(StrEnum):
    """How the harvest policy constrains the inner LP.

    - ``aac_proxy``: per-period harvest volume pinned to the policy AAC
      level (interval row with ``aac_tolerance``).
    - ``rotation_constraints``: harvest operability windows per species
      (rotation-age floor/ceiling) applied as Model I tree constraints.
    """

    AAC_PROXY = "aac_proxy"
    ROTATION_CONSTRAINTS = "rotation_constraints"


class CompositionTarget(BaseModel):
    """Area-share target for one species group, with tolerance.

    The share is the per-period replanted-area share of the target species
    group (when ``PolicyRecord.replant_actions`` is set) or the
    harvested-area share of the source species (when not set).  The policy
    row constrains it to ``[target_share - tolerance, target_share +
    tolerance]``.  Linear (no binaries).

    Three-phase transition schedule (avoids infeasibility when the
    starting landscape is far from the target):

    - **Free periods** (1 to ``n_free_periods``): no constraint.
    - **Ramp periods** (``n_free+1`` to ``n_free+n_ramp``): tolerance
      decays linearly from 1.0 to ``tolerance``.
    - **Binding periods** (after ramp): full constraint at ``tolerance``.

    Defaults (``n_free_periods=0, n_ramp_periods=0``) reproduce the
    current behavior: constraint from period 1 at fixed tolerance.
    """

    model_config = ConfigDict(frozen=True)

    species: SpeciesClass
    target_share: Annotated[float, Field(ge=0.0, le=1.0)]
    tolerance: Annotated[float, Field(ge=0.0, le=1.0)]
    n_free_periods: Annotated[int, Field(ge=0)] = 0
    n_ramp_periods: Annotated[int, Field(ge=0)] = 0
    provenance: Provenance


class HarvestPolicy(BaseModel):
    """Harvest policy parameters, interpreted per ``mode``."""

    model_config = ConfigDict(frozen=True)

    mode: HarvestPolicyMode
    aac_level_m3_per_yr: Annotated[float, Field(default=0.0, ge=0.0)] = 0.0
    aac_tolerance: Annotated[float, Field(default=0.0, ge=0.0, lt=1.0)] = 0.0
    rotation_floor: dict[SpeciesClass, int] = Field(default_factory=dict)
    rotation_ceiling: dict[SpeciesClass, int] = Field(default_factory=dict)
    provenance: Provenance

    @model_validator(mode="after")
    def _validate_mode(self) -> HarvestPolicy:
        if self.mode is HarvestPolicyMode.AAC_PROXY and self.aac_level_m3_per_yr <= 0.0:
            raise ValueError("aac_proxy mode requires a positive aac_level_m3_per_yr")
        if self.mode is HarvestPolicyMode.ROTATION_CONSTRAINTS and not (
            self.rotation_floor or self.rotation_ceiling
        ):
            raise ValueError(
                "rotation_constraints mode requires a rotation_floor or rotation_ceiling"
            )
        for species in set(self.rotation_floor) | set(self.rotation_ceiling):
            floor = self.rotation_floor.get(species)
            ceiling = self.rotation_ceiling.get(species)
            if floor is not None and ceiling is not None and floor > ceiling:
                raise ValueError(
                    f"rotation_floor ({floor}) exceeds rotation_ceiling ({ceiling}) "
                    f"for species {species}"
                )
        return self


class PolicyRecord(BaseModel):
    """A candidate outer policy: composition targets + harvest policy.

    ``harvest_policy`` is optional: a policy may constrain composition only.

    ``replant_actions``: when set, composition constraints bind on
    replant action area (target species).  When ``None``, they bind on
    source species (the existing behavior).
    """

    model_config = ConfigDict(frozen=True)

    name: str
    composition_targets: tuple[CompositionTarget, ...] = ()
    harvest_policy: HarvestPolicy | None = None
    replant_actions: tuple[str, ...] | None = None
    provenance: Provenance
