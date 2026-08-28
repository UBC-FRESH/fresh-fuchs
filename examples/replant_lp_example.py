"""Species-switching replant LP example.

Demonstrates a fire-aware even-flow NPV-maximizing LP where the solver
can choose to replant harvested stands with a different species.  Uses
the synthetic instance (no annex bundle required).

Runs N Monte-Carlo fire scenarios under two policies:

1. **Unconstrained**: the solver freely chooses replant species.
2. **Composition-constrained**: a policy forces ~60% spruce replanting.

Key parameters (edit at the top of main()):

- ``n_scenarios``: number of MC fire realizations
- ``zone_burn_rates``: deterministic base annual burn rate per BEC zone
  (e.g. 0.01 = 1% of exposed live volume burned per year before
  multiplier).  Each scenario multiplies this by a random draw from
  the uncertainty vector (uniform 0.5–1.5 by default).
- ``probability``: scenario weight, always ``1/n_scenarios``.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fresh_fuchs.economy.types import Provenance, interior_surface
from fresh_fuchs.instance import InstanceConfig, SpeciesClass, bootstrap_model, prepare_optimization
from fresh_fuchs.instance.replant import add_replant_actions, target_species_from_acode
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.outer import CompositionTarget, PolicyRecord
from fresh_fuchs.scenario import generate_scenarios
from fresh_fuchs.scenario.distributions import (
    DistributionFamily,
    ParameterDistribution,
    UncertaintyDimension,
    UncertaintyVector,
)
from fresh_fuchs.scenario.fire_lp import FireLpConfig, add_salvage_action
from fresh_fuchs.scenario.records import ScenarioGenerationParams

AU1, AU2 = 1, 2
ZONE_BY_AU = {AU1: "SBPS", AU2: "IDF"}

REPLANT_ACTIONS = ("harvest_SX", "harvest_FD")

# ---------- edit these ----------
N_SCENARIOS = 10
ZONE_BURN_RATES = {z: 0.01 for z in ZONE_BY_AU.values()}  # 1%/yr base burn rate
MASTER_SEED = 42
HORIZON = 10  # periods (10 yr each = 100 yrs)
PERIOD_LENGTH = 10
# -------------------------------


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


def _generate_scenarios(n_scenarios, master_seed, horizon, period_length, zone_burn_rates):
    P = Provenance(source="example", as_of="T0", units="multiplier", basis="replant demo")
    vector = UncertaintyVector(
        distributions={
            UncertaintyDimension.FIRE_BURN_RATE: ParameterDistribution(
                name="burn_rate_multiplier",
                family=DistributionFamily.GAUSSIAN,
                provenance=P,
                mean=1.0,
                std=0.3,
            ),
            UncertaintyDimension.PRICE: ParameterDistribution(
                name="price_factor",
                family=DistributionFamily.FIXED,
                provenance=P,
                value=1.0,
            ),
        }
    )
    params = ScenarioGenerationParams(
        n_scenarios=n_scenarios,
        master_seed=master_seed,
        horizon=horizon,
        period_length=period_length,
        zone_burn_rates=zone_burn_rates,
        vector=vector,
        severity="Moderate",
        provenance=P,
    )
    return generate_scenarios(params)


def _run_one_policy(config, scenarios, policy, label):
    """Run all scenarios under one policy, return list of ScenarioRunRecord."""
    surface = interior_surface()
    action_codes = ("null", "harvest", "salvage") + REPLANT_ACTIONS
    results = []
    for sc in scenarios:
        model = _build_model(config)
        from fresh_fuchs.scenario.fire_lp import apply_salvage_operability
        model = apply_salvage_operability(model, scenario=sc, zone_by_au=ZONE_BY_AU)

        fire_config = FireLpConfig(
            zone_by_au=ZONE_BY_AU, action_codes=action_codes
        )
        from fresh_fuchs.scenario.fire_lp import add_fire_problem
        problem = add_fire_problem(
            model, fire_config, scenario=sc,
            surface=surface, species_by_dtk=_species_map(),
            policy=policy if policy and policy.composition_targets else None,
        )
        from fresh_fuchs.scenario.fire_lp import solve_fire_lp
        solve_fire_lp(
            model, problem, scenario=sc, config=fire_config,
            replant_action_codes=REPLANT_ACTIONS,
            species_by_dtk=_species_map(),
        )
        results.append({
            "name": sc.name,
            "npv": float(problem.z()),
            "burn_multiplier": sc.burn_rate_multiplier,
        })
    return results


def main() -> None:
    print(f"Running {N_SCENARIOS} fire scenarios, horizon={HORIZON} periods "
          f"x {PERIOD_LENGTH} yrs, base burn rate={ZONE_BURN_RATES}\n")

    with tempfile.TemporaryDirectory() as tmp:
        config = InstanceConfig(
            model_name="replant-example",
            model_path=Path(tmp),
            horizon=HORIZON,
            period_length=PERIOD_LENGTH,
            max_age=300,
            min_harvest_age=60,
            max_harvest_age=300,
        )

        from fresh_fuchs.instance.synthetic import build_synthetic_areas, build_synthetic_yields
        write_woodstock_files(
            areas=build_synthetic_areas(), yields=build_synthetic_yields(), config=config
        )

        scenarios = _generate_scenarios(
            N_SCENARIOS, MASTER_SEED, HORIZON, PERIOD_LENGTH, ZONE_BURN_RATES
        )

        # Show scenario catalogue
        print("=== Scenario Catalogue ===")
        print(f"{'Scenario':<20} {'Burn mult':>10} {'Burn rate SBPS':>15} {'Burn rate IDF':>15}")
        for sc in scenarios:
            sbps_rate = ZONE_BURN_RATES["SBPS"] * sc.burn_rate_multiplier
            idf_rate = ZONE_BURN_RATES["IDF"] * sc.burn_rate_multiplier
            print(
                f"{sc.name:<20} {sc.burn_rate_multiplier:>10.2f}"
                f" {sbps_rate:>14.3%} {idf_rate:>14.3%}"
            )
        print()

        # ------------------------------------------------------------------
        # Policy 1: unconstrained replant
        # ------------------------------------------------------------------
        P = Provenance(source="example", as_of="T0", units="share", basis="replant demo")
        policy_unconstrained = PolicyRecord(
            name="unconstrained", provenance=P,
            composition_targets=(), replant_actions=REPLANT_ACTIONS,
        )
        results1 = _run_one_policy(config, scenarios, policy_unconstrained, "Unconstrained")

        print("=== Policy 1: Unconstrained Replant ===")
        print(f"{'Scenario':<20} {'NPV ($)':>15} {'Burn mult':>10}")
        for r in results1:
            print(f"{r['name']:<20} {r['npv']:>15,.0f} {r['burn_multiplier']:>10.2f}")
        npvs1 = [r["npv"] for r in results1]
        print(f"{'Mean':<20} {sum(npvs1)/len(npvs1):>15,.0f}")
        print(f"{'Min':<20} {min(npvs1):>15,.0f}")
        print(f"{'Max':<20} {max(npvs1):>15,.0f}")
        print()

        # ------------------------------------------------------------------
        # Policy 2: composition-constrained (60% spruce target)
        # ------------------------------------------------------------------
        policy_constrained = PolicyRecord(
            name="comp_60_spruce", provenance=P,
            composition_targets=(
                CompositionTarget(
                    species=SpeciesClass.SPRUCE, target_share=0.60,
                    tolerance=0.05, provenance=P,
                ),
            ),
            replant_actions=REPLANT_ACTIONS,
        )
        results2 = _run_one_policy(config, scenarios, policy_constrained, "Constrained")

        print("=== Policy 2: Composition-Constrained (60% SX) ===")
        print(f"{'Scenario':<20} {'NPV ($)':>15} {'Burn mult':>10}")
        for r in results2:
            print(f"{r['name']:<20} {r['npv']:>15,.0f} {r['burn_multiplier']:>10.2f}")
        npvs2 = [r["npv"] for r in results2]
        print(f"{'Mean':<20} {sum(npvs2)/len(npvs2):>15,.0f}")
        print(f"{'Min':<20} {min(npvs2):>15,.0f}")
        print(f"{'Max':<20} {max(npvs2):>15,.0f}")
        print()

        # ------------------------------------------------------------------
        # Comparison
        # ------------------------------------------------------------------
        mean1 = sum(npvs1) / len(npvs1)
        mean2 = sum(npvs2) / len(npvs2)
        print("=== Comparison ===")
        print(f"  Unconstrained mean NPV:      ${mean1:>12,.0f}")
        print(f"  Constrained mean NPV:        ${mean2:>12,.0f}")
        print(f"  Constraint cost (mean):      ${mean1 - mean2:>12,.0f}")
        print()

        # Show action code mapping
        print("=== Action Code -> Target Species ===")
        for acode in ("null", "harvest", "salvage") + REPLANT_ACTIONS:
            target = target_species_from_acode(acode)
            label = target.value if target else "(base action)"
            print(f"  {acode:20s} -> {label}")


if __name__ == "__main__":
    main()
