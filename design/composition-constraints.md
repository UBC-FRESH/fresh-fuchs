# Composition Constraints

Status: **Implemented** (branch `feature/composition-points`)

## Motivation

The inner LP maximizes NPV subject to an even-flow constraint on total
harvest volume. Without composition constraints, the LP is free to
concentrate harvesting on whichever species is most profitable, which
can silently erode species diversity on the landscape.

Composition constraints pin the **per-period harvested-area share** of
target species groups to a specified range, forcing the LP to maintain
a diversified harvest across species.

## Two Modes

### 1. `composition_axes` (Cartesian product)

User specifies one or more species-share values per species. The
`expand()` method computes the Cartesian product of all axis values,
generating every possible combination as a separate policy record.

```json
{
  "composition_axes": {
    "SX": [0.30, 0.40],
    "PL": [0.40, 0.50, 0.60]
  },
  "composition_tolerance": 0.05
}
```

This produces 2 x 3 = 6 policy records, each with a unique
(SX share, PL share) pair.

### 2. `composition_points` (explicit combinations)

User specifies an explicit list of species-share dicts. Only the listed
combinations are generated — no Cartesian product.

```json
{
  "composition_points": [
    {"SX": 0.30, "PL": 0.50, "FD": 0.20},
    {"SX": 0.40, "PL": 0.40, "FD": 0.20}
  ],
  "composition_tolerance": 0.05
}
```

Each dict can optionally include a `"tolerance"` key that overrides
the grid-level `composition_tolerance` for that point.

**Precedence**: `composition_points` takes priority over
`composition_axes` when both are non-empty.

## How It Enters the LP

Composition targets are carried by `PolicyRecord` objects (field
`composition_targets: tuple[CompositionTarget, ...]`). Each
`CompositionTarget` has `(species, target_share, tolerance)`.

In `outer/policy.py`, two coefficient functions per target species
generate the LP rows:

- `comp_lo_{i}`: coefficient = `area_species - (target - tol) * area_total`
- `comp_hi_{i}`: coefficient = `area_species - (target + tol) * area_total`

Bounds:
- `comp_lo_{i}`: lower bound >= 0 (harvested share >= target - tol)
- `comp_hi_{i}`: upper bound <= 0 (harvested share <= target + tol)

These are added via the `cgen_data` pattern in `model.add_problem()`,
exactly like the salvage-feasibility row.

Species identification uses `species_by_dtk` (a dict mapping ws3
development-type keys to `SpeciesClass` values). This is a **static**
mapping derived from the AU → CANFI species code in the initial
inventory.

## What the LP Constrains

The constraint applies to **per-period harvested-area share** within
each scenario solve. It is a policy-level constraint — identical across
all scenarios for a given policy.

Concretely: if the target is SX at 0.30 +/- 0.05, then in every
period the LP must harvest between 25% and 35% of its total harvested
area from SX development types.

## Limitations

1. **No species switching on replant.** The harvest transition resets
   the stand to age 0 of the same development type (same species).
   Composition targets are met by skewing *which* species are harvested,
   not by changing *what is planted*.

2. **Static species mapping.** `species_by_dtk` is derived from the
   initial inventory and never changes. If the model supported
   species-switching replant, the mapping would need to track the
   post-replant species.

3. **Feasibility pressure.** If the standing forest's species mix is
   far from the target, the constraint can be very tight or infeasible.
   The tsa29mini smoke run (3 periods) showed all constrained policies
   failing — the AAC + composition constraints together were
   infeasible.

## Verification

- 7 tests in `tests/test_grid.py` covering:
  - `composition_points` expansion (2 points)
  - Unconstrained policy (no targets)
  - Per-point tolerance override
  - `composition_points` takes precedence over `composition_axes`
  - No harvest axis error
  - `composition_axes` still works (backward compat)
- All 148 tests pass; lint clean

## Files

| File | Role |
|------|------|
| `src/fresh_fuchs/outer/grid.py` | `PolicyGrid.expand()`, `_expand_composition_points()`, `_expand_axes_cell()` |
| `src/fresh_fuchs/outer/records.py` | `PolicyRecord`, `CompositionTarget` dataclasses |
| `src/fresh_fuchs/outer/policy.py` | `policy_coeff_funcs()`, `policy_cgen_data()` — LP row construction |
| `tests/test_grid.py` | Composition-points tests |
| `examples/policy-grid.composition-points.json` | Example config |
