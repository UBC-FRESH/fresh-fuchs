"""Species-composition surface over post-bridge area records.

The ws3 model stays species-free (five themes only); composition is computed
from the fresh-fuchs area records, whose ``species`` column carries each AU's
static primary species class. This is the surface Phase 4 composes targets
against (species area-share composition of the managed land base and of
schedules).
"""

from __future__ import annotations

import pandas as pd

_SPECIES_COLUMN = "species"
_MANAGED = "managed"


def managed_landscape_composition(areas: pd.DataFrame) -> pd.DataFrame:
    """Area share of the managed land base by primary species class.

    ``areas`` must carry the ``species`` column (added by
    :func:`fresh_fuchs.instance.bundle.apply_retention_split` when given
    ``species_by_au``). Returns ``species``, ``area_ha``, ``share`` sorted by
    area share descending; shares sum to 1.
    """
    if _SPECIES_COLUMN not in areas.columns:
        raise ValueError(
            "areas is missing the 'species' column; pass species_by_au to "
            "apply_retention_split when building the area records"
        )
    managed = areas.loc[areas["ifm"] == _MANAGED]
    grouped = (
        managed.groupby(_SPECIES_COLUMN, observed=True)["area_ha"].sum().reset_index()
    )
    total = float(grouped["area_ha"].sum())
    if total <= 0.0:
        raise ValueError("managed land base has zero area; cannot compute composition")
    grouped["share"] = grouped["area_ha"] / total
    return grouped.sort_values("share", ascending=False).reset_index(drop=True)


def development_type_species(areas: pd.DataFrame) -> pd.DataFrame:
    """Species class per development-type key.

    Returns one row per distinct ``(tsa, ifm, au_id, origin, silv_state,
    age)`` with its ``species``. Development types are species-aware through
    their AU, so any schedule keyed by these attributes can be joined to a
    species class without touching the ws3 model.
    """
    if _SPECIES_COLUMN not in areas.columns:
        raise ValueError(
            "areas is missing the 'species' column; pass species_by_au to "
            "apply_retention_split when building the area records"
        )
    keys = [
        "tsa",
        "ifm",
        "au_id",
        "origin",
        "silv_state",
        "age",
        _SPECIES_COLUMN,
    ]
    return areas[keys].drop_duplicates().sort_values(keys[:-1]).reset_index(drop=True)
