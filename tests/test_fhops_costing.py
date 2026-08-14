"""Hermetic tests for the fhops machine-rate harvest cost estimator (P2.2).

The fhops dependency is optional: these tests skip when fhops is not
installed so CI (which installs only ``.[dev]``) stays green.
"""

from __future__ import annotations

import pytest

from fresh_fuchs.economy import (
    HarvestCostModel,
    StandAttributes,
    default_clearcut_stand,
)

fhops = pytest.importorskip("fhops")


def test_default_stand_is_sensible() -> None:
    stand = default_clearcut_stand()
    assert stand.avg_stem_size_m3 > 0
    assert stand.volume_per_ha > 0
    assert stand.stem_density_per_ha > 0
    assert stand.ground_slope_pct >= 0


def test_single_pass_estimate_record() -> None:
    record = HarvestCostModel().estimate()
    assert record.basis == "fhops"
    assert record.cpi_year == 2024
    assert record.cost_per_m3 > 0.0
    assert record.provenance.source
    assert "feller_buncher" in record.provenance.notes


def test_system_estimate_sums_passes() -> None:
    model = HarvestCostModel()
    single = model.estimate().cost_per_m3
    system = model.system_estimate()
    assert system.cost_per_m3 > single
    assert system.basis == "fhops"
    assert "feller_buncher" in system.provenance.notes


def test_system_estimate_vs_tree_to_truck_range() -> None:
    system = HarvestCostModel().system_estimate().cost_per_m3
    assert 20.0 < system < 45.0


def test_custom_stand_changes_cost() -> None:
    stand = StandAttributes(
        avg_stem_size_m3=0.8,
        volume_per_ha=300.0,
        stem_density_per_ha=1200.0,
        ground_slope_pct=10.0,
    )
    rich = HarvestCostModel().estimate(stand).cost_per_m3
    poor = HarvestCostModel().estimate(default_clearcut_stand()).cost_per_m3
    assert rich < poor
