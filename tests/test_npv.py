"""NPV objective tests (P2.5): species mapping, LP solve, cross-checks.

Uses the synthetic bundle fixture (no annex data). The key cross-checks:
(1) with a zero discount rate and no price differential across species, the
NPV-max LP reproduces the volume-max schedule exactly; (2) with the default
3% discount, NPV-max approximates the volume-max total within tolerance.
"""

from __future__ import annotations

import pandas as pd
import pytest

from fresh_fuchs.economy import (
    DiscountRate,
    NpvConfig,
    PriceGroup,
    PriceRecord,
    Product,
    Provenance,
    add_npv_problem,
    interior_surface,
    solve_npv,
    species_by_dtk_from_areas,
)
from fresh_fuchs.instance import (
    BaselineConfig,
    SpeciesClass,
    add_even_flow_problem,
    bootstrap_model,
    prepare_optimization,
    solve_even_flow,
)
from fresh_fuchs.instance.woodstock import write_woodstock_files

SYNTHETIC_DT_KEYS = [
    ("29", "managed", "1", "natural", "baseline"),
    ("29", "managed", "1", "planted", "baseline"),
    ("29", "managed", "2", "natural", "baseline"),
    ("29", "unmanaged", "2", "natural", "baseline"),
]


def _fresh_model(config):
    return prepare_optimization(bootstrap_model(config), max_initial_age=300, config=config)


def _species_map() -> dict:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


def _uniform_surface(*, annual_rate: float) -> object:
    """Surface with no price differential (both price groups price at 127) and the given rate."""
    base = interior_surface()
    provenance = Provenance(
        source="test", as_of="T0", units="CAD/m3", basis="no price differential"
    )
    prices = [
        PriceRecord(
            product=Product.SAWLOG,
            price_group=PriceGroup.SPF,
            price_per_m3=127.0,
            provenance=provenance,
        ),
        PriceRecord(
            product=Product.SAWLOG,
            price_group=PriceGroup.DFLARCH,
            price_per_m3=127.0,
            provenance=provenance,
        ),
    ]
    return base.model_copy(
        update={
            "prices": prices,
            "discount": DiscountRate(annual_rate=annual_rate, provenance=provenance),
        }
    )


def test_species_by_dtk_from_areas_requires_species_column() -> None:
    frame = pd.DataFrame(
        [{"tsa": "29", "ifm": "managed", "au_id": 1, "origin": "natural", "silv_state": "baseline"}]
    )
    with pytest.raises(ValueError):
        species_by_dtk_from_areas(frame)


def test_species_by_dtk_from_areas_mapping() -> None:
    frame = pd.DataFrame(
        [
            {
                "tsa": "29",
                "ifm": "managed",
                "au_id": 1,
                "origin": "natural",
                "silv_state": "baseline",
                "species": "PL",
            },
            {
                "tsa": "29",
                "ifm": "managed",
                "au_id": 2,
                "origin": "natural",
                "silv_state": "baseline",
                "species": "FD",
            },
            {
                "tsa": "29",
                "ifm": "managed",
                "au_id": 1,
                "origin": "natural",
                "silv_state": "baseline",
                "species": "PL",
            },
        ]
    )
    mapping = species_by_dtk_from_areas(frame)
    assert mapping[("29", "managed", "1", "natural", "baseline")] is SpeciesClass.LODGEPOLE_PINE
    assert mapping[("29", "managed", "2", "natural", "baseline")] is SpeciesClass.DOUGLAS_FIR


def test_npv_lp_solves_and_applies_schedule(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    model = _fresh_model(config)
    problem = add_npv_problem(
        model,
        NpvConfig(),
        surface=interior_surface(),
        species_by_dtk=_species_map(),
    )
    results = solve_npv(model, problem)
    assert problem.status() == "optimal"
    assert len(results) == config.horizon
    assert not results["harvest_volume_m3"].isna().any()
    assert (results["harvest_area_ha"] >= 0).all()


def test_npv_zero_discount_no_differential_matches_volume_max(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)

    vol_model = _fresh_model(config)
    vol_problem = add_even_flow_problem(vol_model, BaselineConfig())
    vol_results = solve_even_flow(vol_model, vol_problem)

    npv_model = _fresh_model(config)
    npv_problem = add_npv_problem(
        npv_model,
        NpvConfig(),
        surface=_uniform_surface(annual_rate=0.0),
        species_by_dtk=_species_map(),
    )
    npv_results = solve_npv(npv_model, npv_problem)

    assert npv_problem.status() == "optimal"
    pd.testing.assert_series_equal(
        vol_results["harvest_volume_m3"].round(6),
        npv_results["harvest_volume_m3"].round(6),
    )
    pd.testing.assert_series_equal(
        vol_results["harvest_area_ha"].round(6),
        npv_results["harvest_area_ha"].round(6),
    )


def test_npv_discount_approximates_volume_max_total(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)

    vol_model = _fresh_model(config)
    vol_results = solve_even_flow(vol_model, add_even_flow_problem(vol_model, BaselineConfig()))

    npv_model = _fresh_model(config)
    npv_problem = add_npv_problem(
        npv_model,
        NpvConfig(),
        surface=_uniform_surface(annual_rate=0.03),
        species_by_dtk=_species_map(),
    )
    npv_results = solve_npv(npv_model, npv_problem)

    vol_total = float(vol_results["harvest_volume_m3"].sum())
    npv_total = float(npv_results["harvest_volume_m3"].sum())
    assert vol_total > 0
    assert abs(npv_total - vol_total) / vol_total < 0.01
