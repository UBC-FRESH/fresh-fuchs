"""Static species classification for the tsa29mini instance.

Re-scoped P1.3: the bundle carries no age-varying species-proportion curves
(all 108 curves are ``treated``/``untreated``), so species composition is
carried as a static primary-species class per analysis unit, derived from the
AU table's ``canfi_species`` code. This keeps the ws3 model tight (no species
theme, no development-type growth) while giving Phase 4 a species area-share
composition surface for targets.

Provenance: the CANFI species codes are assigned in femic
(``femic/resources/legacy/00_data-prep.py`` ``canfi_map``); the codes present
in the tsa29mini AU table are 100 (spruce), 204 (lodgepole pine), 500
(Douglas-fir).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import pandas as pd


class SpeciesClass(StrEnum):
    """Primary species classes used by the instance composition surface."""

    SPRUCE = "SX"
    LODGEPOLE_PINE = "PL"
    DOUGLAS_FIR = "FD"
    OTHER = "OT"


CANFI_SPECIES_CLASS: dict[int, SpeciesClass] = {
    100: SpeciesClass.SPRUCE,  # SX / S (spruce)
    204: SpeciesClass.LODGEPOLE_PINE,  # PL / PLI (lodgepole pine)
    500: SpeciesClass.DOUGLAS_FIR,  # FD / FDI / FDC (Douglas-fir)
}


def species_class_for_canfi(code: int) -> SpeciesClass:
    """Map a CANFI species code to a :class:`SpeciesClass`.

    Unknown codes map to :attr:`SpeciesClass.OTHER`; the loader surfaces
    unknown codes as diagnostics rather than failing on new data.
    """
    return CANFI_SPECIES_CLASS.get(int(code), SpeciesClass.OTHER)


def load_species_by_au(bundle_dir: Path) -> dict[int, SpeciesClass]:
    """Read the AU table and return ``au_id -> SpeciesClass``.

    Uses the ``au_id`` and ``canfi_species`` columns of
    ``au_table.csv``. Emits a warning listing any unknown CANFI codes
    (mapped to :attr:`SpeciesClass.OTHER`).
    """
    au_table = pd.read_csv(bundle_dir / "au_table.csv")
    if "au_id" not in au_table.columns or "canfi_species" not in au_table.columns:
        raise ValueError(
            "au_table.csv must provide 'au_id' and 'canfi_species' columns to "
            "derive the species classification"
        )

    unknown_codes: set[int] = set()
    species_by_au: dict[int, SpeciesClass] = {}
    for _, row in au_table.iterrows():
        code = int(row["canfi_species"])
        species = species_class_for_canfi(code)
        if species is SpeciesClass.OTHER:
            unknown_codes.add(code)
        species_by_au[int(row["au_id"])] = species

    if unknown_codes:
        import warnings

        warnings.warn(
            "unknown CANFI species code(s) mapped to OTHER: "
            + ", ".join(str(code) for code in sorted(unknown_codes)),
            stacklevel=2,
        )
    return species_by_au
