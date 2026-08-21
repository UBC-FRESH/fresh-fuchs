"""Species-switching replant LP example.

Demonstrates a fire-aware even-flow NPV-maximizing LP where the solver
can choose to replant harvested stands with a different species.  Uses
the synthetic instance (no annex bundle required).

Two scenarios are run:

1. **Unconstrained**: the solver freely chooses replant species (picks
   100% Douglas-fir, the higher-yielding species).
2. **Composition-constrained**: a policy forces ~60% spruce replanting.
   The replant mix shifts but NPV is unchanged — with no fire events
   and a 30-year horizon, replant species doesn't affect harvest
   revenue (both replant to age-0 stands not harvested in-horizon).
   The real cost appears with fire (species differ in burn susceptibility)
   or longer horizons (replant species affects future yield trajectory).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fresh_fuchs.economy.types import interior_surface
from fresh_fuchs.instance import InstanceConfig, SpeciesClass, bootstrap_model, prepare_optimization
from fresh_fuchs.instance.replant import add_replant_actions, target_species_from_acode
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.outer import CompositionTarget, PolicyRecord
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

REPLANT_ACTIONS = ("harvest_SX", "harvest_FD")


def _species_map() -> dict:
    return {
        ("29", "managed", "1", "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "1", "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        ("29", "managed", "2", "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        ("29", "unmanaged", "2", "natural", "baseline"): SpeciesClass.OTHER,
    }


def _build_model(config):
    model = prepare_optimization(
        bootstrap_model(config), max_initial_age=300, config=config
    )
    model = add_replant_actions(
        model, target_species=(SpeciesClass.SPRUCE, SpeciesClass.DOUGLAS_FIR)
    )
    model = add_salvage_action(model, max_age=300)
    return model


def _scenario():
    return DisturbanceScenario(
        name="example-scenario",
        seed=42,
        probability=1.0,
        burn_rate_multiplier=1.0,
        price_factor=1.0,
        severity="Moderate",
        events=tuple(
            FireEvent(period=t, zone=zone, annual_burn_rate=0.0, severity="Moderate")
            for zone in ZONE_BY_AU.values()
            for t in range(1, 4)
        ),
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config = InstanceConfig(
            model_name="replant-example",
            model_path=Path(tmp),
            horizon=3,
            period_length=10,
            max_age=300,
            min_harvest_age=60,
            max_harvest_age=300,
        )

        from fresh_fuchs.instance.synthetic import build_synthetic_areas, build_synthetic_yields

        write_woodstock_files(
            areas=build_synthetic_areas(), yields=build_synthetic_yields(), config=config
        )

        scenario = _scenario()

        # ------------------------------------------------------------------
        # Scenario 1: unconstrained replant (no composition policy)
        # ------------------------------------------------------------------
        model1 = _build_model(config)
        model1 = apply_salvage_operability(
            model1, scenario=scenario, zone_by_au=ZONE_BY_AU
        )

        action_codes = ("null", "harvest", "salvage") + REPLANT_ACTIONS
        cfg1 = FireLpConfig(zone_by_au=ZONE_BY_AU, action_codes=action_codes)
        problem1 = add_fire_problem(
            model1,
            cfg1,
            scenario=scenario,
            surface=interior_surface(),
            species_by_dtk=_species_map(),
        )
        results1 = solve_fire_lp(
            model1, problem1, scenario=scenario, config=cfg1, replant_action_codes=REPLANT_ACTIONS
        )

        print("=== Scenario 1: Unconstrained Replant ===")
        print(f"LP status: {problem1.status()}")
        print(f"Objective (NPV): ${float(problem1.z()):,.0f}")
        print(results1.to_string(index=False))
        print()

        _print_replant_mix(model1, problem1, "Unconstrained")

        # ------------------------------------------------------------------
        # Scenario 2: composition-constrained replant (60% spruce target)
        # ------------------------------------------------------------------
        model2 = _build_model(config)
        model2 = apply_salvage_operability(model2, scenario=scenario, zone_by_au=ZONE_BY_AU)

        from fresh_fuchs.economy.types import Provenance

        P = Provenance(source="example", as_of="T0", units="multiplier", basis="composition demo")
        policy = PolicyRecord(
            name="comp_60_spruce",
            provenance=P,
            composition_targets=(
                CompositionTarget(
                    species=SpeciesClass.SPRUCE,
                    target_share=0.60,
                    tolerance=0.05,
                    provenance=P,
                ),
            ),
            replant_actions=REPLANT_ACTIONS,
        )

        cfg2 = FireLpConfig(
            zone_by_au=ZONE_BY_AU, action_codes=action_codes
        )
        problem2 = add_fire_problem(
            model2,
            cfg2,
            scenario=scenario,
            surface=interior_surface(),
            species_by_dtk=_species_map(),
            policy=policy,
        )
        results2 = solve_fire_lp(
            model2, problem2, scenario=scenario, config=cfg2, replant_action_codes=REPLANT_ACTIONS
        )

        print("=== Scenario 2: Composition-Constrained Replant (60% Spruce) ===")
        print(f"LP status: {problem2.status()}")
        print(f"Objective (NPV): ${float(problem2.z()):,.0f}")
        print(results2.to_string(index=False))
        print()

        _print_replant_mix(model2, problem2, "Composition-constrained")

        # ------------------------------------------------------------------
        # Summary
        # ------------------------------------------------------------------
        print("=== Comparison ===")
        print(f"  Unconstrained NPV:        ${float(problem1.z()):>12,.0f}")
        print(f"  Composition-constrained:  ${float(problem2.z()):>12,.0f}")
        print(f"  Constraint cost:          ${float(problem1.z()) - float(problem2.z()):>12,.0f}")
        print()

        # Show target_species_from_acode mapping
        print("=== Action Code → Target Species ===")
        for acode in ("null", "harvest", "salvage") + REPLANT_ACTIONS:
            target = target_species_from_acode(acode)
            label = target.value if target else "(base action)"
            print(f"  {acode:20s} → {label}")


def _print_replant_mix(model, problem, label: str) -> None:
    """Print the replanted-area breakdown by target species."""
    schedule = model.compile_schedule(problem)
    mix: dict[str, float] = {}
    for dtk, _age, area, acode, _period, _etype in schedule:
        if not acode.startswith("harvest"):
            continue
        sp = target_species_from_acode(acode)
        if sp is None:
            sp = SpeciesClass.OTHER
        mix[sp.value] = mix.get(sp.value, 0.0) + area
    total = sum(mix.values())
    print(f"  {label} replant mix:")
    for sp_val, ha in sorted(mix.items()):
        share = ha / total if total > 0 else 0.0
        print(f"    {sp_val:6s}: {ha:>7.1f} ha  ({share:.1%})")
    print()


if __name__ == "__main__":
    main()
