"""Multi-species yield curve framework for species-switching replant transitions.

Provides yield curves for all target species at each analysis unit, enabling
the replant actions (harvest_pl, harvest_sx, harvest_fd, harvest_ot) to use
species-appropriate growth projections.

Strategy (ordered by data availability):

1. **Bundle species proportion curves**: If the femic bundle provides
   ``managed_species_prop_<species>`` curves (via ``BundleModelContext.
   managed_species_curve_ids``), multiply total volume by the species
   proportion at each age.

2. **Site-index transfer**: Use the AU's ``si_level`` (L/M/H) as a
   grouping variable. Within each group, apply species-specific growth
   functions scaled by a site-index conversion factor.

3. **Synthetic fallback**: Use species-specific Chapman-Richards growth
   curves with parameter defaults by species class. This is the current
   default path when no bundle data is available.

Data dependency (updated, P6.6/P6.7):

The tsa29mini bundle ships ``treated``/``untreated`` aggregate curves only
(no species-proportion sidecars). Real per-(AU, target-species) plantation
curves for the replant options were generated with BatchTIPSY (BTC) in
P6.6 and live in the instance dataset repo as
``data/tipsy_curves_tsa29mini_replant.csv`` +
``data/tipsy_replant_manifest-tsa29mini.csv`` (see
``load_replant_curves_from_btc``). Bundle species-proportion curves remain
unpopulated; synthetic Chapman-Richards is the explicit fallback.

Provenance:

- Species growth parameters derived from BC forestry yield curve literature
  (Chapman-Richards form: V = a * (1 - exp(-b * age))^c)
- Site-index levels mapped to SI_50 values: L=15m, M=25m, H=35m
- CANFI species codes: 100 (SX), 204 (PL), 500 (FD)
- BTC replant curves: femic-tsa29mini-instance branch
  ``feature/replant-tipsy-curves`` (run manifest
  ``data/tipsy_replant_run_manifest.json``)
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fresh_fuchs.instance.species import SpeciesClass

# ---------------------------------------------------------------------------
# Yield curve data structure
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class YieldCurve:
    """A single yield curve (age -> volume m3/ha).

    Points are sorted by age. Interpolation is caller's responsibility.
    """

    ages: tuple[int, ...]
    volumes: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.ages) != len(self.volumes):
            raise ValueError("ages and volumes must have the same length")
        if len(self.ages) < 2:
            raise ValueError("yield curve must have at least 2 points")
        if self.ages != tuple(sorted(self.ages)):
            raise ValueError("ages must be sorted")

    def volume_at_age(self, age: int) -> float:
        """Linearly interpolate volume at a given age, clamped to curve bounds."""
        if age <= self.ages[0]:
            return self.volumes[0]
        if age >= self.ages[-1]:
            return self.volumes[-1]
        for i in range(len(self.ages) - 1):
            if self.ages[i] <= age <= self.ages[i + 1]:
                t = (age - self.ages[i]) / (self.ages[i + 1] - self.ages[i])
                return self.volumes[i] + t * (self.volumes[i + 1] - self.volumes[i])
        return self.volumes[-1]


@dataclass(frozen=True)
class MultiSpeciesYieldTable:
    """Yield curves for all target species at each analysis unit.

    Keys: ``(au_id, target_species)`` -> :class:`YieldCurve`.

    This is the central data structure consumed by the replant action
    registration (Phase 2) and LP wiring (Phase 3).
    """

    curves: dict[tuple[int, SpeciesClass], YieldCurve] = field(default_factory=dict)

    def get(self, au_id: int, species: SpeciesClass) -> YieldCurve | None:
        """Look up a yield curve for an AU and target species."""
        return self.curves.get((au_id, species))

    def available_species(self, au_id: int) -> list[SpeciesClass]:
        """Return species with yield curves available for an AU."""
        return sorted(
            {sp for (au, sp) in self.curves if au == au_id}, key=lambda s: s.value
        )

    def all_au_ids(self) -> list[int]:
        """Return all AU IDs with at least one yield curve."""
        return sorted({au for (au, _sp) in self.curves})

    def species_for_au(self, au_id: int) -> dict[SpeciesClass, YieldCurve]:
        """Return all yield curves for an AU, keyed by species."""
        return {
            sp: self.curves[(au_id, sp)]
            for (au, sp) in self.curves
            if au == au_id
        }

    @property
    def curve_count(self) -> int:
        """Total number of yield curves in the table."""
        return len(self.curves)


# ---------------------------------------------------------------------------
# Chapman-Richards growth function (synthetic fallback)
# ---------------------------------------------------------------------------

# Species-specific parameter defaults (Chapman-Richards form):
#   V(age) = a * (1 - exp(-b * age))^c
#
# Parameters calibrated to match typical BC yield curves at SI_50 = 25m.
# Site-index scaling: a is multiplied by (SI / 25)^alpha.

_CHAPMAN_RICHARDS_PARAMS: dict[SpeciesClass, dict[str, float]] = {
    SpeciesClass.LODGEPOLE_PINE: {
        "a": 420.0,
        "b": 0.012,
        "c": 1.8,
        "si_alpha": 1.0,
    },
    SpeciesClass.SPRUCE: {
        "a": 380.0,
        "b": 0.010,
        "c": 2.0,
        "si_alpha": 1.1,
    },
    SpeciesClass.DOUGLAS_FIR: {
        "a": 500.0,
        "b": 0.008,
        "c": 2.2,
        "si_alpha": 1.2,
    },
    SpeciesClass.OTHER: {
        "a": 350.0,
        "b": 0.011,
        "c": 1.9,
        "si_alpha": 1.0,
    },
}

# Site-index levels mapped to SI_50 values (meters at age 50).
SI_LEVEL_MAP: dict[str, float] = {
    "L": 15.0,
    "M": 25.0,
    "H": 35.0,
}

REFERENCE_SI = 25.0


def _chapman_richards(
    age: int,
    *,
    a: float,
    b: float,
    c: float,
) -> float:
    """Evaluate Chapman-Richards growth function at a given age."""
    if age <= 0:
        return 0.0
    return a * (1.0 - np.exp(-b * age)) ** c


def generate_synthetic_curve(
    species: SpeciesClass,
    si_level: str = "M",
    *,
    max_age: int = 300,
    step: int = 10,
) -> YieldCurve:
    """Generate a synthetic yield curve for a species at a given site-index level.

    Uses the Chapman-Richards form with species-specific parameters, scaled
    by the site-index level relative to the reference SI (25m).

    Parameters
    ----------
    species:
        Target species class.
    si_level:
        Site-index level: ``"L"`` (low), ``"M"`` (medium), or ``"H"`` (high).
    max_age:
        Maximum age for the curve.
    step:
        Age step between curve points.

    Returns
    -------
    YieldCurve
        Decadal yield curve from age 0 to ``max_age``.
    """
    params = _CHAPMAN_RICHARDS_PARAMS.get(species, _CHAPMAN_RICHARDS_PARAMS[SpeciesClass.OTHER])
    si = SI_LEVEL_MAP.get(si_level.upper(), REFERENCE_SI)
    scale = (si / REFERENCE_SI) ** params["si_alpha"]
    a_scaled = params["a"] * scale

    ages = list(range(0, max_age + 1, step))
    volumes = [_chapman_richards(age, a=a_scaled, b=params["b"], c=params["c"]) for age in ages]
    return YieldCurve(ages=tuple(ages), volumes=tuple(volumes))


# ---------------------------------------------------------------------------
# BTC replant curve store (real TIPSY data, P6.6)
# ---------------------------------------------------------------------------

# Manifest ``target_species`` codes -> SpeciesClass.
BTC_SPECIES_MAP: dict[str, SpeciesClass] = {
    "PL": SpeciesClass.LODGEPOLE_PINE,
    "SW": SpeciesClass.SPRUCE,
    "SX": SpeciesClass.SPRUCE,
    "FD": SpeciesClass.DOUGLAS_FIR,
}


def load_replant_curves_from_btc(
    curves_csv: str | Path,
    manifest_csv: str | Path,
    *,
    max_age: int | None = None,
) -> MultiSpeciesYieldTable:
    """Load the BatchTIPSY replant curve store (P6.6 artifacts).

    Parameters
    ----------
    curves_csv:
        Long-format BTC curves (columns ``AU, Age, Yield``; femic
        ``parse_btc_tsr_transposed_output`` layout), e.g. the instance's
        ``data/tipsy_curves_tsa29mini_replant.csv``.
    manifest_csv:
        Replant option manifest mapping ``feature_id`` ->
        ``(au_id, target_species, ...)``, e.g.
        ``data/tipsy_replant_manifest-tsa29mini.csv``.
    max_age:
        Optional upper age bound; points above are dropped.

    Returns
    -------
    MultiSpeciesYieldTable
        Real TIPSY curves keyed by ``(au_id, SpeciesClass)``.

    Raises
    ------
    ValueError
        If required columns are missing or a ``feature_id`` has an
        unmapped ``target_species``.
    """
    curves_frame = pd.read_csv(curves_csv)
    manifest = pd.read_csv(manifest_csv)
    for col in ("AU", "Age", "Yield"):
        if col not in curves_frame.columns:
            raise ValueError(f"BTC curves file missing required column {col!r}")
    for col in ("feature_id", "au_id", "target_species"):
        if col not in manifest.columns:
            raise ValueError(f"replant manifest missing required column {col!r}")

    option_by_fid = {
        int(r.feature_id): (int(r.au_id), str(r.target_species).strip().upper())
        for r in manifest.itertuples()
    }

    curves: dict[tuple[int, SpeciesClass], YieldCurve] = {}
    for fid, group in curves_frame.groupby("AU"):
        if int(fid) not in option_by_fid:
            raise ValueError(f"BTC curve feature_id {fid} not in replant manifest")
        au_id, species_code = option_by_fid[int(fid)]
        species = BTC_SPECIES_MAP.get(species_code)
        if species is None:
            raise ValueError(
                f"manifest feature_id {fid}: unmapped target_species {species_code!r}"
            )
        group = group.sort_values("Age")
        ages = [int(a) for a in group["Age"]]
        volumes = [float(v) for v in group["Yield"]]
        if max_age is not None:
            clipped = [(a, v) for a, v in zip(ages, volumes) if a <= max_age]
            ages = [a for a, _v in clipped]
            volumes = [v for _a, v in clipped]
        curves[(au_id, species)] = YieldCurve(ages=tuple(ages), volumes=tuple(volumes))
    return MultiSpeciesYieldTable(curves=curves)


# ---------------------------------------------------------------------------
# Build multi-species yield table
# ---------------------------------------------------------------------------


def build_multi_species_yields_from_synthetic(
    au_ids: list[int],
    *,
    native_species: dict[int, SpeciesClass] | None = None,
    si_levels: dict[int, str] | None = None,
    target_species: list[SpeciesClass] | None = None,
    max_age: int = 300,
    step: int = 10,
) -> MultiSpeciesYieldTable:
    """Build a multi-species yield table using synthetic curves.

    This is the current default path when no bundle data is available.
    Each AU gets yield curves for all target species, using the AU's
    site-index level for curve scaling.

    Parameters
    ----------
    au_ids:
        List of analysis unit IDs.
    native_species:
        Mapping of ``au_id -> SpeciesClass`` for the native species.
        If ``None``, all species are generated for all AUs.
    si_levels:
        Mapping of ``au_id -> si_level`` (``"L"``, ``"M"``, ``"H"``).
        If ``None``, defaults to ``"M"`` for all AUs.
    target_species:
        Species to generate curves for. If ``None``, generates for
        all four species classes.
    max_age:
        Maximum age for yield curves.
    step:
        Age step between curve points.

    Returns
    -------
    MultiSpeciesYieldTable
        Yield curves for all (au_id, species) combinations.
    """
    if target_species is None:
        target_species = list(SpeciesClass)
    if native_species is None:
        native_species = {}
    if si_levels is None:
        si_levels = {}

    curves: dict[tuple[int, SpeciesClass], YieldCurve] = {}
    for au_id in au_ids:
        si = si_levels.get(au_id, "M")
        for species in target_species:
            curve = generate_synthetic_curve(species, si, max_age=max_age, step=step)
            curves[(au_id, species)] = curve

    return MultiSpeciesYieldTable(curves=curves)


def build_multi_species_yields_from_bundle_context(
    context: Any,
    *,
    target_species: list[SpeciesClass] | None = None,
) -> MultiSpeciesYieldTable:
    """Build a multi-species yield table from a femic BundleModelContext.

    Uses the ``managed_species_curve_ids`` mapping from the bundle context
    to look up species-specific proportion curves. For each AU, multiplies
    the total volume curve by the species proportion at each age.

    Falls back to synthetic curves for species without proportion data.

    Parameters
    ----------
    context:
        A ``femic.fmg.core.BundleModelContext`` instance.
    target_species:
        Species to generate curves for. If ``None``, generates for
        all four species classes.

    Returns
    -------
    MultiSpeciesYieldTable
        Yield curves for all available (au_id, species) combinations.
    """
    if target_species is None:
        target_species = list(SpeciesClass)

    curves: dict[tuple[int, SpeciesClass], YieldCurve] = {}

    for au in context.analysis_units:
        au_id = au.au_id

        for species in target_species:
            species_key = species.value.lower()

            # Try managed species proportion curve
            managed_map = context.managed_species_curve_ids.get(au_id, {})
            prop_curve_id = managed_map.get(species_key)

            if prop_curve_id is not None and prop_curve_id in context.curves_by_id:
                # Get the base managed curve for total volume
                base_curve = context.curves_by_id.get(au.managed_curve_id)
                prop_curve = context.curves_by_id[prop_curve_id]

                if base_curve is not None and prop_curve.points:
                    # Build proportion lookup (age -> proportion)
                    prop_lookup = {int(p.x): float(p.y) for p in prop_curve.points}

                    ages: list[int] = []
                    volumes: list[float] = []
                    for pt in base_curve.points:
                        age = int(pt.x)
                        total_vol = float(pt.y)
                        prop = prop_lookup.get(age, 0.0)
                        ages.append(age)
                        volumes.append(total_vol * prop)

                    if ages:
                        curves[(au_id, species)] = YieldCurve(
                            ages=tuple(ages), volumes=tuple(volumes)
                        )
                        continue

            # Fallback: generate synthetic curve using AU's si_level
            si_level = getattr(au, "si_level", "M")
            curve = generate_synthetic_curve(species, si_level)
            curves[(au_id, species)] = curve

    return MultiSpeciesYieldTable(curves=curves)


def build_multi_species_yields(
    *,
    au_table: pd.DataFrame | None = None,
    bundle_context: Any = None,
    replant_curves: MultiSpeciesYieldTable | None = None,
    native_species: dict[int, SpeciesClass] | None = None,
    target_species: list[SpeciesClass] | None = None,
    max_age: int = 300,
    step: int = 10,
) -> MultiSpeciesYieldTable:
    """Build multi-species yield curves from the best available data source.

    Strategy (ordered by data availability):

    1. If ``replant_curves`` (a real BTC replant curve store, e.g. from
       :func:`load_replant_curves_from_btc`) covers an ``(au_id, species)``
       combination, that real TIPSY curve wins.
    2. If ``bundle_context`` is provided and has species proportion curves,
       use :func:`build_multi_species_yields_from_bundle_context` for the
       remaining combinations.
    3. Synthetic site-index-scaled curves fill the rest, emitting a
       ``UserWarning`` diagnostic naming the uncovered combinations.

    Parameters
    ----------
    au_table:
        AU table DataFrame (optional). Used for AU IDs and si_levels.
    bundle_context:
        femic ``BundleModelContext`` (optional). Used for species proportion
        curves when available.
    replant_curves:
        Real BTC replant curve store (optional); takes precedence for every
        covered ``(au_id, species)``.
    native_species:
        Mapping of ``au_id -> SpeciesClass`` for the native species.
    target_species:
        Species to generate curves for. If ``None``, generates for all.
    max_age:
        Maximum age for synthetic yield curves.
    step:
        Age step for synthetic yield curves.

    Returns
    -------
    MultiSpeciesYieldTable
        Yield curves for all available (au_id, species) combinations.
    """
    if target_species is None:
        target_species = list(SpeciesClass)
    if bundle_context is not None:
        base = build_multi_species_yields_from_bundle_context(
            bundle_context, target_species=target_species
        )
    else:
        # Extract AU IDs and si_levels from au_table or use defaults
        if au_table is not None and "au_id" in au_table.columns:
            au_ids = sorted(au_table["au_id"].astype(int).unique().tolist())
            si_levels: dict[int, str] = {}
            if "si_level" in au_table.columns:
                for _, row in au_table.iterrows():
                    si_levels[int(row["au_id"])] = str(row["si_level"]).strip().upper()
        else:
            au_ids = list(range(1, 101))
            si_levels = {}
        base = build_multi_species_yields_from_synthetic(
            au_ids,
            native_species=native_species,
            si_levels=si_levels,
            target_species=target_species,
            max_age=max_age,
            step=step,
        )

    if replant_curves is None:
        return base

    merged = dict(base.curves)
    for key, curve in replant_curves.curves.items():
        if key[1] in target_species:
            merged[key] = curve
    missing = sorted(
        k for k in merged if k not in replant_curves.curves and k[0] in replant_curves.all_au_ids()
    )
    if missing:
        warnings.warn(
            "no real BTC replant curve for "
            f"{len(missing)} (au_id, species) combinations; using synthetic: "
            + ", ".join(f"({au}, {sp.value})" for au, sp in missing[:10])
            + (" ..." if len(missing) > 10 else ""),
            stacklevel=2,
        )
    return MultiSpeciesYieldTable(curves=merged)
