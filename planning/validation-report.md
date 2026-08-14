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

# FUCHS Validation Report (Phase 3: Full-MC Scenario Engine)

Phase 3 verification and calibration records. Companion to
`v0.1.0a1-plan.md`.

## Environment (P3, locked)

- Same Python 3.12.3 venv as Phases 1-2; ws3/femic/fhops unchanged.
- Bundle and fragments as Phase 1. fresh-salvage is reference only and NOT
  installed in this environment; parity is asserted against reference values
  carried in `src/fresh_fuchs/scenario/fire.py`.

## P3.1 Fire dynamics (calibration record)

Constants and dynamics reimplemented in `scenario/fire.py` with the
fresh-salvage reference cited (no import):

- MFRI by BEC zone: SBPS 100, IDF 200, MS 150, ESSF 200, ICH 250, SBS 125;
  annual burn probability `1/MFRI`; burned-decay retention 0.85/yr.
- Severity ladder (fresh-salvage `SEVERITY_TO_BURNED_FRAC`): Unburned 0.0,
  Low 0.30, Moderate 0.60, High 0.85; tsa29mini has no burn-severity
  polygons, so severity is a scenario parameter (default Moderate).
- Annual ordering contract harvest -> fire -> salvage -> decay: burn influx
  `R * V_rem[t]`, salvage ceiling `B[t-1] + BURN_IN[t]`, burned balance
  `(B + BURN_IN - S) * 0.85`.
- 10-year period burn probability `1 - (1 - R)^10` (SBPS ~0.0956, IDF
  ~0.0489).

Zone coverage (tsa29mini `au_table.csv`, 21 AUs): 12 IDF + 9 SBPS via the
`{BEC}_{species}` stratum codes; unmapped zones fail fast
(`UnknownBurnRateError`). The full MFRI ladder is carried so future bundles
with more zones work unchanged.

Parity: 14 unit tests assert the reference values and the dynamics ordering;
the full suite is 68 tests.

## P3.2 Distribution framework (calibration record)

`scenario/distributions.py` provides the parameter-distribution registry with
seed control:

- Families: `fixed` (deterministic value), `gaussian` (mean/std), `empirical`
  (sample uniformly from a provided array). Field validation per family.
- Seeding: every draw funnels through `numpy.random.default_rng`; a full
  vector draw under one master seed is bit-stable (dimensions drawn in
  declaration order).
- `UncertaintyVector` maps `UncertaintyDimension` (fire_burn_rate, price) to
  a `ParameterDistribution`, meeting the notes' fire + price vector
  requirement (only fire active in v0.1.0a1).
- nemora integration: `nemora_sample_distribution` delegates to
  `nemora.sampling.sample_distribution` with a seeded generator, gated by
  `MissingDependencyError` when nemora is absent (it is not installed here;
  the empirical family samples its own array, whose Phase 4 source is
  nemora's bootstrap).

## P3.3 Scenario records and generator (calibration record)

`scenario/records.py`:

- `FireEvent` (period, BEC zone, annual burn rate in [0,1], severity tier)
  with per-family validation; `DisturbanceScenario` (name, seed,
  probability, burn-rate multiplier, price factor, severity, events) with
  `to_dict` in the ws3 `StochasticScenario` shape and a `from_dict`
  round-trip.
- `generate_scenarios(params)` draws each scenario's uncertainty vector
  (P3.2) under `master_seed + i`, then expands deterministic zone rates
  (SBPS 0.01, IDF 0.005) into per-period events in sorted-zone x period
  order. Seed-fixed catalogues are bit-stable (asserted in tests); a
  scenario catalogue writer emits JSON with provenance.
- Record count: 85 tests total.

## P3.4 Fire in the ws3 model (verification record)

`scenario/fire_lp.py`:

- Fire enters the Model I even-flow/NPV LP as **path-dependent
  coefficients**, not extra burn decisions: per-period survival
  `product_{u<t}(1-p(u))` since last regeneration (harvest/salvage resets
  the stand); green harvest volume = `Y(a_t) x survival_to(t)`; burn influx
  = `p(t) x exposed live` (0 in harvest periods: harvest precedes fire);
  salvageable = `severity_fraction x p(t) x exposed`.
- `salvage` is a real Model I action (regeneration transition to age 0).
  Operability is pruned per (zone, period) where burn probability = 0
  (`apply_salvage_operability`) and floored at `min_salvage_age = 60`
  (`add_salvage_action`), which also bounds Model I tree growth: a salvaged
  cohort only reopens the salvage branch once back above rotation age.
- Salvage feasibility row `salvage_vol(t) - salvageable_vol(t) <= 0` is an
  explicit general row (`cgen` ub=0). Salvage is a free LP decision at the
  P2.4 margins: default negative SPF margin (-11.95) -> the LP salvages
  nothing (matching the fresh-salvage reference agent); a positive
  (subsidised) margin exercises the mechanism. Salvage-priority forcing
  rows are documented out of scope (degenerate: a forced salvage
  regenerates the stand, so a priority floor collapses to "salvage
  everything immediately").
- The walk (`path_fire_steps`) reads per-ha `totvol` yields from
  `ycomp[age]` scaled by the initial cohort area, so it is independent of
  the model's transient applied-action state and works both at tree-build
  time and post-solve.
- Tests (`tests/test_fire_lp.py`, 8): survival compounds across null
  periods and resets after harvest/salvage; salvage <= burned pool on all
  paths; fire-free seed reproduces the volume-max baseline under a uniform
  zero-discount surface; fire strictly reduces the NPV objective; salvage
  feasibility + economics govern (negative margin -> 0 salvage, positive
  margin -> salvage up to pool); missing zone mapping fails fast.
- Real-bundle LP size (tsa29mini, 213 dtypes, every zone burning every
  period): h=20 -> 377k vars / ~6 min build; h=30 extrapolates to ~1-4M
  vars / tens of minutes build+solve. Dense-burn scenarios are the
  computational worst case; stochastic catalogue scenarios (clustered
  events) are cheaper. Baseline (no salvage) h=30 = 773k vars / ~4 min.
- Record count: 91 tests total.

## P3.5 Scenario -> LP pipeline (verification record)

`scenario/pipeline.py`:

- `run_scenario_lp` boots a fresh ws3 model per scenario (cheap), registers
  the salvage action, applies scenario operability, builds the fire-aware
  LP (`add_fire_problem`), solves/applies it, and records the schedule +
  total NPV + status as a `ScenarioRunRecord` (per-period harvest/salvage/
  salvageable/growing-stock table).
- `run_scenario_pipeline` solves scenarios sequentially or over a process
  pool using the **spawn** start method: the parent process is
  multi-threaded (solver/OpenMP state) and forking it would be unsafe
  (forking first crashed the worker). Each scenario solves from its own
  fresh model under fixed seeds, so parallel results are bit-identical to
  the sequential run (asserted in tests).
- `write_pipeline_record` emits `pipeline_run.json` (scenarios + per-scenario
  schedules + NPV + environment: python/fresh-fuchs/ws3/solver versions),
  one `scenario_XXXX_schedule.csv` per scenario, and a
  `pipeline_summary.csv`.
- Salvage area is reported from the same leaf accounting as salvage volume
  (weighted by solved path fractions), so objective-neutral degenerate
  salvage branches do not inflate the area report; volume and area are
  consistent (0 salvage volume -> 0 salvage area).
- CLI `scenario-run` wires the whole command: builds `zone_by_au` from the
  bundle au_table stratum prefixes, `zone_burn_rates = 1/MFRI` per present
  zone, a seed-fixed Gaussian burn-multiplier catalogue, then the pipeline.
- Real-bundle smoke (tsa29mini, h=8, 2 scenarios, 2 workers): both optimal,
  NPV 19.71M / 19.74M, mean annual harvest ~50k m3/yr, salvage 0 at the
  default negative margin, salvageable pools tracked per period. Real-bundle
  LP size: h=8 ~141k vars (~1 min build); h=20 ~377k vars (~6 min);
  h=24+ grows to tens of minutes per scenario (all-periods burn worst
  case) — bounds the full-MC catalogue size at h=30; fire-free (p=0)
  scenarios are cheap (~4 min at h=30, the P3.6 reproduction anchor).
- Tests (`tests/test_pipeline.py`, 4): record shape; parallel (2 workers)
  bit-matches sequential; scenarios actually differ in burn draw; record
  writer emits JSON + CSVs.
- Record count: 95 tests total.

## P3.6 Acceptance (verification record)

`tests/test_phase3_acceptance.py` (3 tests, public-safe synthetic):

- `test_pipeline_fire_free_reproduces_volume_max_baseline`: fire-free
  scenario through the full P3.5 pipeline (`run_scenario_lp`, zero-discount
  uniform surface) reproduces the deterministic even-flow volume-max
  schedule exactly (per-period harvest to 1e-6); salvage volume zero.
  (The P3.4 LP-level fire-free equivalence test remains in
  `test_fire_lp.py`.)
- `test_burn_rate_monotone_decreases_npv`: burn multiplier
  0.0/0.5/1.0/2.0 (same seed, all periods, both zones) -> total NPV
  strictly decreasing.
- `test_pipeline_seed_fixed_runs_bit_stable`: two pipeline runs under the
  same master seed produce identical run records (bit-stable, deterministic
  solver path).

Recorded real-bundle evidence (needs private data; not part of the test
suite):

- Fire-free h=30 (tsa29mini, no events): reproduces the P2.5 NPV-max anchor
  exactly — mean annual harvest 33,624.77 m3/yr, total harvested area
  104,462.175 ha, per-period diffs < 1e-6 vs `outputs/tsa29mini/npv_30.csv`
  (NPV objective 19.62M; build+solve ~13.6 min; the fire-free LP is the
  same even-flow + NPV LP with a zero salvage-feasibility row).
- Monotonicity h=8 (all zones burning, four burn multipliers):

  | mult | status | NPV (z) | harvest m3/yr | harvested ha | salvageable m3 |
  | --- | --- | --- | --- | --- | --- |
  | 0.0 | optimal | 23,350,932 | 49,596 | 40,768 | 0 |
  | 0.5 | optimal | 21,557,788 | 49,803 | 40,657 | 123,462 |
  | 1.0 | optimal | 19,899,102 | 50,033 | 40,424 | 243,092 |
  | 2.0 | optimal | 16,941,297 | 50,128 | 40,318 | 468,926 |

  Expected NPV strictly decreases with burn rate; salvageable pool grows
  monotonically; green even-flow held (harvest level rises slightly as the
  standing merchantable pool grows and salvage remains at the default
  negative margin).
- Salvage area/volume consistency re-checked on the h=8 two-scenario CLI
  run: period-8 salvage_area 0.0 with salvage_volume 0.0 (leaf accounting
  excludes objective-neutral degenerate salvage branches), salvageable pool
  tracked separately.

Record count: 98 tests total; ruff, docs, build, twine green.

- CI compatibility fix (ws3 1.0.5, PyPI — the version CI installs):
  `apply_salvage_operability` originally recorded closed fire-free periods
  as `operability["salvage"][period] = None`, which PyPI ws3 1.0.5's
  `is_operable`/`operable_ages` cannot unpack (TypeError); the local
  editable ws3 1.1.0a4 tolerates it. Closed periods now use the empty age
  window `(0, -1)`, which both ws3 versions treat as closed. Full suite
  passes against both ws3 1.0.5 and 1.1.0a4.

## P4.1 Outer policy records and constraints (verification record)

`src/fresh_fuchs/outer/records.py` (CompositionTarget, HarvestPolicy,
HarvestPolicyMode, PolicyRecord) and `src/fresh_fuchs/outer/policy.py`
(coeff/cgen row builders, `apply_rotation_constraints`), wired into
`add_even_flow_problem` (baseline) and `add_fire_problem` (fire-aware)
plus `run_scenario_lp`/`run_scenario_pipeline` (policy threaded through
the parallel payload as element 8). `tests/test_outer_policy.py` (6 tests):

- `test_composition_target_binds_species_mix`: a 90%±5% PL composition
  target (composition-only policy, no harvest policy) forces the harvested
  area mix to PL — solver optimal, PL share 0.90 within [0.85, 0.95].
- `test_aac_proxy_pins_harvest_volume`: AAC row pins every period's
  harvest volume to the policy band upper edge (binding: each period hits
  `aac * period_length * (1 + tolerance)` to 1e-6). AAC level derived from
  the no-policy baseline mean annual harvest (~1,550 m3/yr); naive levels
  (e.g. 30,000 or 40,000 m3/yr) are infeasible for the synthetic fixture
  and were replaced by baseline-anchored levels.
- `test_rotation_floor_binds_pl_harvest_age`: rotation floor 140 for PL
  removes all PL harvest — the no-policy schedule harvests young PL
  (ages < 140) while the constrained schedule never does (LP skips PL
  entirely rather than cut it early). Floor semantics implemented as
  operability windows `dt.operability["harvest"][period] = (floor,
  ceiling)` so they work on both ws3 1.0.5 (PyPI) and 1.1.0a4 (editable).
- `test_rotation_floor_ceiling_bounds_harvest_age`,
  `test_records_validate`, `test_records_frozen` (record validation and
  immutability).
- `test_policy_flows_through_fire_pipeline`: composition targets fold
  into the fire-aware LP via `run_scenario_lp` (burning scenario, salvage
  path) — optimal with non-negative per-period harvest.

Design records: composition rows are scenario-independent (share of
harvested area per period, per-species cohorts via `path[0].data("area")`
and `species_by_dtk`); AAC row uses raw (pre-fire) per-period harvest
volume so it matches the reported `harvest_volume_m3` in both LPs.
Rotation constraints are applied to the model before tree build. Outer
policies are immutable records with provenance; `harvest_policy` is
optional (composition-only policies allowed).

Record count: 101 tests total; ruff, docs, build, twine green; the P4.1
suite passes against both ws3 1.0.5 (PyPI) and 1.1.0a4 (editable).

## P4.2 Grid search driver (verification record)

`src/fresh_fuchs/outer/grid.py`: `PolicyGrid` (composition axes +
one harvest axis, `include_unconstrained`), Cartesian `expand` into
`PolicyRecord` points, `run_grid` (full-MC per policy via
`run_scenario_pipeline` with the P4.1 policy rows), and
`write_grid_record` (per-policy pipeline records + grid summaries).
Policies are distributed over a spawn process pool (`policy_workers`);
each policy's scenario solves are independent and seed-fixed, so
parallel results bit-match the sequential run. Failing or infeasible
points are captured (`status="failed"`, `error`) instead of crashing the
grid. `tests/test_grid.py` (8 tests):

- `test_grid_expands_cartesian_product`: 2 composition axes x 1 x AAC
  axis x 2 values (+ unconstrained) -> 5 policies, unique names, correct
  target/AAC values.
- `test_grid_expand_rotation_axis`: rotation floor axis -> floor dicts.
- `test_grid_axis_validation`: out-of-range shares, zero AAC, rotation
  without species all rejected.
- `test_run_grid_evaluates_every_point`: 3 scenarios x 1 policy ->
  optimal runs, 3 distinct NPV samples.
- `test_run_grid_seed_fixed_bit_stable`: two runs, same grid -> identical
  statuses and NPV samples.
- `test_run_grid_parallel_bit_matches_sequential`: 4 policies,
  `policy_workers=2` -> identical results vs sequential.
- `test_run_grid_failed_policy_recorded_not_crashing`: infeasible AAC ->
  `status="failed"`, `error` set, grid completes.
- `test_write_grid_record_writes_summaries_and_per_policy`: per-policy
  pipeline records + `grid_summary.csv` (per-scenario NPV columns) +
  `grid_summary.json`.

CLI `policy-grid` (thin wrapper over `run_grid`; grid spec via
`--grid-json`). Example spec: `examples/policy-grid.tsa29mini.json`.

Real-bundle evidence (needs private data; not part of the test suite),
`outputs/tsa29mini/policy_grid_smoke*`:

- Composition-only grid, h=6, 2 scenarios (master seed 42):
  | policy | status | NPV mean | mean annual harvest |
  | --- | --- | --- | --- |
  | unconstrained | ok | 21,194,385 | 57,361 m3/yr |
  | PL 85% +/- 5% | ok | 11,375,863 | 22,691 m3/yr |
  | PL 90% +/- 5% | ok | 10,319,649 | 18,951 m3/yr |
  Expected: stricter PL composition target trades NPV and harvest away
  monotonically (LP is forced off the FD-rich optimum onto a PL-only
  cut), the target binds in both scenarios, and results are seed-stable.
- A PL 85% + AAC 50,000 m3/yr point is infeasible on this landscape
  (composition x harvest constraint conflict); the grid records it as
  `status="failed"` with the diagnostics and completes the sweep — the
  fail-fast behaviour required for grid robustness.

Record count: 109 tests total; ruff, docs, build, twine green; the P4.2
suite passes against both ws3 1.0.5 (PyPI) and 1.1.0a4 (editable).

## P4.3 Risk metrics (verification record)

`src/fresh_fuchs/outer/risk.py`: pure functions over an NPV sample with
explicit definitions (all in NPV space, "loss = low NPV"):

- ``expected_npv`` (mean), ``npv_volatility`` (sample std, ddof=1).
- ``value_at_risk(alpha)``: empirical alpha-quantile
  (``np.quantile(..., method="inverted_cdf")``): with probability
  ``1 - alpha`` the NPV falls at or below this level.
- ``conditional_value_at_risk(alpha)``: mean of the worst
  ``floor((1 - alpha) * n)`` observations (>= 1, so well-defined on small
  samples).
- ``shortfall_probability(threshold)``: fraction of observations strictly
  below the threshold.
- ``gaussian_tail_metrics``: analytic VaR/CVaR for a Normal fitted to the
  sample moments (``z_alpha = Phi^{-1}(alpha)`` via A&S 26.2.23 + Newton
  on ``math.erf`` — no scipy dependency; CVaR = mu - sigma phi(z)/(1-a)).
  Recorded as a *comparison*, not the metric.
- ``RiskReport`` per policy (metrics + Gaussian comparison + provenance),
  plus ``risk_reports_from_grid`` (one report per successfully solved grid
  point).

`tests/test_risk.py` (9 tests):

- Analytic checks on the constructed sample 1..100: VaR(0.95) = 95,
  VaR(0.5) = 50, VaR(0.05) = 5; CVaR(0.95) = 3 (worst 5), CVaR(0.99) = 1;
  shortfall below 10 = 9%; sample mean 2.5 / std on 1..4.
- CVaR monotone non-increasing in alpha and <= E[NPV] on a seeded Normal
  sample; CVaR <= VaR on grid results (worst-tail mean can never exceed
  the tail boundary).
- Gaussian comparison reproduces the hand-computed values
  (z_0.95 = 1.64485...; mu - sigma phi(z)/(1-a)).
- ``risk_reports_from_grid`` over a real 3-scenario grid run.

Record count: 118 tests total; ruff, docs, build, twine green; the P4.3
suite passes against both ws3 1.0.5 (PyPI) and 1.1.0a4 (editable).

## P4.4 Ranking and report (verification record)

`src/fresh_fuchs/outer/ranking.py`: deterministic, reproducible ranking
over ``RiskReport``\\ s.

- ``RankingCriterion.E_NPV_CVAR``: lexicographic — maximize expected NPV,
  then CVaR(alpha).
- ``RankingCriterion.MEAN_CVAR``: maximize ``weight * E[NPV] +
  (1 - weight) * CVaR(alpha)`` (weight default 0.5; 0 and 1 recover the
  pure-CVaR and pure-E extremes).
- Ties broken by NPV volatility; total order via a stable sort; ranks 1..n
  and the recommended (rank-1) policy recorded in ``PolicyRanking``.

`src/fresh_fuchs/outer/report.py`:

- ``build_report``: ranking table + recommended policy, plus a
  coarse-vs-fine ``SensitivityResult`` (top-rank stability, E[NPV]/CVaR
  deltas of the top policy) when a fine-resolution ranking is supplied.
- ``write_report``: `ranking.csv`, `ranking.json`, `report.json`; a
  `tradeoff.png` (expected NPV vs CVaR, annotated) only when matplotlib is
  importable — an optional diagnostic, never required.
- ``rank_from_grid_summary``: re-derives the ranking from a ``policy-grid``
  `grid_summary.json` without re-solving (full reproducibility).

CLI `policy-rank` over a grid run record (thin wrapper). `tests/
test_ranking.py` (7 tests): lexicographic ordering (E then CVaR), mean-CVaR
weight extremes, run-to-run reproducibility (identical JSON payloads),
sensitivity record (flipped top rank + deltas), report file emission, and
the grid-summary round-trip through a real 3-policy grid run.

Real-bundle evidence (needs private data; not part of the test suite),
`outputs/tsa29mini/policy_rank_smoke` (grid `policy_grid_smoke2`, 3
policies x 2 scenarios):

| rank | policy | E[NPV] | CVaR(95%) |
| --- | --- | --- | --- |
| 1 | smoke2_unconstrained | 21,194,385 | 21,179,172 |
| 2 | smoke2_PL_0.85 | 11,375,863 | 11,369,773 |
| 3 | smoke2_PL_0.90 | 10,319,649 | 10,314,181 |

Ranking reproduces the NPV/risk ordering observed in the P4.2 grid run;
`ranking.csv`, `ranking.json`, `report.json`, and `tradeoff.png` written.

Record count: 125 tests total; ruff, docs, build, twine green; the P4.4
suite passes against both ws3 1.0.5 (PyPI) and 1.1.0a4 (editable).

## P4.5 Phase 4 acceptance (verification record)

End-to-end outer policy layer on the public-safe synthetic bundle,
`tests/test_phase4_acceptance.py` (4 tests): the full sequence
P4.1 -> P4.4 in one run — `PolicyGrid` (PL composition axis 0.85/0.9 +
non-binding PL rotation floor 60 + unconstrained baseline, 3 points) ->
`run_grid` (5 seed-fixed fire scenarios through the inner LP with policy
rows) -> `risk_reports_from_grid` (alpha 0.95) -> `rank_policies`.

- Reproducibility: two independent full evaluations produce bit-identical
  per-policy NPV samples and an identical `PolicyRanking` JSON payload
  (`run_at`/`environment` metadata excluded as expected). All 3 grid points
  solve (`status == "ok"`).
- CVaR-vs-expected trade-off: the E[NPV]-CVaR ranking is
  unconstrained (best) -> PL 85% -> PL 90% (worst), and BOTH the expected
  NPV and CVaR sequences are strictly monotone (tighter PL composition
  lowers expected value and the worst tail together); CVaR(0.95) <= E[NPV]
  for every policy; the recorded recommended policy is the rank-1
  unconstrained baseline.
- Pure-CVaR criterion (`MEAN_CVAR`, weight 0) reproduces a direct CVaR
  sort exactly — the two criteria genuinely differ on this grid only in
  the presence of E/CVaR inversions (checked in unit tests).
- Artifacts: grid record (`grid_summary.csv/json`) and report
  (`ranking.csv/json`, `report.json`) written end-to-end.

Real-bundle evidence (private data, gitignored `outputs/`; recorded in the
P4.2 and P4.4 entries above): `policy_grid_smoke2` (h=6, 2 scenarios, 3
policies: unconstrained 21.19M / 57,361 m3/yr -> PL 85% 11.38M / 22,691 ->
PL 90% 10.32M / 18,951; infeasible PL 85% + AAC 50,000 captured as
failed) and `policy_rank_smoke` (E_NPV_CVAR ranking of that grid,
recommended = unconstrained, plus `tradeoff.png`). Both the synthetic
acceptance and the real-bundle runs place the recommended policy at rank 1
and exhibit the CVaR-vs-expected ordering expected from the constraint
ladder.

Record count: 132 tests total; ruff, docs, build, twine green on both ws3
1.0.5 (PyPI) and 1.1.0a4 (editable). `CHANGE_LOG.md` Phase 4 entry added;
`ROADMAP.md` P4 marked complete; plan checklists updated.

## P5.1 Freshforge integration (verification record)

`src/fresh_fuchs/orchestration/` wraps the pipeline in freshforge
workflows/matrices with evidence. `instance/synthetic.py` (new) moves the
public-safe synthetic fixture into the package so the whole pipeline is
reproducible from the provider without private data.

- `orchestration/workflow.py`: `FuchsOrchestrationProvider`
  (freshforge `Provider` protocol, id `fuchs.orchestration`) with four thin
  node types wrapping the Python APIs — `build_model` (synthetic fixture;
  real-bundle builds run via the `fresh-fuchs build-model` CLI),
  `scenario_run`, `policy_grid`, `policy_rank`. `fuchs_workflow_spec()`
  builds the build_model -> scenario_run -> policy_grid -> policy_rank
  chain; `run_fuchs_workflow()` executes with the FUCHS registry and
  writes a `workflow_run_evidence_manifest`.
- `orchestration/matrix.py`: `load_fuchs_matrix` (validates, raises on
  error diagnostics) and `run_fuchs_matrix` (executes every case with the
  FUCHS registry, writes a `matrix_run_evidence_manifest`).
- Provider registered for entry-point discovery under the
  `freshforge.providers` group (`fuchs_orchestration`); freshforge pinned
  to commit `5bce95b` (the durable-evidence-manifests commit; the v0.1.0a5
  tag predates `evidence.py`) as an `orchestration` extra and in `dev`.
- Examples: `examples/fuchs_workflow_template.yaml` (4-node pipeline with
  a `${matrix.pl_share}` placeholder in the policy-grid node) and
  `examples/fuchs_matrix.yaml` (PL area-share axis, 2 cases).

Tests (`tests/test_orchestration.py`, 7): provider metadata/registry
resolution, workflow topology, validate_node grid-missing diagnostic,
end-to-end workflow run on the synthetic fixture with evidence manifest
(artifacts land under the workdir), seed-fixed reproducibility (scenario
NPV mean bit-identical across runs), matrix run (2 cases, each its own
namespace, each ranking its own recommended policy) with matrix evidence
manifest, and invalid-matrix rejection. `pytest.importorskip("freshforge")`
guards the module so the core suite stays green without the extra.

Record count: 139 tests total; ruff, docs, build, twine green. freshforge
0.1.0a5 (commit `5bce95b`) installed editable locally; CI installs it from
the pinned git URL.
