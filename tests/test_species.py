"""Hermetic tests for the static species classification (P1.3, re-scoped)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fresh_fuchs.instance import (
    SpeciesClass,
    apply_retention_split,
    development_type_species,
    load_species_by_au,
    managed_landscape_composition,
    species_class_for_canfi,
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (100, SpeciesClass.SPRUCE),
        (204, SpeciesClass.LODGEPOLE_PINE),
        (500, SpeciesClass.DOUGLAS_FIR),
    ],
)
def test_species_class_for_canfi_known_codes(code: int, expected: SpeciesClass) -> None:
    assert species_class_for_canfi(code) is expected


def test_species_class_for_canfi_unknown_code_maps_to_other() -> None:
    assert species_class_for_canfi(999) is SpeciesClass.OTHER


def test_load_species_by_au_from_table(tmp_path: Path) -> None:
    pd.DataFrame(
        [
            {"au_id": 1, "canfi_species": 100},
            {"au_id": 2, "canfi_species": 204},
            {"au_id": 3, "canfi_species": 500},
            {"au_id": 4, "canfi_species": 999},
        ]
    ).to_csv(tmp_path / "au_table.csv", index=False)

    with pytest.warns(UserWarning, match="999"):
        species_by_au = load_species_by_au(tmp_path)

    assert species_by_au[1] is SpeciesClass.SPRUCE
    assert species_by_au[2] is SpeciesClass.LODGEPOLE_PINE
    assert species_by_au[3] is SpeciesClass.DOUGLAS_FIR
    assert species_by_au[4] is SpeciesClass.OTHER


def test_load_species_by_au_requires_columns(tmp_path: Path) -> None:
    pd.DataFrame([{"au_id": 1}]).to_csv(tmp_path / "au_table.csv", index=False)
    with pytest.raises(ValueError, match="canfi_species"):
        load_species_by_au(tmp_path)


def _fragments() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "TSA": "29",
                "AU": 1,
                "ORIGIN": "natural",
                "SILV_STATE": "baseline",
                "F_AGE": 196,
                "IFM": "managed",
                "AREA_HA": 10.0,
                "RETENTION": 0.0,
                "area_ha": 10.0,
                "retention": 0.0,
            },
            {
                "TSA": "29",
                "AU": 2,
                "ORIGIN": "natural",
                "SILV_STATE": "baseline",
                "F_AGE": 196,
                "IFM": "managed",
                "AREA_HA": 20.0,
                "RETENTION": 0.0,
                "area_ha": 20.0,
                "retention": 0.0,
            },
            {
                "TSA": "29",
                "AU": 3,
                "ORIGIN": "planted",
                "SILV_STATE": "baseline",
                "F_AGE": 45,
                "IFM": "managed",
                "AREA_HA": 5.0,
                "RETENTION": 0.0,
                "area_ha": 5.0,
                "retention": 0.0,
            },
            {
                "TSA": "29",
                "AU": 3,
                "ORIGIN": "natural",
                "SILV_STATE": "baseline",
                "F_AGE": 196,
                "IFM": "unmanaged",
                "AREA_HA": 30.0,
                "RETENTION": 0.0,
                "area_ha": 30.0,
                "retention": 0.0,
            },
        ]
    )


def test_apply_retention_split_adds_species() -> None:
    species_by_au = {1: SpeciesClass.SPRUCE, 2: SpeciesClass.LODGEPOLE_PINE}
    areas = apply_retention_split(_fragments(), species_by_au=species_by_au)

    assert "species" in areas.columns
    assert sorted(areas["species"].unique()) == ["OT", "PL", "SX"]
    assert areas.loc[areas["au_id"] == 1, "species"].eq("SX").all()
    assert areas.loc[areas["au_id"] == 2, "species"].eq("PL").all()
    assert areas.loc[areas["au_id"] == 3, "species"].eq("OT").all()


def test_apply_retention_split_without_species_is_backwards_compatible() -> None:
    areas = apply_retention_split(_fragments())
    assert "species" not in areas.columns


def test_managed_landscape_composition_conserves_area() -> None:
    species_by_au = {1: SpeciesClass.SPRUCE, 2: SpeciesClass.LODGEPOLE_PINE}
    areas = apply_retention_split(_fragments(), species_by_au=species_by_au)

    composition = managed_landscape_composition(areas)
    managed_area = float(areas.loc[areas["ifm"] == "managed", "area_ha"].sum())

    assert composition["share"].sum() == pytest.approx(1.0)
    assert composition["area_ha"].sum() == pytest.approx(managed_area)
    assert composition["share"].is_monotonic_decreasing
    assert set(composition["species"]) == {"SX", "PL", "OT"}


def test_managed_landscape_composition_requires_species_column() -> None:
    with pytest.raises(ValueError, match="species"):
        managed_landscape_composition(_fragments())


def test_development_type_species_unique_per_key() -> None:
    species_by_au = {1: SpeciesClass.SPRUCE, 2: SpeciesClass.LODGEPOLE_PINE}
    areas = apply_retention_split(_fragments(), species_by_au=species_by_au)

    dts = development_type_species(areas)
    keys = ["tsa", "ifm", "au_id", "origin", "silv_state", "age"]
    assert dts[keys].duplicated().sum() == 0
    assert len(dts) == len(areas)
    assert set(dts["species"]) == {"SX", "PL", "OT"}
