"""Bundle loading and the Patchworks-compatible retention split.

Consumes ``femic`` (source dependency) for the analysis-unit and curve
context and the Woodstock-format yield/action/transition tables. The
retention split is fresh-fuchs-owned logic that mirrors Patchworks semantics:
a managed fragment with proportional retention is split into a managed
portion ``(1 - RETENTION)`` and an unmanaged portion ``RETENTION``.

Reference implementation (provenance): the tsa29mini demo notebook
``profile_ws3_evenflow.py`` in the ``femic-tsa29mini-instance`` bundle.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

if TYPE_CHECKING:
    from femic.fmg.core import BundleModelContext

FRAGMENT_COLUMNS = ("TSA", "AU", "ORIGIN", "SILV_STATE", "F_AGE", "IFM", "AREA_HA", "RETENTION")


class MissingDependencyError(RuntimeError):
    """Raised when an optional source dependency is not importable."""


def load_bundle_context(
    *,
    bundle_dir: Path,
    tsa_list: list[str],
) -> BundleModelContext:
    """Build the femic analysis-unit / curve context from bundle tables."""
    try:
        from femic.fmg.adapters import build_bundle_model_context_from_tables
    except ImportError as exc:  # pragma: no cover - exercised via optional extra
        raise MissingDependencyError(
            "femic is required to load a real bundle context; install the "
            "'bundle' extra (pip install 'fresh-fuchs[bundle]') or add femic "
            "to the environment."
        ) from exc

    au_table = pd.read_csv(bundle_dir / "au_table.csv")
    curve_table = pd.read_csv(bundle_dir / "curve_table.csv")
    curve_points_table = pd.read_csv(bundle_dir / "curve_points_table.csv")
    return build_bundle_model_context_from_tables(
        au_table=au_table,
        curve_table=curve_table,
        curve_points_table=curve_points_table,
        tsa_list=tsa_list,
        bundle_dir=bundle_dir,
    )


def build_woodstock_tables(context: BundleModelContext) -> dict[str, pd.DataFrame]:
    """Long-format Woodstock yields/actions/transitions via ``femic.fmg.woodstock``."""
    from femic.fmg import woodstock as femic_woodstock

    return {
        "yields": femic_woodstock.build_woodstock_yields_table(context=context),
        "actions": femic_woodstock.build_woodstock_actions_table(
            context=context,
            cc_min_age=60,
            cc_max_age=300,
        ),
        "transitions": femic_woodstock.build_woodstock_transitions_table(context=context),
    }


def load_fragments(fragments_path: Path) -> pd.DataFrame:
    """Read fragment attributes from the bundle shapefile."""
    try:
        import geopandas as gpd
    except ImportError as exc:  # pragma: no cover - exercised via optional extra
        raise MissingDependencyError(
            "geopandas is required to read the fragments shapefile; install "
            "the 'bundle' extra."
        ) from exc

    fragments = gpd.read_file(fragments_path)
    for column in FRAGMENT_COLUMNS:
        if column not in fragments.columns:
            raise ValueError(f"fragments shapefile is missing required column {column!r}")
    fragments["area_ha"] = pd.to_numeric(fragments["AREA_HA"], errors="coerce").fillna(0.0)
    fragments["retention"] = (
        pd.to_numeric(fragments["RETENTION"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
    )
    return fragments


def age_to_midpoint(age: int, *, width: int = 10) -> int:
    """Map an age to the midpoint of its ``width``-year age class.

    Standard Woodstock-style age-class discretization: a stand aged 62 is
    treated as being in the 60-69 class with midpoint 65. Keeping a single
    midpoint per class collapses the initial-age distribution (tsa29mini:
    264 distinct ages -> 44 midpoints), which keeps the Model I LP tight.
    """
    if width <= 0:
        raise ValueError(f"age class width must be positive, got {width}")
    if age < 0:
        raise ValueError(f"age must be non-negative, got {age}")
    return (age // width) * width + width // 2


def apply_retention_split(
    fragments: pd.DataFrame,
    *,
    ageclass_width: int = 10,
) -> pd.DataFrame:
    """Apply the Patchworks proportional-retention split to fragment records.

    Returns long-format area records with columns ``tsa``, ``au_id``,
    ``origin``, ``silv_state``, ``age``, ``ifm``, ``area_ha``. The total area
    is conserved across the split. Ages are bucketed to ``ageclass_width``-
    year midpoints (default 10) so ws3 stays as tight as possible.
    """
    area_rows: list[dict[str, Any]] = []
    for _, row in fragments.iterrows():
        base = {
            "tsa": str(row["TSA"]),
            "au_id": int(row["AU"]),
            "origin": str(row["ORIGIN"]),
            "silv_state": str(row["SILV_STATE"]),
            "age": age_to_midpoint(int(row["F_AGE"]), width=ageclass_width),
        }
        area = float(row["area_ha"])
        retention = float(row["retention"])
        ifm = str(row["IFM"])
        if ifm == "managed" and retention > 0.0:
            managed_area = area * (1.0 - retention)
            unmanaged_area = area * retention
            if managed_area > 0.0:
                record = base.copy()
                record.update({"ifm": "managed", "area_ha": managed_area})
                area_rows.append(record)
            if unmanaged_area > 0.0:
                record = base.copy()
                record.update({"ifm": "unmanaged", "area_ha": unmanaged_area})
                area_rows.append(record)
        else:
            record = base.copy()
            record.update({"ifm": ifm, "area_ha": area})
            area_rows.append(record)
    return pd.DataFrame(area_rows)


def managed_area_ha(areas: pd.DataFrame) -> float:
    """Managed land base in hectares after the retention split."""
    return float(areas.loc[areas["ifm"] == "managed", "area_ha"].sum())
