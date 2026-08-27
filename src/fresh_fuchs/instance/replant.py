"""Replant action registration for species-switching transitions.

Registers harvest and salvage actions that transition stands to a
different species at age 0. Each replant action maps every source AU
to its corresponding replant AU (e.g. AU ``1`` → ``1-SX``) using
explicit per-AU target masks.

Design: ``design/species-switching-replant.md`` (Option C).
"""

from __future__ import annotations

from typing import Any

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

# Reverse lookup: species value (e.g. "SX") → SpeciesClass.
_ACODE_VALUE_TO_SPECIES: dict[str, SpeciesClass] = {
    sp.value: sp for sp in REPLANT_SUFFIX
}


def target_species_from_acode(acode: str) -> SpeciesClass | None:
    """Extract the target species from a replant action code.

    Returns ``SpeciesClass.SPRUCE`` for ``"harvest_SX"``,
    ``SpeciesClass.LODGEPOLE_PINE`` for ``"salvage_PL"``, etc.
    Returns ``None`` for base action codes (``"harvest"``, ``"salvage"``,
    ``"null"``).

    >>> target_species_from_acode("harvest_SX")
    <SpeciesClass.SPRUCE: 'SX'>
    >>> target_species_from_acode("salvage_FD")
    <SpeciesClass.DOUGLAS_FIR: 'FD'>
    >>> target_species_from_acode("harvest") is None
    True
    """
    parts = acode.rsplit("_", 1)
    if len(parts) == 2:
        species_value = parts[1]
        return _ACODE_VALUE_TO_SPECIES.get(species_value)
    return None


def replant_au_id(au_id: int | str, species: SpeciesClass) -> str:
    """Compute the replant AU code for a given source AU and target species.

    Strips any existing replant suffix before appending the new one.

    >>> replant_au_id(1001, SpeciesClass.SPRUCE)
    '1001-SX'
    >>> replant_au_id("204", SpeciesClass.LODGEPOLE_PINE)
    '204-PL'
    >>> replant_au_id("1-SX", SpeciesClass.DOUGLAS_FIR)
    '1-FD'
    """
    base = _strip_replant_suffix(au_id)
    return f"{base}{REPLANT_SUFFIX[species]}"


def _strip_replant_suffix(au_id: str) -> str:
    """Remove any replant suffix from an AU code.

    >>> _strip_replant_suffix('1-SX')
    '1'
    >>> _strip_replant_suffix('2')
    '2'
    """
    s = str(au_id)
    for suffix in REPLANT_SUFFIX.values():
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s


def _collect_au_ids(model: ws3.forest.ForestModel) -> list[str]:
    """Return sorted unique AU codes (theme index 2) from the model."""
    return sorted({dtk[2] for dtk in model.dtypes})


def _build_per_au_transitions(
    model: ws3.forest.ForestModel,
    species: SpeciesClass,
) -> dict[tuple[str, ...], dict[str, list[tuple]]]:
    """Build per-AU transition dicts for a replant species.

    Returns a dict keyed by source mask -> ``{condition: [target_tuple]}``.
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

    Also pre-creates the replant DTKs in ``model.dtypes`` so that
    ws3's tree builder can follow replant transitions without crashing.
    Each replant DTK is initialised with the same yield curves as its
    source AU, zero initial area, and transitions for all registered
    replant actions.

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
    n = model.nthemes()
    wildcard_mask = tuple("?" for _ in range(n))
    if min_harvest_age is not None and max_harvest_age is not None:
        oper_expr = f"_age >= {min_harvest_age} and _age <= {max_harvest_age}"
    else:
        oper_expr = next(iter(model.oper_expr.get("harvest", {}).values()), None)
        if oper_expr is None:
            raise ValueError(
                "base 'harvest' action not found; cannot derive operability"
            )

    all_acodes: list[str] = []

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
            source_mask = tuple("?" if i != 2 else dtk[2] for i in range(n))
            if source_mask in per_au_transitions:
                dt.transitions[acode, -1] = per_au_transitions[source_mask][""]

        for period in model.applied_actions:
            model.applied_actions[period][acode] = {}

        all_acodes.append(acode)

    if all_acodes:
        _precreate_replant_dtypes(model, target_species, all_acodes, oper_expr)

    return model


def _yields_stash_ycomps(
    model: ws3.forest.ForestModel, key: tuple[str, ...]
) -> list[tuple[str, Any]]:
    """Return ``(yname, ycomp)`` pairs stashed in ``model.yields`` for *key*.

    ws3's ``import_yields_section`` stashes ``(mask, t, ycomps)`` for DTKs
    that do not exist yet at bootstrap (our replant AUs have curves but no
    area records). Only simple literal/wildcard masks are matched (the
    replant curves are written with ``*Y ? managed <rau> ? ?`` masks).
    ws3 lowercases mask entries on import, so comparison is
    case-insensitive.
    """
    found: list[tuple[str, Any]] = []
    for mask, t, ycomps in getattr(model, "yields", []):
        if len(mask) != len(key):
            continue
        if all(
            str(m).lower() == "?" or str(m).lower() == str(k).lower()
            for m, k in zip(mask, key, strict=True)
        ):
            found.extend(ycomps)
    return found


def _precreate_replant_dtypes(
    model: ws3.forest.ForestModel,
    target_species: tuple[SpeciesClass, ...],
    all_acodes: list[str],
    oper_expr: str,
) -> None:
    """Pre-create replant DTKs with yield curves and transitions.

    ws3's ``create_dtype_fromkey`` uses theme-hierarchy mask matching,
    which cannot resolve non-standard AU codes like ``1-SX``.  This
    function bypasses that by creating ``DevelopmentType`` objects
    directly and wiring up their yield curves and transitions.

    For each original DTK and each target species, the corresponding
    replant DTK is created (if not already present) with:

    - Yield curves from the ``model.yields`` stash when the Woodstock
      ``.yld`` section carried curves for this replant AU (the real
      target-species curves, e.g. BTC replant store); otherwise curves
      copied from the source AU's DTK (backward-compatible placeholder)
    - Operability and transitions for ALL registered actions
      (copied from existing DTKs via model-level oper_expr)
    - Zero initial area
    """
    n = model.nthemes()
    source_dtks = list(model.dtypes.keys())

    for source_dtk in source_dtks:
        source_dt = model.dtypes[source_dtk]
        for species in target_species:
            replant_key = list(source_dtk)
            replant_key[2] = replant_au_id(source_dtk[2], species)
            replant_key = tuple(replant_key)

            if replant_key in model.dtypes:
                dt = model.dtypes[replant_key]
            else:
                dt = ws3.forest.DevelopmentType(replant_key, model)
                model.dtypes[replant_key] = dt

                # Prefer real replant-AU curves from the yields stash;
                # fall back to copying the source DTK's curves.
                stashed = _yields_stash_ycomps(model, replant_key)
                if stashed:
                    for yname, ycomp in stashed:
                        dt.add_ycomp("a", yname, ycomp)
                else:
                    for yname in source_dt.ycomps():
                        ycomp = source_dt.ycomp(yname)
                        dt.add_ycomp("a", yname, ycomp)

            # Wire up ALL model-level actions on this DTK
            for acode in model.actions:
                # Copy operability expression from model-level (not the
                # harvest-only oper_expr; e.g. null needs _age >= 0)
                if acode not in dt.oper_expr:
                    model_oper = next(
                        iter(model.oper_expr.get(acode, {}).values()), oper_expr
                    )
                    dt.oper_expr[acode] = [model_oper]

                # Copy transitions: for replant actions, set self-loop;
                # for base actions, replicate from source DTK if available.
                if (acode, -1) not in dt.transitions:
                    sp = target_species_from_acode(acode)
                    if acode in all_acodes and sp is not None:
                        # Replant action: target is the species of THIS action
                        target_au = replant_au_id(replant_key[2], sp)
                        target_mask = tuple(
                            "?" if i != 2 else target_au for i in range(n)
                        )
                        dt.transitions[acode, -1] = [
                            (target_mask, 1.0, None, 0, None, None, None)
                        ]
                    else:
                        # Base action: copy from source DTK if it has transitions
                        for age_key in source_dt.transitions:
                            if age_key[0] == acode:
                                dt.transitions[acode, -1] = source_dt.transitions[
                                    age_key
                                ]


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

    Like :func:`add_replant_actions`, newly registered salvage replant
    targets are pre-created in ``model.dtypes`` (curves copied from the
    source DTK) so the tree builder can follow salvage replant
    transitions even when no harvest replant action was registered.
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

    all_acodes: list[str] = []

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

        all_acodes.append(acode)

    if all_acodes:
        _precreate_replant_dtypes(model, target_species, all_acodes, oper_expr)

    return model
