# Multi-Species Yield Curve Framework

Status: **Implemented** (Phase 1 of species-switching replant design)

## Motivation

Species-switching replant transitions require yield curves for the target
species at each analysis unit. Currently each AU has one species and one
yield curve (the native species). To replant AU 1001 (PL site) as FD,
we need an FD yield curve for that site.

## Data Dependency (Flagged)

The tsa29mini bundle does NOT currently populate species proportion curves.
All 108 curves are `treated`/`untreated` (single-species per AU).

The femic framework *supports* multi-species proportion curves:
- `BundleModelContext.managed_species_curve_ids: dict[int, dict[str, int]]`
- `BundleModelContext.unmanaged_species_curve_ids: dict[int, dict[str, int]]`
- Curve types in `curve_table.csv`: `managed_species_prop_<species>`,
  `unmanaged_species_prop_<species>`

But the current bundle doesn't populate them. The `si_level` column
(L/M/H) exists in `au_table.csv` as a grouping variable but isn't used
for cross-species transfer yet.

## Grouping Variables Available

| Variable | Source | Purpose |
|----------|--------|---------|
| `si_level` (L/M/H) | `au_table.csv` | Site-index level for curve scaling |
| `stratum_code` | `au_table.csv` | Forest stratum grouping |
| `curve_id` | `au_table.csv` | Base curve ID (species proportion curves derived from this) |
| `canfi_species` | `au_table.csv` | Native species code |

The `si_level` is the primary grouping variable for site-index transfer.
AUs with the same `si_level` share similar site productivity, making them
candidates for cross-species yield curve derivation.

## Strategy (Ordered by Data Availability)

### 1. Bundle Species Proportion Curves

When the femic bundle provides `managed_species_prop_<species>` curves:

```
species_volume[au_id, species, age] = total_volume[au_id, age] * proportion[au_id, species, age]
```

The `build_multi_species_yields_from_bundle_context()` function implements
this path using `BundleModelContext.managed_species_curve_ids`.

### 2. Site-Index Transfer

Use `si_level` as a grouping variable. Within each group (L, M, H):
1. Map `si_level` to SI_50 values: L=15m, M=25m, H=35m
2. Apply species-specific growth functions scaled by SI conversion:
   `SI_target = f(SI_source, species_pair)`
3. Generate yield curves using the scaled growth function

This requires site-index conversion equations (e.g., Wang et al. 2002).
The framework is ready but the conversion equations are not yet
implemented.

### 3. Synthetic Fallback (Current Default)

Use species-specific Chapman-Richards growth curves with parameter defaults:

```
V(age) = a * (1 - exp(-b * age))^c
```

Parameters by species (calibrated to typical BC yield curves at SI_50=25m):

| Species | a | b | c | si_alpha |
|---------|---|---|---|----------|
| PL (lodgepole pine) | 420.0 | 0.012 | 1.8 | 1.0 |
| SX (spruce) | 380.0 | 0.010 | 2.0 | 1.1 |
| FD (Douglas-fir) | 500.0 | 0.008 | 2.2 | 1.2 |
| OT (other) | 350.0 | 0.011 | 1.9 | 1.0 |

SI scaling: `a_scaled = a * (SI / 25)^si_alpha`

These parameters are synthetic defaults. Real parameters should come from
BC forestry yield curve literature or the femic bundle.

## Data Structure

```python
@dataclass(frozen=True)
class YieldCurve:
    ages: tuple[int, ...]
    volumes: tuple[float, ...]

@dataclass(frozen=True)
class MultiSpeciesYieldTable:
    curves: dict[tuple[int, SpeciesClass], YieldCurve]

    def get(self, au_id: int, species: SpeciesClass) -> YieldCurve | None: ...
    def available_species(self, au_id: int) -> list[SpeciesClass]: ...
    def species_for_au(self, au_id: int) -> dict[SpeciesClass, YieldCurve]: ...
```

## API Functions

```python
# Synthetic fallback (current default)
build_multi_species_yields_from_synthetic(
    au_ids, *, native_species, si_levels, target_species, max_age, step
) -> MultiSpeciesYieldTable

# Bundle-based (when available)
build_multi_species_yields_from_bundle_context(
    context, *, target_species
) -> MultiSpeciesYieldTable

# Unified entry point
build_multi_species_yields(
    *, au_table, bundle_context, native_species, target_species, max_age, step
) -> MultiSpeciesYieldTable
```

## Upgrade Path

When the femic bundle is enhanced with species proportion curves:

1. `build_multi_species_yields()` will automatically use the bundle path
   when `bundle_context` is provided
2. The `MultiSpeciesYieldTable` interface is unchanged
3. Phase 2 (replant action registration) and Phase 3 (LP wiring) work
   identically regardless of the yield curve source

## Test Coverage

21 tests in `tests/test_yields_multi.py`:
- `YieldCurve` construction, interpolation, clamping
- `MultiSpeciesYieldTable` lookup, species listing, AU listing
- Synthetic curve generation, SI scaling, species differentiation
- Build functions from synthetic data, AU tables, default parameters

All 169 tests pass (1 skipped).

## Files

| File | Status | Purpose |
|------|--------|---------|
| `src/fresh_fuchs/instance/yields_multi.py` | New | Multi-species yield curve framework |
| `tests/test_yields_multi.py` | New | 21 tests for the framework |
| `design/species-switching-replant.md` | Updated | Phase 1 marked complete |
