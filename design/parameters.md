# Parameter Reference

Consolidated reference of all user-adaptable and internal parameters in
`fresh-fuchs` (v0.1.0a1), grouped thematically. For each parameter: where it
is applied, its implemented default, unit, a short description, and its
implementation status.

**Status legend**

- *Implemented* — wired end-to-end; changing the value changes results.
- *Implemented, off by default* — functional but inactive under defaults.
- *Prepared* — record/field/API exists but is not yet consumed by the model.
- *Internal* — module-level constant; adapting requires a code change.

Source files are given as `module.py` paths relative to
`src/fresh_fuchs/`. Monetary values are CAD; the default economic surface is
anchored to the fresh-salvage economics calibration (reference only) and the
BC Interior Log Market Report Q4-2023.

---

## 1. Model instance and planning horizon

Configured via `InstanceConfig` (`instance/types.py`) and consumed by every
model build / LP solve. CLI exposure: `build-model`, `baseline-run`,
`economy-run`, `scenario-run`, `policy-grid`.

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| `model_name` | ws3 `ForestModel`, Woodstock file prefix | `"tsa29mini"` (synthetic builds: `"synthetic"`) | — | Name handed to ws3; prefixes the `.lan/.are/.yld/.act/.trn` files. | Implemented |
| `model_path` | Woodstock section output/input directory | `outputs/tsa29mini/ws3_woodstock_bootstrap_model` | — | Directory for the compiled Woodstock-format sections. | Implemented |
| `bundle_dir` | `instance/bundle.py`, species/fire loaders | `None` | — | Directory with `au_table.csv`, `curve_table.csv`, `curve_points_table.csv`; required for real-bundle builds. | Implemented |
| `fragments_path` | `instance/bundle.load_fragments` | `None` | — | Fragments shapefile with `TSA/AU/ORIGIN/SILV_STATE/F_AGE/IFM/AREA_HA/RETENTION` columns; required for real-bundle builds. | Implemented |
| `tsa_list` | bundle context build | `["29"]` | — | TSA identifiers read from the bundle tables. | Implemented |
| `base_year` | ws3 model calendar | `2026` | year | First year of period 1. | Implemented |
| `horizon` | all LPs, scenario generation | `30` (CLI/examples use 10–30; workflow nodes default 2) | periods | Number of LP periods. | Implemented |
| `period_length` | discounting, fire events, AAC rows | `10` | years/period | Years per period. | Implemented |
| `max_age` | yield curves, salvage operability upper bound | `300` | years | Patchworks-compatible maximum stand age. | Implemented |
| `min_harvest_age` | harvest operability floor | `60` | years | Minimum age for the harvest/replant actions to be operable. | Implemented |
| `max_harvest_age` | harvest operability ceiling | `300` | years | Maximum age for harvest operability. | Implemented |
| `ageclass_width` | `bundle.age_to_midpoint`, retention split | `10` | years | Initial fragment ages are bucketed to this class width's midpoint to keep the Model I LP tight (tsa29mini: 264 ages → 44 midpoints). | Implemented |
| `max_initial_age` | `woodstock.prepare_optimization` null-action window | `436` (tsa29mini max initial age; examples/workflow use 300) | years | Upper bound of the null action so stands older than `max_age` can still stand through the horizon. | Implemented |
| `workers` | ws3 problem build (baseline/NPV configs) | `1` | count | Solver threads for the Model I tree build. | Implemented |

## 2. Yields and species

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| Species classes (`SX`, `PL`, `FD`, `OT`) | everywhere species attribution is needed (`instance/species.py`) | — | — | Static primary species class per AU, derived from the AU table's CANFI code (`100→SX`, `204→PL`, `500→FD`, unknown→`OT`). | Implemented |
| Chapman–Richards `a`, `b`, `c`, `si_alpha` per species | `yields_multi.generate_synthetic_curve` | PL 420/0.012/1.8/1.0; SX 380/0.010/2.0/1.1; FD 500/0.008/2.2/1.2; OT 350/0.011/1.9/1.0 | m³/ha (a); 1/yr (b); — (c, si_alpha) | Synthetic fallback growth curve `V(age) = a·(1−e^(−b·age))^c`, calibrated at SI₅₀ = 25 m. Module constant `_CHAPMAN_RICHARDS_PARAMS`. | Internal (synthetic fallback path) |
| Site-index levels L/M/H | SI scaling of synthetic curves | L=15 m, M=25 m, H=35 m; reference 25 m | m at 50 yr | `SI_LEVEL_MAP` scales parameter `a` by `(SI/25)^si_alpha`. The bundle's `si_level` column exists but is not yet used for cross-species transfer in real runs. | Prepared (site-index transfer strategy) |
| Bundle species-proportion curves | `yields_multi.build_multi_species_yields_from_bundle_context` | none in tsa29mini | share | Strategy 1: total-volume × species proportion when the bundle provides `managed_species_prop_<species>` curves. tsa29mini does not populate them, so the synthetic fallback is the active path. | Prepared |
| Curve `max_age`, `step` | synthetic curve generation | 300 / 10 | years | Age range and decadal step of generated curves. | Implemented |
| Synthetic fixture curves (`synthetic.py`) | CI-safe example/test instance | peak 420 (managed)/350 (unmanaged) m³/ha; shape 80 (AU1)/110 (AU2) yr | m³/ha, yr | Saturating exponential curves `peak·(1−e^(−age/shape))` for the two-AU public-safe landscape; areas 100/50/80/200 ha at ages 75/35/95/125. | Internal |

## 3. Economic surface (green operations)

`EconomicSurface` and helpers (`economy/types.py`, `economy/cashflow.py`);
default factory `interior_surface()`. Used by the NPV objective and the fire
LP cash flows.

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| Sawlog prices by price group | LP objective via `net_revenue_per_m3` | SPF 127; Df-Larch 103; HemBal 120; Cedar 144; Other 90 | CAD/m³ | Q4-2023 BC Interior flat sawlog-basis prices (grade premia reserved). Peeler/pulpwood records exist (SPF 146/55 etc.) but only sawlog enters the v0.1.0a1 objective. Sawlog: Implemented; peeler/pulpwood grades: Prepared. |
| Price-group mapping | `price_group_for_species` | FD→Df-Larch; SX/PL→SPF; else Other | — | Attributes each species class to an interior price group. | Implemented |
| Harvest cost `cost_per_m3` | green + burned margins | 45 | CAD/m³ | Fresh-salvage total tree-to-truck plus road/admin/silviculture allocation (flagged assumption, CPI year 2024). | Implemented |
| Harvest-cost basis (`flat`/`fhops`) | `HarvestCostRecord.basis` | `flat` | — | Distinguishes recorded flat cost from fhops machine-rate estimate (§4). | Implemented (label) |
| `transport_per_m3` | net revenue | 30 | CAD/m³ | Green haul cost. | Implemented |
| `stumpage_per_m3` | net revenue | 15 | CAD/m³ | Green stumpage charge. | Implemented |
| Replant cost per ha by species | `harvest_cash_flow` when replant charging on | PL 2200; SX 2400; FD 2600; OT 2200 | CAD/ha | Planting + free-to-grow establishment (flagged assumptions). Not charged by default (silviculture already inside the $45/m³ harvest cost). | Implemented, off by default |
| `charge_replant_in_npv` | `EconomicSurface` flag | `False` | bool | Switch that charges per-ha replant cost in the LP objective. Flip on only with a silviculture-exclusive harvest cost to avoid double counting. | Implemented, off by default |
| Discount `annual_rate` | `DiscountRate.discount_factor`, all NPV terms | 0.03 | fraction/yr | Annual discount rate (3%). | Implemented |
| Discount `convention` | discount factor timing | `end_of_period` | — | `end_of_period` discounts cash flows at `t·L` years; `mid_period` at `(t−0.5)·L`. | Implemented |
| `product` (yield expression) | baseline/NPV/fire even-flow rows and objective volumes | `"totvol"` | — | ws3 yield component used for volume accounting. | Implemented |
| Land-base mask | all LPs (`BaselineConfig`/`NpvConfig`/`FireLpConfig.mask`) | `("?", "managed", "?", "?", "?")` | — | Restricts the LP to managed development types (theme 2 = IFM). | Implemented |

## 4. Harvest costing via fhops (alternative basis)

Optional module `economy/fhops_costing.py` (requires the `fhops` extra).
Provides a machine-rate clearcut cost as an alternative to the flat $45/m³;
it is **not** wired into any default surface.

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| `avg_stem_size_m3` | Lahrsen productivity prediction | 0.3 | m³/stem | Mean stem volume of the representative interior clearcut (flagged assumption). | Implemented (standalone estimator) |
| `volume_per_ha` | same | 180 | m³/ha | Merchantable volume per ha. | Implemented (standalone estimator) |
| `stem_density_per_ha` | same | 2000 | stems/ha | Stand density. | Implemented (standalone estimator) |
| `ground_slope_pct` | same | 25 | % | Average ground slope. | Implemented (standalone estimator) |
| `role` | fhops machine-rate table lookup | `feller_buncher` | — | Machine role; single-pass felling is a lower bound of tree-to-truck cost. | Implemented (standalone estimator) |
| `rental_rate_smh` | cost composition | `None` (compose from table) | $/SMH | Explicit rental rate override. | Implemented (standalone estimator) |
| `utilisation` | cost composition | machine-rate default | fraction (0,1] | Realised machine utilisation override. | Implemented (standalone estimator) |
| `cpi_year` | CPI adjustment | 2024 | year | Base year of the fhops cost (fhops `TARGET_YEAR`). | Implemented (standalone estimator) |

## 5. Fire dynamics

Module `scenario/fire.py`. Constants mirror the fresh-salvage reference
implementation (parity-tested, no import). Rationale, LP encoding,
validation evidence, limitations, and the species-specific
parameterization roadmap are documented in
[fire-regime.md](fire-regime.md).

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| MFRI per BEC zone | annual burn rate `R = 1/MFRI`, period burn probability `1−(1−R)^L` | SBPS 100, IDF 200, MS 150, ESSF 200, ICH 250, SBS 125 | years | Mean fire return interval ladder (`MFRI_YEARS_BY_ZONE`). Only SBPS/IDF occur in tsa29mini; unknown zones raise `UnknownBurnRateError`. | Internal |
| Burn severity → salvageable fraction | salvageable volume = severity × burn influx | Unburned 0.0; Low 0.30; Moderate 0.60; High 0.85 | fraction | `SEVERITY_TO_BURNED_FRAC` ladder. | Internal |
| Default severity | scenario generation default tier | `"Moderate"` (0.60) | — | tsa29mini has no burn-severity polygons, so severity is a scenario choice. Exposed as `ScenarioGenerationParams.severity` / `DisturbanceScenario.severity`. | Implemented |
| Burned-volume decay rate | burned pool balance `B[t]=(B[t−1]+in−S[t])·decay` | 0.85 | fraction/yr retention | Annual retention of unsalvaged burned volume (`DEFAULT_BURNED_DECAY_RATE`). | Internal |
| Dynamics ordering | cohort simulation | harvest → fire → salvage → decay | — | Fixed within-timestep ordering contract. | Internal (fixed) |

## 6. Monte-Carlo scenario generation

`ScenarioGenerationParams`, `UncertaintyVector`, `ParameterDistribution`
(`scenario/distributions.py`, `scenario/records.py`). Exposed via
`scenario-run` / `policy-grid` CLIs and orchestration nodes.

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| `n_scenarios` | catalogue size, probability weights `1/n` | CLI 10; workflow node 3 | count | Number of MC fire realizations. | Implemented |
| `master_seed` | scenario seeds (`seed_i = master_seed + i`) | 42 | — | Master seed; draws are bit-stable under a fixed master seed. | Implemented |
| `zone_burn_rates` | per-period fire events per BEC zone | derived from MFRI (SBPS 0.01, IDF 0.005); synthetic fixture same values | fraction/yr | Deterministic base annual burn rates before the scenario multiplier. | Implemented |
| Burn-rate multiplier distribution | FIRE_BURN_RATE dimension | Gaussian mean 1.0, std 0.2 (CLI/workflow); std 0.3 in `examples/replant_lp_example.py` | multiplier | Scenario-wide multiplier on every zone burn rate. Distribution family/parameters are chosen at call sites (fixed/gaussian/empirical families available). | Implemented |
| `price_factor` distribution | PRICE dimension; multiplies LP cash flows | FIXED value 1.0 | multiplier | Scenario price realization. The multiplier is applied in the fire-LP objective, but the default vector keeps it neutral; richer price uncertainty is future work. | Implemented (neutral by default) |
| Distribution family fields (`value`, `mean`, `std`, `samples`) | `ParameterDistribution` | — | varies | fixed/gaussian/empirical registry; empirical draws with replacement, optionally via nemora (`nemora_sample_distribution`). | Implemented |
| `severity` (catalogue-wide) | all events of the catalogue | Moderate | — | Severity tier applied to every event (see §5). | Implemented |

## 7. Inner LP configuration (fire-aware NPV)

`FireLpConfig` (`scenario/fire_lp.py`), `NpvConfig`, `BaselineConfig`
(`economy/types.py`, `instance/types.py`).

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| `sense` | LP objective direction | maximize | — | All current problems maximize. | Implemented |
| `flow_coefficient` | even-flow band on post-fire green harvest volume (AAC proxy) | 0.05 | fraction | Per-period harvest volume constrained within ±5% of period-1 volume. | Implemented |
| `action_codes` | actions enabled in the LP tree | baseline/NPV: `null, harvest`; fire LP: `null, harvest, salvage` (+ policy replant codes) | — | Action set offered to the solver. | Implemented |
| `min_salvage_age` | salvage operability floor (`add_salvage_action`) | 60 | years | Salvage of regenerating stands is not modelled; also bounds Model I tree growth. | Implemented |
| Salvage operability pruning | `apply_salvage_operability` | salvage closed in zero-burn periods | — | Closes the salvage branch where the scenario does not burn a zone. | Implemented |
| Solver | ws3 opt backend | HiGHS (ws3 default) | — | Recorded in run-record environment provenance; not switchable from fresh-fuchs. | Internal |

## 8. Outer policy layer

`PolicyRecord`, `CompositionTarget`, `HarvestPolicy` (`outer/records.py`),
row encoding `outer/policy.py`, grid `outer/grid.py`.

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| Composition `species` | composition rows per target | required | — | Target species group (`SpeciesClass`). | Implemented |
| Composition `target_share` | replanted-area (or harvested-area) share pinned to `[share−tol, share+tol]` | required | fraction [0,1] | Landscape composition target per period. | Implemented |
| Composition `tolerance` | half-width of the binding band | grid axis/points default 0.05 | fraction | Tolerance around the target share. | Implemented |
| `n_free_periods` | three-phase transition schedule | 0 | periods | Periods 1..n unconstrained (avoids infeasibility far from target). | Implemented |
| `n_ramp_periods` | three-phase transition schedule | 0 | periods | Tolerance decays linearly 1.0 → `tolerance` over these periods. | Implemented |
| Harvest policy mode | constraint encoding | — | — | `aac_proxy` (volume interval row) or `rotation_constraints` (operability windows). | Implemented |
| `aac_level_m3_per_yr` | AAC proxy row: per-period volume ≈ level × period_length | required (>0 in aac_proxy mode) | m³/yr | Policy AAC level. | Implemented |
| `aac_tolerance` | AAC proxy interval half-width | 0.0 | fraction | ± tolerance on `level × period_length`. | Implemented |
| `rotation_floor` / `rotation_ceiling` | per-species harvest operability windows (`apply_rotation_constraints`) | empty dicts | years | Rotation-age bounds per species; floor ≤ ceiling validated. | Implemented |
| `replant_actions` | policy linkage to replant actions; composition attribution switches to replanted-area shares | `None` | — | Tuple like `("harvest_SX", "harvest_FD")`; when set, the pipeline registers the corresponding replant actions. | Implemented |
| Grid `composition_axes.values` / `composition_points` | outer search space (`PolicyGrid.expand`) | required axes or points | fractions | Cartesian product of candidate shares, or explicit points (points take precedence). | Implemented |
| Grid `composition_tolerance` | default tolerance for points mode | 0.05 | fraction | Overridable per point via a `tolerance` key (also `n_free_periods`/`n_ramp_periods`). | Implemented |
| Grid harvest axis `values`, `species`, `ceiling` | candidate AAC levels or rotation ages | required when axis present | m³/yr or years | One harvest axis per grid; `ceiling=True` makes rotation values ceilings. Axis tolerance default 0.05. | Implemented |
| `include_unconstrained` | prepends the unconstrained baseline policy | `False` | bool | Adds a no-constraint reference point first. | Implemented |

## 9. Risk metrics and policy ranking

`outer/risk.py`, `outer/ranking.py`; CLI `policy-rank`, workflow node
`policy_rank`.

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| `alpha` (VaR/CVaR tail) | empirical VaR/CVaR, Gaussian comparison, ranking | 0.95 | probability | Tail probability: CVaR is the mean of the worst `1−alpha` mass. | Implemented |
| `shortfall_threshold` | shortfall probability P[NPV < t] | `None` (metric omitted) | CAD | Optional downside threshold. | Implemented |
| Volatility `ddof` | sample standard deviation (tie-breaker) | 1 | — | Bessel-corrected NPV volatility. | Internal |
| Ranking criterion | `rank_policies` / `--criterion` | `expected_npv_cvar` | — | Lexicographic E[NPV] then CVaR; alternative `mean_cvar`. | Implemented |
| Ranking `weight` | MEAN_CVAR score `w·E[NPV]+(1−w)·CVaR` | 0.5 when MEAN_CVAR | fraction | Weight of expected NPV in the weighted score. | Implemented |
| Gaussian tail comparison | `gaussian_tail_metrics` | fitted to sample moments | CAD | Explicitly labeled comparison, never the reported metric. | Implemented (diagnostic) |

## 10. Orchestration and performance

`orchestration/workflow.py` (freshforge provider), `orchestration/matrix.py`,
`outer/grid.run_grid`, `scenario/pipeline.run_scenario_pipeline`, examples.

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| `source` (build_model node) | model build | `synthetic` | — | Only the synthetic fixture is supported by the provider; real bundles go through the CLI. Real-bundle source: Prepared. |
| Node `horizon` | workflow nodes | 2 | periods | CI-safe default in templates (`examples/fuchs_workflow_template.yaml`). | Implemented |
| Node `n_scenarios`, `master_seed` | scenario_run / policy_grid nodes | 3 / 42 | count / — | Workflow-node scenario controls (see §6 for semantics). | Implemented |
| Node burn-rate vector | `_scenario_params` | Gaussian mean 1.0 std 0.2, fixed price 1.0 | multiplier | Hardcoded inside the provider (not a node parameter yet). | Internal |
| `out_dir` | run/grid/rank outputs | `scenario_run` / `policy_grid` / `policy_rank` relative to workdir | — | Output directories for run records, summaries, reports. | Implemented |
| `n_workers` (scenarios) | process-pool scenario solving | 1 | count | Spawn-based pool; parallel results bit-match sequential runs. | Implemented |
| `scenario_workers`, `policy_workers` | grid evaluation | 1 / 1 | count | Nested parallelism: policies × scenarios. | Implemented |
| Matrix axes (`examples/fuchs_matrix.yaml`) | freshforge matrix expansion | PL share 0.85/0.90 sweep | fraction | Template variables substituted into workflow nodes. | Implemented |
| Stub commands | CLI `inner-run`, `outer-run`, `pipeline-run` | — | — | Phase placeholders echoing "not implemented". | Prepared (stubs) |

## 11. Reporting

`reports/replant_summary.qmd`, `outer/report.py` (ranking/report writing).

| Parameter | Where applied | Default | Unit | Description | Status |
|-----------|---------------|---------|------|-------------|--------|
| Quarto report parameters (`replant_species`, grid summary path) | `reports/replant_summary.qmd` | — | — | Parameterized species-specific LP output report (period tables, OT mixtures, NPV chart). | Implemented |
| Trade-off plot availability | `policy-rank` PNG export | matplotlib optional | — | Report degrades gracefully without matplotlib. | Implemented |

---

### Cross-cutting notes

- **Provenance**: every economic constant carries a `Provenance` record
  (`source`, `as_of`, `units`, `basis`, `assumption`); scenario catalogues,
  pipeline runs, grid runs, and rankings embed provenance and environment
  snapshots in their JSON records.
- **Known call-site inconsistencies to keep in mind when adapting**:
  burn-multiplier std is 0.2 in the CLI/workflow but 0.3 in
  `examples/replant_lp_example.py`; `max_initial_age` is 436 in the real-bundle
  CLI commands but 300 in examples/workflow nodes (synthetic fixture).
- **Deliberately out of scope for v0.1.0a1** (recorded in docstrings): log-grade
  premia in the objective, transition-dependent replant costs, burned-pool
  stock tracking in the LP, binaries/thresholding of decision variables.
