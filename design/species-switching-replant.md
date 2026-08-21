# Species-Switching Replant Transitions

Status: **Design**

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

**Verification**:
- Model with replant actions compiles successfully ✅
- `operable_area()` returns correct values for replant actions ✅
- `apply_action()` with replant action transitions to correct target dtk ✅
- Existing tests still pass without replant actions ✅ (192 passed, 1 skipped)

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

### Phase 5: Salvage Replant Integration

**Goal**: Salvage actions can replant with a different species.

**Tasks**:
1. Extend `path_fire_steps` to handle salvage replant actions
   (treat like salvage + species switch)
2. Extend `compile_path_z` to apply burned-price discount +
   replant cost for salvage replant actions
3. Wire salvage replant actions into `FireLpConfig`
4. Tests:
   - Salvage with species switch solves correctly
   - Burned price discount + replant cost applied

**Verification**:
- Salvage replant LP solves
- Correct economics (burned price + replant cost)
- Salvage feasibility constraint still holds

**Files**:
- Modified: `src/fresh_fuchs/scenario/fire_lp.py`
- New: `tests/test_replant_salvage.py`

### Phase 6: CLI + Example Configs

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

## Open Questions

1. **Yield curve source**: The femic bundle framework supports species
   proportion curves but the tsa29mini bundle doesn't populate them yet.
   The ``si_level`` (L/M/H) column exists as a grouping variable for
   site-index transfer. Synthetic curves are the current default path.
   See ``design/yield-curve-framework.md`` and
   ``src/fresh_fuchs/instance/yields_multi.py``.

2. **Number of replant species**: All 4 (SX, PL, FD, OT) or a subset?
   Each additional species multiplies the action count. Recommend
   starting with 2-3 for testing.

3. **Replant cost data**: Per-species planting costs need to come from
   somewhere (economics config, bundle data, or hardcoded defaults).

4. **Theme count**: The 5-theme structure (TSA, IFM, AU, ORIGIN,
   SILV_STATE) stays. Replant actions target different AUs (which have
   different yield curves), not different themes. No 6th theme needed.

5. **Performance**: More actions = larger LP. With 4 replant species,
   the action count goes from 3 (null, harvest, salvage) to 7. The
   Model I tree grows proportionally. Monitor solve times on tsa29mini.

## Key Files Reference

| File | Current Role | Changes Needed |
|------|-------------|----------------|
| `instance/woodstock.py` | Bootstrap, transition registration | ✅ Wired replant actions via `replant_species` param |
| `instance/replant.py` | ✅ Replant action registration | Phase 2 complete |
| `instance/yields_multi.py` | ✅ Multi-species yield curves | Phase 1 complete |
| `scenario/fire_lp.py` | Fire LP, salvage action, path stepping | Extend for replant actions (Phase 3) |
| `economy/cashflow.py` | Harvest cash flow, replant cost | Add replant cost per species (Phase 3) |
| `economy/npv.py` | NPV objective wiring | Extend for replant cost (Phase 3) |
| `outer/policy.py` | Composition + AAC LP rows | Extend for action-based composition (Phase 4) |
| `outer/records.py` | PolicyRecord, CompositionTarget | Add replant_actions field (Phase 4) |
| `outer/grid.py` | PolicyGrid expansion | Extend for replant config |
| `cli.py` | CLI commands | Add --replant-species flag |
