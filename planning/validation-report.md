# FUCHS Validation Report (Phase 1)

Phase 1 (Instance and model integration) verification and calibration
records. Companion to `v0.1.0a1-plan.md`.

## Environment (P1.0, locked)

- Python 3.12.3 venv at the FRESH workspace root.
- `ws3` resolves to the local source checkout (`ws3/ws3/__init__.py`,
  code version 1.1.0a4; pip metadata 1.0.5). Highspy 1.15.1.
- `femic` installed editable (`--no-deps`) from the source checkout
  (`femic/src`), version 0.2.0a1.
- Bundle: `femic-tsa29mini-instance` (annex submodule, data materialized).

## Regression anchors (deterministic baseline)

| Anchor | Reference (ws3/notebook) | fresh-fuchs | Status |
|---|---|---|---|
| Total bundle area | 90,499.8 ha (fragments) | 90,499.7978 ha | PASS |
| Managed land base after retention split | 35,083.0 ha | 35,083.015 ha | PASS |
| Unmanaged land base after retention split | 55,416.8 ha | 55,416.782 ha | PASS |
| Analysis units | 21 | 21 | PASS |
| Curves | 108 | 108 | PASS |
| Yields table rows | 1,407 | 1,407 | PASS |
| Development types (ws3, after split) | 73 | 73 | PASS |
| Max initial age (drives null operability) | 436 | 435 (post-midpoint) | INTENTIONAL |
| Distinct initial ages | 264 (raw F_AGE) | 37 (10-yr midpoints) | INTENTIONAL (tight model) |
| 30-period mean annual harvest (even-flow LP) | ~35,381 m3/yr | PENDING (30-period run) | -- |
| 30-period mean annual harvest (heuristic) | (record here) | PENDING | -- |
| 30-period mean annual harvest (Patchworks) | ~34,094 m3/yr | reference only | -- |

Notes:

- `build-model` reports total area 90,498.6 ha via `model.inventory(period=0)`;
  the ~1.2 ha gap vs the fragment total is the rounding of area records to
  6 decimals in the `.are` section plus ws3's `area_epsilon` handling.
- The 30-period even-flow LP run is slow (~1-2 h, single worker); smoke
  validation uses `--horizon 3`.

## Model tightness (maintainer direction)

- No LU/land-use theme: the Woodstock dataset carries exactly five themes
  (TSA, IFM, AU, ORIGIN, SILV_STATE). `bootstrap_model` fails hard if the
  loaded model has any other theme count.
- Ages are smashed to 10-year ageclass midpoints (`age_to_midpoint`,
  default `ageclass_width=10` in `InstanceConfig`): 264 distinct fragment
  ages -> 37 distinct initial ages (5..435, all midpoints). ws3 interpolates
  yields at any real age (piecewise-linear `Curve.__call__`), so midpoint
  volumes are exact interpolants of the curve table. Fewer initial ages
  means fewer action branches in the Model I LP, keeping models tight.

## P1.4 Open investigation: harvest-area discrepancy vs Patchworks

(TBD — carried from project notes: ws3 bridge harvests ~32% more area at a
lower volume per hectare than Patchworks on the same land base. Hypotheses to
test: yield-strata resolution, merchantability/volume discounts, operability
age-band differences.)
