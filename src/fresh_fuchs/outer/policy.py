"""Policy constraints as inner-LP rows and harvest-operability windows.

Composition targets and the AAC policy enter the inner LP as general rows
on the Model I leaf variables (the ``cgen_data`` pattern used for the
salvage-feasibility row in :mod:`fresh_fuchs.scenario.fire_lp`):

- Composition row ``comp_lo_{i}`` / ``comp_hi_{i}`` per target: the
  per-period replanted-area share (when ``PolicyRecord.replant_actions``
  is set) or harvested-area share (when not set) of the target species
  group is pinned to ``[target_share - tolerance, target_share +
  tolerance]`` via the two linear rows ``sum(area_G - s * area_total) >=
  0`` (``s = target - tol``) and ``sum(area_G - s * area_total) <= 0``
  (``s = target + tol``).

  Three-phase transition (avoids infeasibility): free periods (no
  constraint), ramp periods (tolerance decays linearly from 1.0 to
  ``tolerance``), binding periods (full constraint at ``tolerance``).

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
from fresh_fuchs.instance.replant import target_species_from_acode
from fresh_fuchs.instance.species import SpeciesClass

from .records import CompositionTarget, HarvestPolicyMode, PolicyRecord


def _harvest_steps(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    replant_actions: tuple[str, ...] | None = None,
) -> list[tuple[int, DevelopmentTypeKey, int, str]]:
    """(period, dtk, age, acode) for harvest actions along a prescription path.

    When *replant_actions* is set, matches any ``harvest_*`` action;
    otherwise matches only ``"harvest"``.
    """
    steps: list[tuple[int, DevelopmentTypeKey, int, str]] = []
    for t, node in enumerate(path, start=1):
        d = node.data()
        acode = d["acode"]
        if replant_actions is not None:
            if not acode.startswith("harvest"):
                continue
        else:
            if acode != "harvest":
                continue
        steps.append((t, tuple(d["dtk"]), d["age"], acode))
    return steps


def _resolve_species(
    acode: str,
    dtk: DevelopmentTypeKey,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
    replant_actions: tuple[str, ...] | None,
) -> SpeciesClass:
    """Determine the species to attribute a harvest step to.

    When *replant_actions* is set, uses the action code's target species
    (falling back to ``species_by_dtk`` for base ``"harvest"``).
    Otherwise uses ``species_by_dtk`` (source species).
    """
    if replant_actions is not None:
        sp = target_species_from_acode(acode)
        if sp is not None:
            return sp
    return species_by_dtk.get(dtk, SpeciesClass.OTHER)


def _share_by_period(
    target: CompositionTarget,
    periods: list[int],
) -> dict[int, float]:
    """Per-period effective tolerance from the three-phase schedule.

    Returns ``{period: effective_tolerance}``.  The coefficient uses
    ``target_share ± effective_tolerance`` to encode the constraint.

    - Free periods: tolerance = 1.0 (row is structurally satisfied).
    - Ramp periods: tolerance decays linearly from 1.0 to
      ``target.tolerance``.
    - Binding periods: tolerance = ``target.tolerance``.
    """
    n_free = target.n_free_periods
    n_ramp = target.n_ramp_periods
    result: dict[int, float] = {}
    for t in periods:
        if t <= n_free:
            result[t] = 1.0
        elif n_ramp > 0 and t <= n_free + n_ramp:
            ramp_frac = (t - n_free) / n_ramp
            result[t] = 1.0 - ramp_frac * (1.0 - target.tolerance)
        else:
            result[t] = target.tolerance
    return result


def _composition_coeff(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    target: CompositionTarget,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
    share_by_period: dict[int, float],
    replant_actions: tuple[str, ...] | None = None,
) -> dict[int, float]:
    """Per-period coeff ``(area_G - share_t * area_total)`` for one target.

    ``share_by_period`` maps period → effective share (``target_share ±
    tolerance_t``).  The species attribution uses replant action codes
    when *replant_actions* is set; otherwise uses source species.
    """
    cohort_area = float(path[0].data("area"))
    result: dict[int, float] = {}
    for t, dtk, _age, acode in _harvest_steps(
        fm, path, replant_actions=replant_actions
    ):
        sp = _resolve_species(acode, dtk, species_by_dtk, replant_actions)
        is_target = 1.0 if sp is target.species else 0.0
        share = share_by_period.get(t, target.target_share)
        result[t] = cohort_area * (is_target - share)
    return result


def _aac_coeff(fm: ws3.forest.ForestModel, path: Any, *, expr: str) -> dict[int, float]:
    """Per-period raw harvest volume (m3) for the AAC row."""
    result: dict[int, float] = {}
    for t, dtk, age, _acode in _harvest_steps(fm, path):
        result[t] = fm.compile_product(t, expr, "harvest", [dtk], age, coeff=False)
    return result


def policy_coeff_funcs(
    policy: PolicyRecord,
    *,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
    periods: list[int] | None = None,
) -> dict[str, Callable[[Any, Any], dict[int, float]]]:
    """Per-leaf coefficient functions for the policy's general rows.

    When ``policy.replant_actions`` is set, composition coefficients use
    replant action area (target species).  Otherwise they use source
    species (the existing behavior).

    *periods* is required for the three-phase tolerance schedule;
    when ``None``, falls back to fixed-tolerance behavior.
    """
    funcs: dict[str, Callable[[Any, Any], dict[int, float]]] = {}
    replant_actions = policy.replant_actions

    for idx, target in enumerate(policy.composition_targets):
        if periods is not None:
            tol_lo = _share_by_period(target, periods)
            tol_hi = _share_by_period(target, periods)
            lo_share = {
                t: target.target_share - tol_lo[t] for t in periods
            }
            hi_share = {
                t: target.target_share + tol_hi[t] for t in periods
            }
        else:
            lo_share = {t: target.target_share - target.tolerance for t in (periods or [])}
            hi_share = {t: target.target_share + target.tolerance for t in (periods or [])}

        def _lo(
            fm,
            path,
            *,
            _t=target,
            _ls=lo_share,
            _m=species_by_dtk,
            _ra=replant_actions,
        ):
            return _composition_coeff(
                fm, path, target=_t, species_by_dtk=_m,
                share_by_period=_ls, replant_actions=_ra,
            )

        def _hi(
            fm,
            path,
            *,
            _t=target,
            _hs=hi_share,
            _m=species_by_dtk,
            _ra=replant_actions,
        ):
            return _composition_coeff(
                fm, path, target=_t, species_by_dtk=_m,
                share_by_period=_hs, replant_actions=_ra,
            )

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
    """General-row bounds for the policy's coefficient rows.

    Composition rows use zero bounds (the share is embedded in the
    coefficient via ``_share_by_period``).  Three-phase periods with
    tolerance = 1.0 produce structurally satisfied rows.
    """
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
