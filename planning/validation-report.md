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
| 30-period mean annual harvest (even-flow LP) | ~35,381 m3/yr (raw-age ws3) | 35,451 m3/yr (10-yr midpoints) | PASS (+0.2%) |
| 30-period mean annual harvest (oldest-first heuristic) | (record here) | 91,718 m3/yr | RECORDED |
| 30-period mean annual harvest (Patchworks) | ~34,094 m3/yr | reference only | -- |

Notes:

- `build-model` reports total area 90,498.6 ha via `model.inventory(period=0)`;
  the ~1.2 ha gap vs the fragment total is the rounding of area records to
  6 decimals in the `.are` section plus ws3's `area_epsilon` handling.
- The 30-period even-flow LP run is slow (~1-2 h, single worker); smoke
  validation uses `--horizon 3`.
- 2026-08-13 30-period run (tightened model, midpoint ages): LP optimal;
  per-period volumes within the 5% even-flow band (period 1 = 361,129 m3;
  periods 3-20 at -5%, 21-30 at +5%, volume-max sawtooth); total harvested
  area 94,890 ha (3,163 ha/period). Heuristic: total harvested area
  194,012 ha (6,467 ha/period), monotone age-class ramp. Anchors recorded
  from `outputs/tsa29mini/baseline_30.csv`.

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

## P1.3 Species dimension (re-scoped, static class)

- The tsa29mini bundle carries no species-proportion curves: all 108 curves
  are `treated`/`untreated`; fragments have no species attribute. femic's
  species-proportion machinery requires input curves of type
  `managed_species_prop_*` / `unmanaged_species_prop_*`, which the bundle
  does not provide. Age-varying proportions are therefore unavailable for
  the mini case (recorded data gap; Phase 4 concern gated on upstream data).
- Static primary-species class per AU from `au_table.csv` `canfi_species`
  (codes 100/204/500; see `instance/species.py` for the provenance of the
  mapping).

| Species class | CANFI code | Managed area (ha) | Share |
|---|---|---|---|
| FD (Douglas-fir) | 500 | 20,217.1 | 57.6% |
| PL (lodgepole pine) | 204 | 14,740.3 | 42.0% |
| SX (spruce) | 100 | 125.6 | 0.4% |
| Total | -- | 35,083.0 | 100.0% |

- The composition sums to the managed land-base anchor (35,083.0 ha), so
  area is conserved; the ws3 model keeps exactly five themes and the LP is
  unchanged (volume conservation follows from the untouched baseline).

## P1.4 Harvest-area discrepancy vs Patchworks (investigation, 2026-08-13)

Reference comparison (notebook cell 19, `docs/ws3_harvest_scenario_woodstock_bootstrap_demo.ipynb`):

| Metric (periods 1-30) | ws3 LP (reference) | Patchworks (`tsa29mini_patchworks_model`) | Diff |
|---|---|---|---|
| Total harvested area | 95,166 ha | 72,171 ha | +31.9% |
| Total harvested volume | 10,614,173 m3 | 10,228,152 m3 | +3.8% |
| Mean annual harvest | 35,381 m3/yr | 34,094 m3/yr | +3.8% |
| Volume per harvested ha | 111.5 m3/ha | 141.7 m3/ha | -21% |

fresh-fuchs production run reproduces the ws3 lane almost exactly (midpoint
ages): total area 94,890 ha, total volume 10,635,259 m3, 35,451 m3/yr,
112.1 m3/ha.

Diagnosis (ws3-side mechanism, reproduced):

- Per-period volume/ha of the LP schedule falls monotonically over the
  horizon (211, 184, 167, ..., 66, 36 m3/ha), i.e. the LP harvests
  increasingly marginal stands, down to ~36 m3/ha, while landscape growing
  stock RISES (6.58M -> 7.14M m3). This is a flow-maintenance artifact, not
  liquidation.
- Managed operable stock at period 0 (age >= 60) is only 22,067 ha of the
  35,083 ha managed base, mean 135 m3/ha; only 11,462 ha (52%) is >= 100
  m3/ha and 6,603 ha (30%) is >= 140 m3/ha (Patchworks' average).
- The even-flow band is on VOLUME: `(1 - eps)*V1 <= Vt <= (1 + eps)*V1` with
  `eps = 0.05`. To hold the band the LP must draw on low-volume/ha operable
  stock, inflating harvested area while adding little volume. The band is
  binding in the middle periods (periods 3-20 sit at the -5% bound; 21-30 at
  +5%), confirming stock scarcity rather than yield-definition differences.
- Flow-band sensitivity (30-period LP, same model):

  | eps | Total area (ha) | m3/yr | m3/ha |
  |---|---|---|---|
  | 0.0 (strict) | 97,026 | 35,061 | 108.4 |
  | 0.05 (production) | 94,890 | 35,451 | 112.1 |
  | 0.10 (wide) | 93,324 | 35,778 | 115.0 |

  A tighter band forces MORE area at LOWER volume/ha: the volume even-flow
  line is the direct driver of the extra area. Even at eps=0.10 the area is
  ~30% above Patchworks, so Patchworks additionally restricts its harvest
  stock (see mitigation note below).

Hypotheses:

- Yield-strata resolution: NOT the cause. Both lanes come from the same
  femic bundle context (the Patchworks XML carries 781 curves vs 108 in the
  bundle, but the main yield curves referenced by `au_table.csv` are the
  same). Volume differs by only +3.8%.
- Merch-volume discounts: NOT present in either lane (both use gross
  `totvol`). The missing mechanism is merchantability filtering: ws3's
  operability is "any stand aged 60-300", regardless of volume/ha.
- Operability / flow structure: CONFIRMED as the operative mechanism (see
  diagnosis above).

Verdict: the ~32% extra area is the ws3 LP harvesting sub-merchantable,
low-volume/ha stands to hold the volume even-flow band; it is a formulation
artifact of the volume-band even-flow setup, not a land-base or yield bug.
Mitigations to consider (not applied in P1): a merchantability floor in
harvest operability (e.g. min volume/ha; ws3 operability is expressed on
theme values and age only, so this requires a formulation-side filter or a
minimum-age proxy), an area-based even-flow target, or a looser band.
Sensitivity table: `outputs/tsa29mini/p1.4_flow_sensitivity.csv`.

Open items: Patchworks solve logs/settings for `tsa29mini_patchworks_model`
are not present in the bundle, so Patchworks' own flow rule cannot be
confirmed directly; the comparison rests on the reference notebook table.

# FUCHS Validation Report (Phase 2: Economic Valuation Layer)

Phase 2 verification and calibration records. Companion to
`v0.1.0a1-plan.md`. Commits: implementation `c846f2b`, plan update `44820b7`.

## Environment (P2, locked)

- Same Python 3.12.3 venv as Phase 1; `ws3`/`femic` unchanged.
- `fhops` installed editable (`pip install -e <ws>/fhops --no-deps`), version
  1.0.0 (pyomo/pyarrow/optuna not installed; not required by the costing
  surface). pyproject extra: `fhops = ["fhops>=1.0.0"]`.
- Bundle and fragments as Phase 1.
- CI dependency fix: ws3 1.0.5 from PyPI imports `pulp` unconditionally in
  `ws3.opt.status()` even on the HiGHS path, so `pulp` was added to the core
  dependencies (the local ws3 source checkout guards the import, which hid
  the requirement locally).

## P2.1-P2.4 Economic surface records (calibration record)

Constants composed by `economy.interior_surface()` (provenance on every
record; source `fresh-salvage/planning/economics-calibration.md`, reference
only, no import; prices at BC Interior Log Market Report Q4-2023 levels):

- SPF sawlog $127/m3 (Df-Larch $103, Hem-Bal $120, Cedar $144, Other $90);
  per-Product price records for peeler/sawlog/pulpwood.
- Harvest cost flat $45/m3 (green; carries road/admin/silviculture
  allocation — replant NOT charged by default, `charge_replant_in_npv`).
- Transport $30/m3 green, $38 burned; stumpage $15/m3 green, 0.25 x price
  burned floor; burned-price discount 0.65; burned harvest premium +25%
  ($56/m3); burned volume decay 0.85/yr; discount rate 0.03 (annual,
  end-of-period factors); grade transition downgrade-only
  (Peel {0.55/0.35/0.10}, Saw {0.00/0.80/0.20}, Pulp {1.0}).

fhops alternative harvest cost (default interior stand: 0.3 m3 stems,
180 m3/ha, 2000 stems/ha, 25% slope; machine-rate provenance + CPI 2024):

- Single feller-buncher pass: $7.15/m3 (felling only — lower bound).
- 4-pass system (fell/process/skid/load): $23.22/m3 (near the $30-40/m3
  tree-to-truck range; excludes road/admin/silviculture).

Salvage margins (zero subsidy, sawlog basis, $/m3) reconcile to the
fresh-salvage anchors:

- SPF sawlog-basis: -11.95 (calibration approx -11.7).
- SPF transition-mix: -21.31 (fresh-salvage -21..-24 band; asserted in
  tests). Df-Larch sawlog-basis -27.55 reflects the lower DF price basis and
  sits outside the SPF-dominated band — recorded, not asserted.

## P2.5 NPV objective in the inner LP (cross-validation)

Synthetic cross-checks (`tests/test_npv.py`, synthetic bundle, no femic):

- Zero discount + no price differential: NPV-max LP reproduces the
  volume-max schedule EXACTLY (per-period volume and area, series equality).
- 3% discount + no price differential: NPV-max total volume within 1% of
  volume-max total.

Real bundle (tsa29mini, 30 x 10-yr periods, 3% discount), `economy-run`
(`outputs/tsa29mini/npv_30.csv`, `npv_30.log`):

| LP | mean volume (m3/yr) | total area (ha) | volume intensity (m3/ha) | status |
|----|--------------------|-----------------|--------------------------|--------|
| volume-max (P1 baseline) | 354,509 | 94,890 | 112.1 | optimal |
| npv-max (P2, 3% discount) | 336,248 | 104,462 | 96.6 | optimal |

Both LPs bind the even-flow band at both ends (period volumes span
0.95-1.05 x period 1). The NPV-max shift (5% less volume, 10% more area,
lower m3/ha) is the first-order effect of the species price differentials
(SPF net $37/m3 vs Df-Larch net $13/m3 redirect harvest toward SPF/PL
stands) combined with discounting (period-1 area 3,155 ha at 110 m3/ha vs
1,707 ha at 212 m3/ha for volume-max). The no-differential cross-checks
isolate the mechanism; the divergence is expected, not a defect.

Open items: per-stand revenue by grade within the LP (flat sawlog-basis for
v0.1.0a1); fhops system cost as the LP harvest-cost basis (currently $45
calibration flat) — both flagged for later phases.
