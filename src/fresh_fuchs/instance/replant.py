"""Replant action registration for species-switching transitions.

Registers harvest and salvage actions that transition stands to a
different species at age 0. Each replant action maps every source AU
to its corresponding replant AU (e.g. AU ``1`` → ``1-SX``) using
explicit per-AU target masks.

Design: ``design/species-switching-replant.md`` (Option C).
"""

from __future__ import annotations

import ws3.forest

from .species import SpeciesClass

# Suffix appended to the original AU code to create the replant AU.
# e.g. AU 1001 + suffix "-SX" → replant AU "1001-SX".
REPLANT_SUFFIX: dict[SpeciesClass, str] = {
    SpeciesClass.SPRUCE: "-SX",
    SpeciesClass.LODGEPOLE_PINE: "-PL",
    SpeciesClass.DOUGLAS_FIR: "-FD",
    SpeciesClass.OTHER: "-OT",
}


def replant_au_id(au_id: int | str, species: SpeciesClass) -> str:
    """Compute the replant AU code for a given source AU and target species.

    >>> replant_au_id(1001, SpeciesClass.SPRUCE)
    '1001-SX'
    >>> replant_au_id("204", SpeciesClass.LODGEPOLE_PINE)
    '204-PL'
    """
    return f"{au_id}{REPLANT_SUFFIX[species]}"


def _collect_au_ids(model: ws3.forest.ForestModel) -> list[str]:
    """Return sorted unique AU codes (theme index 2) from the model."""
    return sorted({dtk[2] for dtk in model.dtypes})


def _build_per_au_transitions(
    model: ws3.forest.ForestModel,
    species: SpeciesClass,
) -> dict[tuple[str, ...], dict[str, list[tuple]]]:
    """Build per-AU transition dicts for a replant species.

    Returns a dict keyed by source mask → ``{condition: [target_tuple]}``.
    Each source AU gets its own mask so the target AU is computed
    deterministically.
    """
    au_ids = _collect_au_ids(model)
    n = model.nthemes()
    transitions: dict[tuple[str, ...], dict[str, list[tuple]]] = {}
    for au_id in au_ids:
        source_mask = tuple("?" if i != 2 else au_id for i in range(n))
        target_mask = tuple(
            "?" if i != 2 else replant_au_id(au_id, species) for i in range(n)
        )
        target_tuple = [(target_mask, 1.0, None, 0, None, None, None)]
        transitions[source_mask] = {"": target_tuple}
    return transitions


def add_replant_actions(
    model: ws3.forest.ForestModel,
    *,
    target_species: tuple[SpeciesClass, ...],
    min_harvest_age: int | None = None,
    max_harvest_age: int | None = None,
) -> ws3.forest.ForestModel:
    """Register species-switching harvest actions on *model*.

    For each species in *target_species*, creates an action
    ``harvest_{species.value}`` (e.g. ``harvest_SX``) with:

    - Operability matching the base ``harvest`` action
    - Per-AU transitions that send each source AU to its corresponding
      replant AU at age 0

    The base ``harvest`` action is **not** modified. If a policy wants
    same-species replanting only, it simply does not include the new
    action codes.

    Parameters
    ----------
    model :
        Compiled ws3 ForestModel (already has ``harvest`` action).
    target_species :
        Species classes to register replant actions for.
    min_harvest_age, max_harvest_age :
        Override the operability bounds. If *None*, inherit from the
        existing ``harvest`` action's operability expression.
    """
    wildcard_mask = tuple("?" for _ in range(model.nthemes()))
    if min_harvest_age is not None and max_harvest_age is not None:
        oper_expr = f"_age >= {min_harvest_age} and _age <= {max_harvest_age}"
    else:
        oper_expr = next(iter(model.oper_expr.get("harvest", {}).values()), None)
        if oper_expr is None:
            raise ValueError(
                "base 'harvest' action not found; cannot derive operability"
            )

    for species in target_species:
        acode = f"harvest_{species.value}"
        if acode in model.actions:
            continue  # idempotent

        per_au_transitions = _build_per_au_transitions(model, species)

        model.actions[acode] = ws3.forest.Action(acode, is_harvest=True)
        model.oper_expr[acode] = {wildcard_mask: oper_expr}
        model.transitions[acode] = per_au_transitions

        for dtk in model.dtypes:
            dt = model.dtypes[dtk]
            dt.oper_expr[acode] = [oper_expr]
            source_mask = tuple("?" if i != 2 else dtk[2] for i in range(model.nthemes()))
            if source_mask in per_au_transitions:
                dt.transitions[acode, -1] = per_au_transitions[source_mask][""]

        for period in model.applied_actions:
            model.applied_actions[period][acode] = {}

    return model


def add_replant_salvage_actions(
    model: ws3.forest.ForestModel,
    *,
    target_species: tuple[SpeciesClass, ...],
    min_salvage_age: int | None = None,
    max_salvage_age: int | None = None,
) -> ws3.forest.ForestModel:
    """Register species-switching salvage actions on *model*.

    For each species in *target_species*, creates an action
    ``salvage_{species.value}`` (e.g. ``salvage_SX``) with:

    - Operability matching the base ``salvage`` action
    - Per-AU transitions that send each source AU to its corresponding
      replant AU at age 0

    The base ``salvage`` action is **not** modified.
    """
    wildcard_mask = tuple("?" for _ in range(model.nthemes()))
    if min_salvage_age is not None and max_salvage_age is not None:
        oper_expr = f"_age >= {min_salvage_age} and _age <= {max_salvage_age}"
    else:
        oper_expr = next(iter(model.oper_expr.get("salvage", {}).values()), None)
        if oper_expr is None:
            raise ValueError(
                "base 'salvage' action not found; cannot derive operability"
            )

    for species in target_species:
        acode = f"salvage_{species.value}"
        if acode in model.actions:
            continue

        per_au_transitions = _build_per_au_transitions(model, species)

        model.actions[acode] = ws3.forest.Action(acode)
        model.oper_expr[acode] = {wildcard_mask: oper_expr}
        model.transitions[acode] = per_au_transitions

        for dtk in model.dtypes:
            dt = model.dtypes[dtk]
            dt.oper_expr[acode] = [oper_expr]
            source_mask = tuple("?" if i != 2 else dtk[2] for i in range(model.nthemes()))
            if source_mask in per_au_transitions:
                dt.transitions[acode, -1] = per_au_transitions[source_mask][""]

        for period in model.applied_actions:
            model.applied_actions[period][acode] = {}

    return model
