# Real-Curve Replant Validation (P6.7, issue #49)

Date: 2026-08-27. Branch: `feature/species-switching-replant`.
Instance: `femic-tsa29mini-instance` branch `feature/replant-tipsy-curves`
(commit `42bc969`), bundle `data/model_input_bundle` (21 AUs; managed land
base 35,083.0 ha anchor reproduced).

## What was validated

1. **BTC replant curve store resolution.** `load_replant_curves_from_btc`
   reads `tipsy_curves_tsa29mini_replant.csv` + `tipsy_replant_manifest-
   tsa29mini.csv` (63 pure-plantation curves: 21 AUs × PL/SW/FD).
   `build_multi_species_yields(au_table, replant_curves=store)` resolved
   63/63 (AU × target-species) curves from real TIPSY data with **zero**
   synthetic-fallback warnings; the synthetic path remains as the explicit
   fallback (emits a `UserWarning` naming uncovered combinations).

2. **Real curves reach the replant DTKs.** The Woodstock `.yld` section
   carries the replant-AU curves; `_precreate_replant_dtypes` now prefers
   the ws3 `model.yields` stash (matching the replant AU mask) over copying
   source-DTK curves (ws3 lowercases mask entries on import — comparison is
   case-insensitive). Spot checks (3 AUs × 3 species): replant DTK
   `totvol` tracks the BTC curve within ws3's curve-simplification
   tolerance (max deviation ≤ 1.1 m3/ha on ~300 m3/ha curves) and differs
   materially from the source-copy placeholder for cross-species replants.

3. **End-to-end policy run on the real instance.** h=10 (10-yr periods),
   2 fixed-seed MC fire scenarios (seed 42, Moderate severity), policy
   `p67-sx40`: `replant_actions=("harvest_SX", "harvest_FD")`,
   composition target SX replant share 0.40 ± 0.10 with 3 free + 5 ramp
   periods (binding from period 9). Both scenarios solved **optimal**
   (NPV ≈ 1.84e7 CAD each; pipeline wall 71 s for 2 scenarios).

   Constraint-view SX replant share of all harvested area (base `harvest`
   replants to the source species):

   | period | 1 | 2 | 3-5 | 6 | 7 | 8 | 9 | 10 |
   |---|---|---|---|---|---|---|---|---|
   | share (scen 0) | 0.30 | 0.64 | 0.00 | 0.19 | 0.31 | 0.50 | 0.50 | 0.47 |

   Binding periods 9–10 within the 0.30–0.50 band in both scenarios
   (LP rides the upper tolerance edge — SX curves are economically
   attractive). Free periods show the expected economic pull toward SX
   (high-yield SW curves), the ramp recompresses toward the target.

## Caveats / recorded semantics

- `ScenarioRunPeriod.replant_area_by_species` counts only species-*switching*
  actions (`harvest_*`, `salvage_*`); base `harvest` (same-species replant)
  is not included, so the report metric can show "0 ha replanted" in periods
  where harvesting (and same-species replanting) occurred. The composition
  *constraint* counts base harvest correctly (source-species attribution via
  `_resolve_species`). Report/constraint consistency is a candidate follow-up.
- Bundle species-proportion sidecars (femic `managed_species_curve_ids`)
  remain unpopulated — that path serves per-species attribution of existing
  stands, not replant curves; the BTC replant store supersedes it for the
  replant feature (issue body updated to record the supersede).
- OT (other) has no TIPSY representation; OT replant uses the synthetic
  fallback with a diagnostic.
- ws3 simplifies curves on registration (`CURVE_EPSILON_DEFAULT = 0.01`):
  pointwise equality with the BTC table is not expected; tolerance-based
  checks are used.

## Reproduce

```bash
PYTHONPATH=src <instance-venv>/python tmp/p67_e2e_validation.py \
  --horizon 10 --n-scenarios 2 \
  --model-path tmp/p67_model_h10 --out tmp/p67_h10.json
```

(instance venv provides femic + geopandas; `pydantic` and `pulp` were
added to it for this run.)
