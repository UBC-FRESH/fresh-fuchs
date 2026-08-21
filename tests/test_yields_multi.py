"""Tests for the multi-species yield curve framework."""

from __future__ import annotations

import pytest

from fresh_fuchs.instance.species import SpeciesClass
from fresh_fuchs.instance.yields_multi import (
    MultiSpeciesYieldTable,
    YieldCurve,
    build_multi_species_yields,
    build_multi_species_yields_from_synthetic,
    generate_synthetic_curve,
)

# ---------------------------------------------------------------------------
# YieldCurve basics
# ---------------------------------------------------------------------------


class TestYieldCurve:
    def test_basic_construction(self) -> None:
        curve = YieldCurve(ages=(0, 10, 20), volumes=(0.0, 100.0, 200.0))
        assert curve.ages == (0, 10, 20)
        assert curve.volumes == (0.0, 100.0, 200.0)

    def test_mismatched_lengths_raises(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            YieldCurve(ages=(0, 10), volumes=(0.0,))

    def test_too_few_points_raises(self) -> None:
        with pytest.raises(ValueError, match="at least 2 points"):
            YieldCurve(ages=(0,), volumes=(0.0,))

    def test_unsorted_ages_raises(self) -> None:
        with pytest.raises(ValueError, match="ages must be sorted"):
            YieldCurve(ages=(20, 10, 0), volumes=(200.0, 100.0, 0.0))

    def test_volume_at_age_exact(self) -> None:
        curve = YieldCurve(ages=(0, 10, 20), volumes=(0.0, 100.0, 200.0))
        assert curve.volume_at_age(0) == 0.0
        assert curve.volume_at_age(10) == 100.0
        assert curve.volume_at_age(20) == 200.0

    def test_volume_at_age_interpolated(self) -> None:
        curve = YieldCurve(ages=(0, 10, 20), volumes=(0.0, 100.0, 200.0))
        assert curve.volume_at_age(5) == pytest.approx(50.0)
        assert curve.volume_at_age(15) == pytest.approx(150.0)

    def test_volume_at_age_clamped(self) -> None:
        curve = YieldCurve(ages=(0, 10, 20), volumes=(0.0, 100.0, 200.0))
        assert curve.volume_at_age(-5) == 0.0
        assert curve.volume_at_age(30) == 200.0


# ---------------------------------------------------------------------------
# MultiSpeciesYieldTable
# ---------------------------------------------------------------------------


class TestMultiSpeciesYieldTable:
    def _make_table(self) -> MultiSpeciesYieldTable:
        c1 = YieldCurve(ages=(0, 10, 20), volumes=(0.0, 100.0, 200.0))
        c2 = YieldCurve(ages=(0, 10, 20), volumes=(0.0, 80.0, 160.0))
        return MultiSpeciesYieldTable(
            curves={
                (1, SpeciesClass.LODGEPOLE_PINE): c1,
                (1, SpeciesClass.SPRUCE): c2,
                (2, SpeciesClass.LODGEPOLE_PINE): c1,
            }
        )

    def test_get_existing(self) -> None:
        table = self._make_table()
        curve = table.get(1, SpeciesClass.LODGEPOLE_PINE)
        assert curve is not None
        assert curve.volume_at_age(10) == 100.0

    def test_get_missing(self) -> None:
        table = self._make_table()
        assert table.get(1, SpeciesClass.DOUGLAS_FIR) is None
        assert table.get(99, SpeciesClass.LODGEPOLE_PINE) is None

    def test_available_species(self) -> None:
        table = self._make_table()
        sp = table.available_species(1)
        assert sp == [SpeciesClass.LODGEPOLE_PINE, SpeciesClass.SPRUCE]
        assert table.available_species(2) == [SpeciesClass.LODGEPOLE_PINE]
        assert table.available_species(99) == []

    def test_all_au_ids(self) -> None:
        table = self._make_table()
        assert table.all_au_ids() == [1, 2]

    def test_species_for_au(self) -> None:
        table = self._make_table()
        result = table.species_for_au(1)
        assert set(result.keys()) == {SpeciesClass.LODGEPOLE_PINE, SpeciesClass.SPRUCE}

    def test_curve_count(self) -> None:
        table = self._make_table()
        assert table.curve_count == 3


# ---------------------------------------------------------------------------
# Synthetic curve generation
# ---------------------------------------------------------------------------


class TestGenerateSyntheticCurve:
    def test_basic_curve(self) -> None:
        curve = generate_synthetic_curve(SpeciesClass.LODGEPOLE_PINE, "M")
        assert len(curve.ages) > 0
        assert curve.ages[0] == 0
        assert curve.volumes[0] == 0.0
        # Volume should increase with age
        assert curve.volume_at_age(50) > curve.volume_at_age(20)

    def test_si_level_scaling(self) -> None:
        low = generate_synthetic_curve(SpeciesClass.LODGEPOLE_PINE, "L")
        med = generate_synthetic_curve(SpeciesClass.LODGEPOLE_PINE, "M")
        high = generate_synthetic_curve(SpeciesClass.LODGEPOLE_PINE, "H")
        # Higher SI should produce higher volumes at the same age
        assert low.volume_at_age(50) < med.volume_at_age(50)
        assert med.volume_at_age(50) < high.volume_at_age(50)

    def test_species_differ(self) -> None:
        pl = generate_synthetic_curve(SpeciesClass.LODGEPOLE_PINE, "M")
        fd = generate_synthetic_curve(SpeciesClass.DOUGLAS_FIR, "M")
        sx = generate_synthetic_curve(SpeciesClass.SPRUCE, "M")
        # Different species produce different curves
        assert fd.volume_at_age(50) != pl.volume_at_age(50)
        assert pl.volume_at_age(50) != sx.volume_at_age(50)

    def test_custom_age_range(self) -> None:
        curve = generate_synthetic_curve(
            SpeciesClass.SPRUCE, "M", max_age=100, step=5
        )
        assert curve.ages[-1] == 100
        assert len(curve.ages) == 21  # 0, 5, ..., 100


# ---------------------------------------------------------------------------
# Build multi-species yields (synthetic)
# ---------------------------------------------------------------------------


class TestBuildMultiSpeciesYields:
    def test_default_build(self) -> None:
        table = build_multi_species_yields(
            au_table=None, target_species=[SpeciesClass.LODGEPOLE_PINE]
        )
        assert table.curve_count > 0
        # Default AU range is 1..100
        assert 1 in table.all_au_ids()
        assert 100 in table.all_au_ids()

    def test_from_au_table(self) -> None:
        import pandas as pd

        au_table = pd.DataFrame(
            [
                {"au_id": 101, "si_level": "H"},
                {"au_id": 102, "si_level": "L"},
            ]
        )
        table = build_multi_species_yields(au_table=au_table)
        assert set(table.all_au_ids()) == {101, 102}
        # AU 101 (high SI) should have higher PL volume than AU 102 (low SI)
        c101 = table.get(101, SpeciesClass.LODGEPOLE_PINE)
        c102 = table.get(102, SpeciesClass.LODGEPOLE_PINE)
        assert c101 is not None and c102 is not None
        assert c101.volume_at_age(50) > c102.volume_at_age(50)

    def test_all_species_present(self) -> None:
        table = build_multi_species_yields_from_synthetic(
            [1],
            target_species=None,
        )
        # With default target_species, all 4 classes should be present
        sp = table.available_species(1)
        assert len(sp) == 4

    def test_native_species_metadata(self) -> None:
        table = build_multi_species_yields_from_synthetic(
            [1],
            native_species={1: SpeciesClass.LODGEPOLE_PINE},
        )
        # Native species should still have a curve
        assert table.get(1, SpeciesClass.LODGEPOLE_PINE) is not None
