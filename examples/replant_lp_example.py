"""Species-switching replant LP example.

Demonstrates a fire-aware even-flow NPV-maximizing LP where the solver
can choose to replant harvested stands with a different species.  Uses
the synthetic instance (no annex bundle required).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from fresh_fuchs.economy import DiscountRate, PriceGroup, PriceRecord, Product, Provenance
from fresh_fuchs.economy.types import interior_surface
from fresh_fuchs.instance import SpeciesClass, bootstrap_model, prepare_optimization
from fresh_fuchs.instance.replant import add_replant_actions, target_species_from_acode
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.scenario import (
    DisturbanceScenario,
    FireEvent,
    FireLpConfig,
    add_fire_problem,
    add_salvage_action,
    apply_salvage_operability,
    solve_fire_lp,
)

AU1, AU2 = 1, 2
ZONE_BY_AU = {AU1: "SBPS", AU2: "IDF"}


def _fresh_model(config, tmp_path):
    return prepare_optimization(bootstrap_model(config), max_initial_age=300, config=config)


def _species_map() -> dict:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


def main() -> None:
    from fresh_fuchs.instance import InstanceConfig

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config = InstanceConfig(
            model_name="replant-example",
            model_path=tmp_path,
            horizon=3,
            period_length=10,
            max_age=300,
            min_harvest_age=60,
            max_harvest_age=300,
        )

        from fresh_fuchs.instance.synthetic import build_synthetic_areas, build_synthetic_yields

        yields = build_synthetic_yields()
        areas = build_synthetic_areas()
        write_woodstock_files(areas=areas, yields=yields, config=config)

        # Build model with replant actions for spruce and Douglas-fir
        model = _fresh_model(config, tmp_path)
        model = add_replant_actions(
            model, target_species=(SpeciesClass.SPRUCE, SpeciesClass.DOUGLAS_FIR)
        )
        model = add_salvage_action(model, max_age=300)

        # Fire-free scenario (no burns)
        scenario = DisturbanceScenario(
            name="example-scenario",
            seed=42,
            probability=1.0,
            burn_rate_multiplier=1.0,
            price_factor=1.0,
            severity="Moderate",
            events=tuple(
                FireEvent(period=t, zone=zone, annual_burn_rate=0.0, severity="Moderate")
                for zone in ZONE_BY_AU.values()
                for t in range(1, config.horizon + 1)
            ),
        )

        model = apply_salvage_operability(model, scenario=scenario, zone_by_au=ZONE_BY_AU)

        # Configure LP with replant action codes
        action_codes = ("null", "harvest", "salvage", "harvest_SX", "harvest_FD")
        cfg = FireLpConfig(zone_by_au=ZONE_BY_AU, action_codes=action_codes)

        problem = add_fire_problem(
            model,
            cfg,
            scenario=scenario,
            surface=interior_surface(),
            species_by_dtk=_species_map(),
        )

        results = solve_fire_lp(
            model,
            problem,
            scenario=scenario,
            config=cfg,
            replant_action_codes=("harvest_SX", "harvest_FD"),
        )

        print("=== Species-Switching Replant LP Results ===")
        print(f"LP status: {problem.status()}")
        print(f"Objective (NPV): ${float(problem.z()):,.0f}")
        print()
        print(results.to_string(index=False))
        print()
        print(f"Total harvest area: {results['harvest_area_ha'].sum():,.1f} ha")
        print(f"Total harvest volume: {results['harvest_volume_m3'].sum():,.0f} m3")

        # Show replant cost impact
        surface = interior_surface()
        print()
        print("=== Replant Costs (charge_replant_in_npv=True) ===")
        for sp in SpeciesClass:
            cost = surface.replant_cost_per_ha(sp)
            print(f"  {sp.value}: ${cost:,.0f}/ha")

        # Demonstrate target_species_from_acode
        print()
        print("=== Action Code → Target Species ===")
        for acode in action_codes:
            target = target_species_from_acode(acode)
            label = target.value if target else "(base action)"
            print(f"  {acode:20s} → {label}")


if __name__ == "__main__":
    main()
