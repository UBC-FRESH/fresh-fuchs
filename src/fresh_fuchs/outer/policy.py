"""Policy constraints as inner-LP rows and harvest-operability windows.

Composition targets and the AAC policy enter the inner LP as general rows
on the Model I leaf variables (the ``cgen_data`` pattern used for the
salvage-feasibility row in :mod:`fresh_fuchs.scenario.fire_lp`):

- Composition row ``comp_lo_{i}`` / ``comp_hi_{i}`` per target: the
  per-period harvested-area share of the target species group is pinned to
  ``[target_share - tolerance, target_share + tolerance]`` via the two
  linear rows ``sum(area_G - s * area_total) >= 0`` (``s = target -
  tol``) and ``sum(area_G - s * area_total) <= 0`` (``s = target + tol``).
- AAC row ``aac_hv`` (``aac_proxy`` mode): per-period harvest volume
  pinned to ``aac_level_m3_per_yr * period_length`` within ``aac_tolerance``
  via ``lb``/``ub`` interval bounds. Volume is the raw (pre-fire) yield
  matching the reported ``harvest_volume_m3`` accounting, so the row is
  scenario-independent and identical between the baseline and fire LPs.

``rotation_constraints`` mode instead restricts harvest operability windows
per species (rotation-age floor/ceiling), applied to the model before the
Model I tree is built.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import ws3.forest

from fresh_fuchs.economy.npv import DevelopmentTypeKey
from fresh_fuchs.instance.species import SpeciesClass

from .records import CompositionTarget, HarvestPolicyMode, PolicyRecord


def _harvest_steps(
    fm: ws3.forest.ForestModel, path: Any
) -> list[tuple[int, DevelopmentTypeKey, int]]:
    """(period, dtk, age) for harvest actions along a prescription path."""
    return [
        (t, tuple(d["dtk"]), d["age"])
        for t, node in enumerate(path, start=1)
        if (d := node.data())["acode"] == "harvest"
    ]


def _composition_coeff(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    target: CompositionTarget,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
    share: float,
) -> dict[int, float]:
    """Per-period coeff ``(area_G - share * area_total)`` for one target."""
    cohort_area = float(path[0].data("area"))
    result: dict[int, float] = {}
    for t, dtk, _age in _harvest_steps(fm, path):
        area = cohort_area if species_by_dtk.get(dtk, SpeciesClass.OTHER) is target.species else 0.0
        result[t] = area - share * cohort_area
    return result


def _aac_coeff(fm: ws3.forest.ForestModel, path: Any, *, expr: str) -> dict[int, float]:
    """Per-period raw harvest volume (m3) for the AAC row."""
    result: dict[int, float] = {}
    for t, dtk, age in _harvest_steps(fm, path):
        result[t] = fm.compile_product(t, expr, "harvest", [dtk], age, coeff=False)
    return result


def policy_coeff_funcs(
    policy: PolicyRecord,
    *,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
) -> dict[str, Callable[[Any, Any], dict[int, float]]]:
    """Per-leaf coefficient functions for the policy's general rows."""
    funcs: dict[str, Callable[[Any, Any], dict[int, float]]] = {}
    for idx, target in enumerate(policy.composition_targets):
        lo_share = target.target_share - target.tolerance
        hi_share = target.target_share + target.tolerance

        def _lo(fm, path, *, _t=target, _s=lo_share, _m=species_by_dtk):
            return _composition_coeff(fm, path, target=_t, species_by_dtk=_m, share=_s)

        def _hi(fm, path, *, _t=target, _s=hi_share, _m=species_by_dtk):
            return _composition_coeff(fm, path, target=_t, species_by_dtk=_m, share=_s)

        funcs[f"comp_lo_{idx}"] = _lo
        funcs[f"comp_hi_{idx}"] = _hi
    hp = policy.harvest_policy
    if hp is not None and hp.mode is HarvestPolicyMode.AAC_PROXY:
        funcs["aac_hv"] = lambda fm, path: _aac_coeff(fm, path, expr="totvol")
    return funcs


def policy_cgen_data(
    policy: PolicyRecord,
    *,
    period_length: int,
    periods: list[int],
) -> dict[str, dict[str, dict[int, float] | None]]:
    """General-row bounds for the policy's coefficient rows."""
    data: dict[str, dict[str, dict[int, float] | None]] = {}
    for idx in range(len(policy.composition_targets)):
        data[f"comp_lo_{idx}"] = {"lb": {t: 0.0 for t in periods}, "ub": None}
        data[f"comp_hi_{idx}"] = {"lb": None, "ub": {t: 0.0 for t in periods}}
    hp = policy.harvest_policy
    if hp is not None and hp.mode is HarvestPolicyMode.AAC_PROXY:
        aac = hp.aac_level_m3_per_yr * period_length
        tol = hp.aac_tolerance
        data["aac_hv"] = {
            "lb": {t: aac * (1.0 - tol) for t in periods},
            "ub": {t: aac * (1.0 + tol) for t in periods},
        }
    return data


def apply_rotation_constraints(
    model: ws3.forest.ForestModel,
    *,
    policy: PolicyRecord,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
) -> ws3.forest.ForestModel:
    """Restrict harvest operability windows per species (rotation policy).

    Sets each development type's harvest operability window to the species
    rotation floor/ceiling (unset sides keep the compiled window). Applied
    before the Model I tree is built; ``rotation_constraints`` mode only.
    """
    hp = policy.harvest_policy
    if hp is None or hp.mode is not HarvestPolicyMode.ROTATION_CONSTRAINTS:
        raise ValueError("rotation constraints require rotation_constraints mode")
    for dtk, dt in model.dtypes.items():
        species = species_by_dtk.get(dtk, SpeciesClass.OTHER)
        dt.compile_action("harvest")
        for period in model.periods:
            window = dt.operability.get("harvest", {}).get(period)
            cur_lo, cur_hi = window if window is not None else (0, dt._max_age)
            floor = hp.rotation_floor.get(species)
            ceiling = hp.rotation_ceiling.get(species)
            lo = floor if floor is not None else cur_lo
            hi = ceiling if ceiling is not None else cur_hi
            dt.operability["harvest"][period] = (lo, hi)
    return model
