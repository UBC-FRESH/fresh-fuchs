"""Hermetic tests for the typed economic surface (P2.1)."""

from __future__ import annotations

import pytest

from fresh_fuchs.economy import (
    DiscountRate,
    EconomicSurface,
    PriceGroup,
    PriceRecord,
    Product,
    Provenance,
    burned_harvest_cost_per_m3,
    discounted_harvest_npv,
    green_net_revenue,
    harvest_cash_flow,
    interior_surface,
    price_group_for_species,
    sawlog_basis_salvage_margin,
    transition_mix_burned_price,
)
from fresh_fuchs.instance import SpeciesClass


def _provenance() -> Provenance:
    return Provenance(source="test", as_of="T0", units="CAD/m3", basis="test basis")


def test_price_group_for_species() -> None:
    assert price_group_for_species(SpeciesClass.SPRUCE) is PriceGroup.SPF
    assert price_group_for_species(SpeciesClass.LODGEPOLE_PINE) is PriceGroup.SPF
    assert price_group_for_species(SpeciesClass.DOUGLAS_FIR) is PriceGroup.DFLARCH
    assert price_group_for_species(SpeciesClass.OTHER) is PriceGroup.OTHER


def test_price_lookup_and_net_revenue() -> None:
    base = interior_surface()
    prices = [
        PriceRecord(
            product=Product.SAWLOG,
            price_group=PriceGroup.SPF,
            price_per_m3=127.0,
            provenance=_provenance(),
        )
    ]
    surface = EconomicSurface(
        prices=prices,
        harvest_cost=base.harvest_cost.model_copy(),
        transport_per_m3=30.0,
        stumpage_per_m3=15.0,
        replant_cost=base.replant_cost.model_copy(),
        salvage=base.salvage.model_copy(),
        discount=DiscountRate(annual_rate=0.03, provenance=_provenance()),
    )
    assert surface.sawlog_price(PriceGroup.SPF) == 127.0
    expected_net = 127.0 - surface.harvest_cost.cost_per_m3 - 30.0 - 15.0
    assert surface.net_revenue_per_m3(PriceGroup.SPF) == pytest.approx(expected_net)


def test_price_lookup_missing_raises() -> None:
    surface = interior_surface()
    with pytest.raises(KeyError):
        surface.price(PriceGroup.OTHER, Product.PULPWOOD)


def test_interior_surface_defaults_match_calibration() -> None:
    surface = interior_surface()
    assert surface.salvage.burned_price_discount == 0.65
    assert surface.salvage.volume_decay_rate == 0.85
    assert surface.discount.annual_rate == 0.03
    assert surface.transport_per_m3 == 30.0
    assert surface.stumpage_per_m3 == 15.0
    assert surface.sawlog_price(PriceGroup.SPF) == 127.0
    assert surface.sawlog_price(PriceGroup.DFLARCH) == 103.0
    assert surface.sawlog_price(PriceGroup.CEDAR) == 144.0


def test_salvage_grade_transition_is_downgrade_only_and_conserves() -> None:
    surface = interior_surface()
    rank = {Product.PEELER: 0, Product.SAWLOG: 1, Product.PULPWOOD: 2}
    for source, targets in surface.salvage.grade_transition.items():
        assert sum(targets.values()) == pytest.approx(1.0)
        for target, share in targets.items():
            assert share >= 0.0
            assert rank[target] >= rank[source], "fire can never upgrade grade"


def test_discount_factor_conventions() -> None:
    r = DiscountRate(annual_rate=0.03, provenance=_provenance())
    assert r.discount_factor(1, period_length=10) == pytest.approx((1.03) ** (-10))
    assert r.discount_factor(2, period_length=10) == pytest.approx((1.03) ** (-20))
    mid = DiscountRate(
        annual_rate=0.03,
        convention="mid_period",
        provenance=_provenance(),
    )
    assert mid.discount_factor(1, period_length=10) == pytest.approx((1.03) ** (-5))


def test_discount_factor_rejects_invalid_period() -> None:
    r = DiscountRate(annual_rate=0.03, provenance=_provenance())
    with pytest.raises(ValueError):
        r.discount_factor(0, period_length=10)


def test_replant_cost_lookup_and_default() -> None:
    surface = interior_surface()
    assert surface.replant_cost_per_ha(SpeciesClass.LODGEPOLE_PINE) == 2200.0
    assert surface.replant_cost_per_ha(SpeciesClass.DOUGLAS_FIR) == 2600.0
    assert surface.replant_cost_per_ha() == surface.replant_cost_per_ha(SpeciesClass.OTHER)


def test_every_constant_carries_provenance() -> None:
    surface = interior_surface()
    assert surface.harvest_cost.provenance.source
    assert surface.replant_cost.provenance.source
    assert surface.salvage.provenance.source
    assert surface.discount.provenance.source
    assert len(surface.prices) > 0
    for record in surface.prices:
        assert record.provenance.source
        assert record.provenance.units


def test_green_net_revenue_matches_calibration_sawlog_basis() -> None:
    surface = interior_surface()
    assert green_net_revenue(surface, SpeciesClass.LODGEPOLE_PINE) == pytest.approx(
        127.0 - 45.0 - 30.0 - 15.0
    )
    assert green_net_revenue(surface, SpeciesClass.DOUGLAS_FIR) == pytest.approx(
        103.0 - 45.0 - 30.0 - 15.0
    )


def test_burned_harvest_cost_premium() -> None:
    surface = interior_surface()
    assert burned_harvest_cost_per_m3(surface) == pytest.approx(45.0 * 1.25)


def test_sawlog_basis_salvage_margin_anchors() -> None:
    surface = interior_surface()
    sawlog_margin = sawlog_basis_salvage_margin(surface, PriceGroup.SPF)
    assert sawlog_margin == pytest.approx(127.0 * 0.65 - 56.25 - 38.0 - 0.25)

    mix_margin = (
        transition_mix_burned_price(surface, PriceGroup.SPF, source_product=Product.SAWLOG)
        - burned_harvest_cost_per_m3(surface)
        - surface.salvage.burned_transport_per_m3
        - surface.salvage.burned_stumpage_per_m3
    )
    assert -24.0 <= mix_margin <= -21.0, (
        f"transition-mix margin {mix_margin:.2f} outside -21..-24 band"
    )


def test_transition_mix_burned_price_spf() -> None:
    surface = interior_surface()
    expected = 0.65 * (0.80 * 127.0 + 0.20 * 55.0)
    assert transition_mix_burned_price(surface, PriceGroup.SPF) == pytest.approx(expected)


def test_discounted_harvest_npv_no_replant_default() -> None:
    surface = interior_surface()
    assert surface.charge_replant_in_npv is False
    npv = discounted_harvest_npv(
        surface,
        volume_m3=200.0,
        area_ha=1.0,
        period=2,
        period_length=10,
        species=SpeciesClass.LODGEPOLE_PINE,
    )
    expected = (1.03) ** (-20) * 200.0 * green_net_revenue(surface, SpeciesClass.LODGEPOLE_PINE)
    assert npv == pytest.approx(expected)


def test_harvest_cash_flow_charges_replant_when_enabled() -> None:
    surface = interior_surface().model_copy(update={"charge_replant_in_npv": True})
    flow = harvest_cash_flow(
        surface,
        volume_m3=200.0,
        area_ha=1.0,
        species=SpeciesClass.LODGEPOLE_PINE,
    )
    replant = surface.replant_cost_per_ha(SpeciesClass.LODGEPOLE_PINE)
    assert flow == pytest.approx(
        200.0 * green_net_revenue(surface, SpeciesClass.LODGEPOLE_PINE) - replant
    )
