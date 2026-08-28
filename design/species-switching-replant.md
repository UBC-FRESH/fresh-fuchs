# Species-Switching Replant Transitions

Status: **Implemented** — roadmap phase P6, parent issue
[#42](https://github.com/UBC-FRESH/fresh-fuchs/issues/42), branch
`feature/species-switching-replant`. All design phases complete:
1–4b (P6.1–P6.4, #43–#46, tracked retroactively), salvage integration
(P6.5, #47), TIPSY (BTC) curve generation (P6.6, #48), real-curve
integration + real-instance validation (P6.7, #49), CLI + examples
(P6.8, #50), acceptance (P6.9, #51).

## Motivation

Currently the harvest transition resets a stand to age 0 of the **same
development type** (same species, same yield curve). The LP can choose
*when* to harvest, but not *what to replant*. Composition constraints
work by skewing which species are harvested, not by changing what grows
back.

The goal is to allow harvesting any species and replanting any other
available species, driven by a target landscape composition. The
species choice at replanting should be a free LP decision, subject to
policy-level composition targets.

## Design: Option C — Separate Harvest Actions + Policy-Driven Operability

### Core Idea

Register **separate harvest actions** per replant species at model
bootstrap. A policy specifies which replant actions are active and
their target area shares. Only the active subset enters the LP.

```
Policy A: "same species only" (backward-compatible default)
  actions: [harvest]
  → transitions to same AU, age 0 (no species change)

Policy B: "50% pine, 30% spruce, 20% dougfir"
  actions: [harvest_pl, harvest_sx, harvest_fd]
  composition targets: {harvest_pl: 0.50, harvest_sx: 0.30, harvest_fd: 0.20}
```

### How ws3 Transitions Work

A transition is a 7-tuple:
```
(target_mask, probability, yield_expr, age, treplace, tappend, tcondition)
```

The `target_mask` specifies the new development type key — it **can**
change any theme value. When a stand is harvested, ws3 looks up the
transition, creates or finds the target development type, and moves the
area there at age 0.

Key point: the `transitions` dict on each `DevelopmentType` is keyed
by `(acode, age)`. Each key maps to a single transition list. Multiple
targets in the same list create a **probabilistic branch**, not an LP
decision. To get separate LP decision variables per replant species, we
need **separate actions**.

### Actions and Transitions

At bootstrap, register N+1 harvest actions (N = number of replant
species):

| Action Code | Transition Target | Species Planted |
|-------------|-------------------|-----------------|
| `harvest` | same AU, age 0 | Same (default) |
| `harvest_pl` | AU with PL yield curve, age 0 | Lodgepole pine |
| `harvest_sx` | AU with SX yield curve, age 0 | Spruce |
| `harvest_fd` | AU with FD yield curve, age 0 | Douglas-fir |
| `harvest_ot` | AU with OT yield curve, age 0 | Other |

Each replant action needs:
1. A target AU with the correct species yield curve
2. Operability matching the base harvest action (min_harvest_age .. max_harvest_age)
3. A transition tuple targeting age 0 of the target AU

The transition registration follows the pattern in `add_salvage_action`
(`fire_lp.py:240-268`), which already registers a new action with a
custom transition programmatically.

### Yield Curve Requirement

Each replant action needs a yield curve for the target species at each
site. Currently each AU has one species and one yield curve. To replant
AU 1001 (PL site) as FD, we need an FD yield curve for that site.

**Status (flagged):** The tsa29mini bundle does NOT currently populate
species proportion curves. All 108 curves are ``treated``/``untreated``
(single-species per AU). The ``si_level`` column exists in the AU table
but is not yet used for cross-species transfer. See
`design/yield-curve-framework.md` for the full analysis.

Options for obtaining multi-species yield curves:
- **Bundle species proportion curves**: The femic framework has
  ``managed_species_curve_ids`` / ``unmanaged_species_curve_ids`` in
  ``BundleModelContext`` — the infrastructure exists but the bundle
  doesn't populate it yet.
- **Site-index transfer**: Use the AU's ``si_level`` (L/M/H) as a
  grouping variable. Within each group, apply species-specific growth
  functions scaled by a site-index conversion factor.
- **Generic curves**: species-class-average curves per site class
- **Synthetic fallback**: Use species-specific Chapman-Richards growth
  curves with parameter defaults by species class (current default path)

The framework can be built without real data — the transition registration
and LP wiring work regardless of which yield curves are available.
See ``src/fresh_fuchs/instance/yields_multi.py`` for the implementation.

### Economics

**Timber revenue** (NPV objective): based on the **source species**
(the old stand being harvested). The `species_by_dtk` lookup in
`compile_path_z` uses the source development type's species, which
determines the stumpage price.

**Planting cost**: based on the **target species** (what is planted).
This is a new cost line item per replant action. It enters the
objective as a negative coefficient on the replant action's path.

Currently `harvest_cash_flow` in `economy/cashflow.py` computes:
```
revenue = volume * price(species) - planting_cost
```

With species switching, this splits into:
- Revenue: `volume * price(source_species)` (unchanged)
- Planting cost: `replant_cost(target_species)` (new, per replant action)

The replant cost is species-dependent (e.g., PL seedlings are cheaper
than FD seedlings).

### Salvage Interaction

Salvage currently transitions to age 0 of the same AU. With species
switching, salvage should also allow replanting with a different
species. This means registering replant-specific salvage actions:

| Action Code | Transition Target | Species Planted |
|-------------|-------------------|-----------------|
| `salvage` | same AU, age 0 | Same (default) |
| `salvage_pl` | AU with PL yield curve, age 0 | Lodgepole pine |
| `salvage_sx` | AU with SX yield curve, age 0 | Spruce |
| `salvage_fd` | AU with FD yield curve, age 0 | Douglas-fir |
| `salvage_ot` | AU with OT yield curve, age 0 | Other |

The fire LP path stepping in `path_fire_steps` already handles
multiple action codes. The salvage replant actions need their own
coefficient functions for the NPV objective (burned price discount +
replant cost for target species).

### Composition Constraints

With separate harvest actions, composition constraints bind on
**action area** rather than species area:

```python
# Old: constrain area harvested of species X
# New: constrain area harvested by action harvest_X
```

The coefficient function simplifies — no `species_by_dtk` lookup needed,
just check `d["acode"] == target_action`. Each replant action maps to
one target species, so constraining `harvest_pl` area share is
equivalent to constraining pine replant area share.

### Backward Compatibility

Default policy: `replant_actions = ("harvest",)`. This uses the
original single harvest action with same-species transition. The model
behaves identically to the current implementation.

When a policy specifies `replant_actions = ("harvest_pl", "harvest_fd")`,
the LP gets separate decision variables for each replant species and
the composition constraints bind on those actions.

---

## Implementation Phases

### Phase 1: Yield Curve Framework (data, no LP changes)

**Goal**: Build the data infrastructure for multi-species yield curves
per site, without changing the LP or transition registration.

**Status**: Implemented (synthetic fallback path).

**Tasks**:
1. Define a `ReplantSpecies` enum or config that maps replant action
   codes to species classes ✅ (uses existing `SpeciesClass`)
2. Create a `build_multi_species_yields()` function that takes the
   existing femic bundle context and produces yield curves for all
   target species at each site (site-index transfer or generic curves)
   ✅ Implemented in `instance/yields_multi.py`
3. Store multi-species yields in a structured format (dict keyed by
   `(au_id, target_species)` → yield curve) ✅ `MultiSpeciesYieldTable`
4. Write tests using synthetic fixtures (no real bundle data)
   ✅ `tests/test_yields_multi.py` (21 tests)

**Verification**:
- Unit tests for yield curve lookup ✅
- Synthetic AU with known SI produces reasonable FD curve from PL SI ✅
- All existing tests still pass ✅ (169 passed, 1 skipped)

**Files**:
- New: `src/fresh_fuchs/instance/yields_multi.py` ✅
- New: `tests/test_yields_multi.py` ✅

### Phase 2: Replant Action Registration (ws3 model changes)

**Goal**: Register harvest and salvage replant actions with correct
transitions at model bootstrap.

**Status**: Implemented.

**Tasks**:
1. Create `add_replant_actions()` function ✅
2. For each replant species, register:
   - An action with `is_harvest=True` ✅
   - A transition targeting the appropriate AU's development type at age 0 ✅
   - Operability matching the base harvest action ✅
3. Create `add_replant_salvage_actions()` for salvage → replant ✅
4. Wire into `prepare_optimization()` with `replant_species` parameter ✅
5. Tests verifying:
   - Actions are registered and operable ✅
   - Transitions target the correct development types ✅
   - Backward-compatible default (no replant actions) still works ✅

**Implementation note**: ws3's `_REPLACE` mechanism does not support
string concatenation (the `resolve_replace` hack does a naive
`eval(expr.replace('_TH3', dtk[i]))` which fails when `dtk[i]`
is a numeric string). Instead, per-AU source masks are registered:
each source AU gets its own `(?, ?, au_id, ?, ?)` → `(?, ?, au_id-SX, ?, ?)`
transition. This is O(n_aus × n_species) transitions but keeps
the approach simple and reliable.

**DTK pre-creation** (`_precreate_replant_dtypes`): ws3's `_bld_tree_m1`
follows transitions to target DTKs during tree construction. If the
target DTK does not exist in `model.dtypes`, it calls
`create_dtype_fromkey` which uses `match_mask` → `_expand_theme` to
resolve theme values. Replant AU codes like `1-SX` are not in the
theme hierarchy (themes have integer AU IDs), so mask matching fails
silently and the DTK is never created. The result is a `TypeError`
('NoneType' object is not subscriptable) at `_bld_tree_m1:1164` when
stands reach harvest age.

This only manifests with `horizon >= 7` periods (stand age 60 at
period 7 for 10-yr periods). Shorter horizons mask the bug because
no stands reach harvest age before the planning horizon ends.

Fix: `add_replant_actions` now calls `_precreate_replant_dtypes`
after registering actions but before tree building. For each replant
target (e.g. AU 1 + SPRUCE → DTK `1-SX`):
1. Creates a `DevelopmentType` with the replant DTK key
2. Copies yield curves from the source DTK
3. Wires per-action operability (null: age 0–400, harvest: 60–300,
   salvage: 0–400, replant actions: correct age bounds)
4. Sets `(acode, -1)` transitions for all actions

**`replant_au_id` suffix stripping**: `replant_au_id(au, species)`
strips any existing replant suffix before appending the new species
suffix. `replant_au_id('1-FD', SPRUCE)` → `'1-SX'` (not `'1-FD-SX'`).
This prevents double-suffix DTKs when an AU already has a replant
suffix from a prior call.

**`apply_salvage_operability` fix**: parses `int(dtk[2])` to look up
the base AU for zone-based operability. Replant DTKs like `'1-SX'`
fail `int()`. Fix: strip replant suffix (split on `-`) before
conversion. This is in `scenario/fire_lp.py:~298`.

**Verification**:
- Model with replant actions compiles successfully ✅
- `operable_area()` returns correct values for replant actions ✅
- `apply_action()` with replant action transitions to correct target dtk ✅
- Existing tests still pass without replant actions ✅ (192 passed, 1 skipped)
- Deep-horizon tree build (horizon=10) with pre-created DTKs ✅

**Files**:
- New: `src/fresh_fuchs/instance/replant.py` ✅
- Modified: `src/fresh_fuchs/instance/woodstock.py` ✅
- New: `tests/test_replant_actions.py` ✅

### Phase 3: LP Wiring (objective + even-flow) ✅

**Goal**: Wire replant actions into the inner LP so the solver can
choose replant species.

**Tasks**:
1. Extend `FireLpConfig.action_codes` to accept replant action codes ✅
2. Extend `compile_path_z` (NPV objective) to:
   - Use source species for timber revenue (unchanged) ✅
   - Subtract replant cost for target species on replant actions ✅
3. Extend `compile_path_caa` (even-flow) to aggregate volume across
   all replant actions (not just `harvest`) ✅
4. Extend `path_fire_steps` to handle replant action codes (they behave
   like `harvest` for fire dynamics — the stand regenerates) ✅
5. Tests:
   - Synthetic model with 2 replant species solves correctly ✅
   - Objective includes replant costs ✅
   - Even-flow constraint aggregates all replant actions ✅

**Verification**:
- LP solves with replant actions ✅
- Objective value includes replant cost deduction ✅
- Even-flow constraint works across all replant actions ✅
- Backward-compatible: LP with default action_codes unchanged ✅

**Implementation notes**:
- `_burn_prob_for_dtk` strips replant AU suffixes (e.g. `"1-SX"` → `1`)
  for zone lookup.
- `path_fire_steps` handles missing yield curves on replant AUs (zero
  volume at age 0).
- `solve_fire_lp` accepts `replant_action_codes` to sum replant volumes
  into harvest totals.
- `target_species_from_acode()` helper parses replant action codes.

**Files**:
- Modified: `src/fresh_fuchs/scenario/fire_lp.py`
- Modified: `src/fresh_fuchs/instance/replant.py` (added `target_species_from_acode`)
- New: `tests/test_replant_lp.py` (15 tests)
- New: `examples/replant_lp_example.py`
- Note: `cashflow.py` was not modified — replant cost is handled directly in
  `_compile_path_z` via `surface.replant_cost_per_ha(target_sp)`.

### Phase 4: Replant Composition Constraints

**Status**: complete.

**Goal**: Composition constraints bind on replant action area (target
species), controlling the landscape trajectory rather than harvest access.

#### Rationale

**Why replant composition, not harvest composition.**
Current composition constraints bind on harvested area by source species
(`policy.py:58-60`): they control which species' stands get *cut*. With
species-switching, the novel lever is what gets *replanted*. Replant
composition shapes landscape trajectory: a policy demanding 40% spruce
replanting forces the solver to harvest non-spruce stands and replant
them as spruce, gradually converting the forest. This is the long-term
management target. Harvest composition is a short-term timber-access
lever that already works.

**Why three-phase transition (free → ramp → binding).**
A hard composition constraint from period 1 can be infeasible. Example:
the current forest is 60% pine, the target is 30% pine replanting, but
only 10% of harvestable area is available in period 1 — the even-flow
band prevents enough harvesting to meet the 30% pine replant share. The
three-phase structure avoids this:

1. **Free periods** (1 to `n_free_periods`): no composition constraint.
   The solver harvests freely, building toward the target composition.
2. **Ramp periods** (`n_free+1` to `n_free+n_ramp`): tolerance
   linearly decays from 1.0 (effectively unconstrained) to `tolerance`
   (the final band). The solver gradually shifts replant species.
3. **Binding periods** (after ramp): full constraint at `tolerance`.
   The landscape is near the target; the constraint maintains it.

Default values (`n_free_periods=0, n_ramp_periods=0`) reproduce the
current behavior: constraint from period 1 at fixed tolerance.

**What drives species selection.**
Without the composition constraint, the LP is indifferent to replant
species when replant costs are equal — the objective sees
source-species timber revenue, not target-species revenue. The
constraint is the primary driver of species choice. With longer
horizons, yield curve differences (growth rate × price) create a
secondary economic incentive: the solver can see the future volume
trajectory of the target species and prefers faster-growing,
higher-priced species. The three-phase structure lets the solver
exploit this secondary incentive during free periods while still
converging to the policy target.

#### Schema changes

**`CompositionTarget`** (`outer/records.py`) — add two fields:

```python
n_free_periods: int = Field(default=0, ge=0,
    description="Periods with no composition constraint.")
n_ramp_periods: int = Field(default=0, ge=0,
    description="Periods where tolerance decays from 1.0 to self.tolerance.")
```

Backward compatible: defaults produce current behavior.

**`PolicyRecord`** — add:

```python
replant_actions: tuple[str, ...] | None = Field(
    default=None,
    description="Replant action codes for composition attribution. "
    "When set, composition binds on replant action area (target species). "
    "When None, binds on source species (current behavior).",
)
```

**`CompositionGridAxis`** and **`PolicyGrid`** — pass through
`n_free_periods` and `n_ramp_periods`. Grid dict entries can include
these keys (like the existing `"tolerance"` key).

#### Policy coefficient changes (`outer/policy.py`)

**`_harvest_steps`** — extend to accept `replant_actions` parameter.
When set, match `acode.startswith("harvest")` instead of
`acode == "harvest"`, and yield the acode alongside (period, dtk, age).

**`_resolve_species`** — new helper: if `replant_actions` is set, use
`target_species_from_acode(acode)` (falling back to `species_by_dtk`
for base `"harvest"`); otherwise use `species_by_dtk` directly.

**`_composition_coeff`** — becomes period-aware. Returns raw `area_G`
(area of target species replanted) modulated by a per-period `share`:

```python
def _composition_coeff(..., share_by_period):
    for t, dtk, _age, acode in _harvest_steps(...):
        sp = _resolve_species(acode, dtk, ...)
        share = share_by_period[t]  # target_share ± tolerance_t
        result[t] = cohort_area * ((1 if sp is target else 0) - share)
```

Bounds stay at 0 (same as current). The time-varying share is embedded
in the coefficient.

**`policy_coeff_funcs`** — generates two functions per target:
- `comp_lo_{i}`: uses `share = target_share - tolerance_t`
- `comp_hi_{i}`: uses `share = target_share + tolerance_t`

Where `tolerance_t` varies by period (1.0 during free, decaying during
ramp, final during binding). Passes `replant_actions` from the policy.

**`_share_by_period`** — new helper that computes the per-period share
lookup from the three-phase schedule:

```
for each period:
  if period <= n_free:       tolerance_t = 1.0  (unconstrained)
  elif in ramp:              tolerance_t = 1.0 - ramp_frac * (1.0 - tolerance)
  else:                      tolerance_t = tolerance
```

#### Three-phase bounds (`policy_cgen_data`)

For free periods, the coefficient uses `share = target_share ± 1.0`,
which makes the row structurally satisfied (the bound is always met).
The row still exists but doesn't constrain the LP. This is equivalent
to omitting the row but avoids period-conditional row creation.

#### Wiring

`policy_coeff_funcs` signature changes to accept `replant_actions` from
the `PolicyRecord`. `add_fire_problem` already passes the policy
through — no changes needed there.

#### Files

| File | Change |
|------|--------|
| `outer/records.py` | `CompositionTarget.n_free_periods`, `n_ramp_periods`; `PolicyRecord.replant_actions` |
| `outer/policy.py` | `_harvest_steps` extended; `_resolve_species` helper; `_composition_coeff` period-aware; `policy_coeff_funcs` passes `replant_actions`; `policy_cgen_data` three-phase bounds; `_share_by_period` helper |
| `outer/grid.py` | `CompositionGridAxis` gets `n_free_periods`, `n_ramp_periods`; `PolicyGrid.composition_points` passes them through |
| `design/species-switching-replant.md` | Phase 4 section rewritten with rationale |
| `tests/test_replant_composition.py` | New: replant composition, three-phase, backward compat |

#### Tests

1. Replant composition constraint on `harvest_SX` area share binds
2. Three-phase: free periods produce unconstrained LP
3. Three-phase: ramp periods narrow tolerance linearly
4. Backward compat: existing composition_constraints tests pass
   (no `replant_actions` → source species attribution)
5. `PolicyGrid` expansion with `n_free_periods` / `n_ramp_periods`

#### Verification

- LP with composition constraints on replant actions solves
- Replanted area shares match targets within tolerance
- Three-phase schedule prevents infeasibility on distant targets
- Backward-compatible: existing composition_constraints tests pass

#### What drives species selection (design note)

The composition constraint is the primary driver of replant species
choice. Without it, the LP is indifferent when replant costs are equal.
With longer horizons, yield curve differences (growth rate × price) and
replant cost differences create secondary incentives. The constraint
ensures the landscape transitions at the policy pace rather than
jumping to the economic optimum.

### Phase 4b: Species-Specific LP Outputs + Quarto Report

**Goal**: Expose per-species harvest/replant data from the LP and
produce a parameterized Quarto report for result visualization.

**Status**: Implemented.

**Design decisions**:

- **Composition = area**: The policy constraint binds on replant *area*
  share per target species. The report shows both area composition
  (what the policy controls) and volume composition (what economics
  see).
- **Bray-Curtis defaults**: Unspecified species default to 0% target
  share. This captures absolute drift (not just proportional drift
  among targeted species). If the policy targets 10% PL and 20% SX,
  but the landscape replants 85% FD, BC correctly reports high
  dissimilarity.
- **Report aggregation**: Per-period values are shown as mean across
  MC scenarios with min/max shaded bands. The default policy is the
  first in the grid when no policy is specified.
- **Env var config**: The `.qmd` reads `FUCHS_GRID_DIR` and
  `FUCHS_POLICY` from environment variables (quarto params don't
  inject reliably for Python kernels).

**Changes**:

- `ScenarioRunPeriod` gains 3 fields: `harvest_area_by_species`,
  `harvest_volume_by_species`, `replant_area_by_species` (all
  `dict[str, float]`).
- `run_scenario_lp` adds replant actions to the model when
  `policy.replant_actions` is set, passes replant action codes to
  `FireLpConfig.action_codes` and to `solve_fire_lp`.
- `solve_fire_lp` accepts `species_by_dtk`; extracts per-species data
  from schedule after solve+apply; attributes base `harvest` via
  `species_by_dtk`, replant `harvest_*` via `target_species_from_acode`.

**Files**:
- Modified: `src/fresh_fuchs/scenario/pipeline.py`
- Modified: `src/fresh_fuchs/scenario/fire_lp.py`
- New: `reports/_quarto.yml`
- New: `reports/replant_summary.qmd`
- New: `scripts/render_report.py`
- Modified: `pyproject.toml` (`reports = ["matplotlib"]`)

### Phase 5: Salvage Replant Integration (P6.5, issue #47)

**Status**: complete.

**Goal**: Salvage actions can replant with a different species.

**Tasks**:
1. Extend `path_fire_steps` to handle salvage replant actions
   (treat like salvage + species switch) ✅ — no code change needed:
   the `acode.startswith("salvage")` handling already covers
   `salvage_*` codes (pool salvage + survival reset); the species
   switch itself rides on the ws3 transition registered in Phase 2.
   Locked in with path-level tests.
2. Extend `compile_path_z` to apply burned-price discount +
   replant cost for salvage replant actions ✅ — the salvage branch
   already applies the burned-price margin to any `salvage_*` code;
   added the target-species replant cost deduction (per cohort area,
   same convention as the harvest branch) when
   `surface.charge_replant_in_npv` is set. Base `salvage` carries no
   replant cost (unchanged).
3. Wire salvage replant actions into `FireLpConfig` ✅ —
   `apply_salvage_operability` now prunes every registered `salvage*`
   action (autodetected from `model.actions`), so salvage replant
   branches close in fire-free periods like base salvage;
   `add_fire_problem` adds the `salvage_feas` row when any
   `salvage*` code is in `action_codes` (previously only on base
   `salvage`); `solve_fire_lp` attributes `salvage_*` schedule area
   to `replant_area_by_species` under the target species.
4. Tests ✅ — `tests/test_replant_salvage.py` (13 tests):
   registration standalone (no harvest replant needed), transition
   targets, path fire steps (pool, survival reset, DTK switch),
   path-level economics (burned margin identity, replant-cost delta
   = discounted target cost, base-salvage invariance), operability
   pruning, LP solves with subsidy (salvage used, feasibility holds,
   salvaged area == SX replant area), objective lower with replant
   cost charged, backward compatibility.

**Implementation notes**:

- `add_replant_salvage_actions` now also pre-creates replant DTKs
  (same `_precreate_replant_dtypes` pass as harvest replant), so
  salvage replant works standalone — previously a salvage replant
  transition to a non-existent replant DTK would hit the ws3
  `_bld_tree_m1` mask-matching failure documented in Phase 2.
- `_precreate_replant_dtypes` resolves a replant action's target
  species via `target_species_from_acode` instead of positional
  parallel-array indexing (robust to partial re-registration now that
  both harvest and salvage registration call it).
- **Composition-constraint boundary (recorded semantics)**: outer
  composition rows bind on `harvest*` steps only
  (`outer/policy.py::_harvest_steps`); salvage replant area is
  reported in `replant_area_by_species` but does not count toward
  composition targets. Salvage is disturbance-driven and, at the
  default negative salvage margin, rare; if subsidised-salvage
  policies become a study focus, revisit whether salvaged-and-
  replanted area should enter the composition shares.

**Verification**:
- Salvage replant LP solves ✅
- Correct economics (burned price + replant cost) ✅
- Salvage feasibility constraint still holds ✅
- Full suite green: 229 passed, 2 skipped (freshforge-env skips);
  ruff clean ✅

**Files**:
- Modified: `src/fresh_fuchs/scenario/fire_lp.py` ✅
- Modified: `src/fresh_fuchs/instance/replant.py` (salvage DTK
  pre-creation + robust species resolution)
- New: `tests/test_replant_salvage.py` ✅

### Phase 6: CLI + Example Configs (P6.8, issue #50)

**Goal**: End-to-end usability from CLI and example configs.

**Tasks**:
1. Add `--replant-species` flag to `policy-grid` CLI command
2. Create example JSON configs demonstrating:
   - Default (no species switch)
   - Two-species replant policy
   - Full four-species replant with composition targets
3. Update `policy_grid` run script to support replant policies
4. Document in `examples/` directory

**Verification**:
- `fuchs policy-grid --config examples/policy-grid.replant.json` runs
- Output CSV shows replant action area by species
- Results are interpretable (harvest area, replant area, NPV)

**Files**:
- Modified: `src/fresh_fuchs/cli.py`
- New: `examples/policy-grid.replant.json`
- Modified: `scripts/run_policy_grid.py`

---

## Open Questions (reconciled at P6.9 acceptance)

1. **Yield curve source — RESOLVED.** Real TIPSY (BTC) pure-plantation
   curves for every source AU × PL/SW/FD were generated in P6.6 (instance
   repo `feature/replant-tipsy-curves` @ `42bc969`) and are wired in
   (P6.7): `load_replant_curves_from_btc` + the `replant_curves` overlay
   in `build_multi_species_yields()`; synthetic Chapman–Richards remains
   the explicit fallback (with a diagnostic). The femic
   species-proportion-sidecar path stays for per-species attribution of
   existing stands if femic populates it later. Species mixes and OT have
   no TIPSY representation yet (mixes deferred; OT falls back to
   synthetic).

2. **Number of replant species — RESOLVED.** All 4 (SX, PL, FD, OT) are
   supported; the action-count limitation was retired (see Known
   Limitation 1). Action count scales the LP, so policies should still
   register only policy-relevant species for large horizons.

3. **Replant cost data — documented defaults.** Flat per-ha costs by
   species class in `economy/types.py::_default_replant` (PL 2200, SX
   2400, FD 2600, OT 2200 CAD/ha; flagged assumption, not charged by
   default since the $45/m3 harvest cost carries silviculture;
   `charge_replant_in_npv` flips it on). Calibrate against a
   femic/fhops source before relying on cost-driven species choice.

4. **Theme count — confirmed.** 5 themes (TSA, IFM, AU, ORIGIN,
   SILV_STATE); replant targets are AU variants, not new themes.

5. **Performance — recorded.** Real instance (tsa29mini, 5 action
   codes): h=10 ≈ 35 s build+solve per scenario (P6.7 validation);
   h=30 with replant actions exceeds an hour per scenario (consistent
   with the P3.4 scaling bounds: h=20 ~377k vars/~6 min at 3 actions,
   h=24+ tens of minutes). Full-MC catalogue sizing at h=30 with replant
   actions is a study-design consideration, not a code limitation.

## Known Limitations

1. **~~ws3 action-dropping at high action counts~~ — RESOLVED (P6.9).**
   The Phase-4 observation (actions silently losing all paths at 7+
   action codes) was a *fresh-fuchs* bug, not ws3: before the DTK
   pre-creation fix (P6.2, `a39a2fb`), replant transitions pointed at
   non-existent DTKs, so the tree builder never branched on those
   actions. Re-verified on ws3 1.0.5 (PyPI) and 1.1.0a5 (editable):
   7 action codes (4 replant species) × horizon 10 → every action has
   live paths (279 each on the synthetic 2-AU instance) and the LP
   solves optimal. Regression guards:
   `test_replant_lp.py::test_four_species_all_actions_survive_and_solve`,
   `test_replant_composition.py::test_four_species_composition_solves`.
   Four replant species are now the supported configuration.

2. **Bundle lacks species-proportion curves; replant curves now
   generated (P6.6 ✅)**: the femic tsa29mini bundle is available
   locally (`femic/external/femic-tsa29mini-instance`) but ships only
   treated/untreated aggregate curves (108 curves) — no
   species-proportion curves. For the replant feature, real
   pure-plantation TIPSY (BTC) curves for every source AU × PL/SW/FD
   (63 curves) were generated on this host under a self-contained
   Linux+Wine lane and committed to the instance dataset repo (branch
   `feature/replant-tipsy-curves`, `42bc969`; run manifest
   `data/tipsy_replant_run_manifest.json`). Remaining: wiring those
   curves into `build_multi_species_yields()` and the end-to-end
   real-instance run — P6.7 (#49). Species mixes were descoped from
   P6.6 (pure options only; mix ratio decision deferred). All
   fresh-fuchs tests still use synthetic fixtures.

## Key Files Reference

| File | Current Role | Status |
|------|-------------|--------|
| `instance/woodstock.py` | Bootstrap, transition registration | ✅ Wired replant actions via `replant_species` param |
| `instance/replant.py` | Replant action registration, DTK pre-creation, `target_species_from_acode` | ✅ Phase 2+3+5 complete (pre-creation fix applied; salvage replant also pre-creates DTKs) |
| `instance/yields_multi.py` | Multi-species yield curves; BTC replant store loader + resolution order (real > synthetic) | ✅ Phase 1 + P6.7 complete |
| `scenario/fire_lp.py` | Fire LP, salvage, path stepping, per-species extraction, replant DTK operability, salvage replant economics | ✅ Phase 3+4b+5 complete (operability fix applied) |
| `scenario/pipeline.py` | Scenario→LP pipeline, replant wiring, species-specific records | ✅ Phase 4b complete |
| `outer/policy.py` | Composition + harvest LP rows, three-phase transition | ✅ Phase 4 complete |
| `outer/records.py` | PolicyRecord (`replant_actions`), CompositionTarget (three-phase) | ✅ Phase 4 complete |
| `outer/grid.py` | PolicyGrid expansion, `CompositionGridAxis` | ✅ Phase 4 complete |
| `reports/replant_summary.qmd` | Quarto report (11 chunks: tables, charts, BC distance) | ✅ Phase 4b complete |
| `scripts/render_report.py` | CLI wrapper: LP pipeline + quarto render | ✅ Phase 4b complete |
| `economy/cashflow.py` | Harvest cash flow, replant cost | Deferred to Phase 5 |
| `economy/npv.py` | NPV objective wiring | Deferred to Phase 5 |
| `cli.py` | CLI commands | Deferred to Phase 6 |
