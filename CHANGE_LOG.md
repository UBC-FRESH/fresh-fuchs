# fresh-fuchs Change Log

Append-only project narrative, reverse-chronological.

## Unreleased — species-switching replant (feature/species-switching-replant)

Species-switching replant transitions: harvest any species and replant
with a different species, driven by policy-level composition targets.

Phase 1 — Multi-species yield curve framework:
- `instance/yields_multi.py`: `YieldCurve` dataclass, `MultiSpeciesYieldTable`,
  `generate_synthetic_curve()` (Chapman-Richards with species-specific params
  and SI-level scaling), `build_multi_species_yields()` (tries bundle
  species-proportion curves first, falls back to synthetic).
- `tests/test_yields_multi.py`: 21 tests.

Phase 2 — Replant action registration:
- `instance/replant.py`: `add_replant_actions()` registers per-species
  harvest actions (`harvest_SX`, `harvest_PL`, `harvest_FD`) with per-AU
  target masks; `add_replant_salvage_actions()` for salvage → replant;
  `replant_au_id()` computes replant AU codes (e.g. `1001` → `1001-SX`).
- `instance/woodstock.py`: `_landscape_section()` and `write_woodstock_files()`
  extended to add replant AU codes and yield curves; `prepare_optimization()`
  accepts `replant_species` parameter.
- `tests/test_replant_actions.py`: 23 tests (action registration, operability,
  transitions, apply, salvage, backward compatibility).
- `design/species-switching-replant.md`: Phase 1 and 2 marked complete;
  `_REPLACE` limitation documented (ws3 hack doesn't support string
  concatenation), per-AU mask approach adopted.
- `design/yield-curve-framework.md`: data dependency flag, grouping
  variables, strategy, upgrade path.

Phase 3 — LP wiring (objective + even-flow):
- `instance/replant.py`: added `target_species_from_acode()` helper to
  extract target species from replant action codes (e.g. `"harvest_SX"`
  → `SpeciesClass.SPRUCE`).
- `scenario/fire_lp.py`: `path_fire_steps` recognizes `harvest_*` and
  `salvage_*` as harvest/salvage actions; `_burn_prob_for_dtk` strips
  replant AU suffixes for zone lookup; `path_fire_steps` handles missing
  yield curves on replant AUs (treats as zero volume); `_compile_path_z`
  charges source-species timber revenue plus target-species replant cost;
  `_compile_path_caa` aggregates volume across all harvest actions;
  `solve_fire_lp` accepts `replant_action_codes` to sum replant volumes
  into the harvest totals.
- `tests/test_replant_lp.py`: 15 tests (acode parsing, survival reset,
  LP solve, replant cost impact, even-flow aggregation, backward compat).
- `examples/replant_lp_example.py`: end-to-end demo with synthetic data.

Phase 4 — Replant composition constraints:
- `outer/records.py`: `CompositionTarget` gains `n_free_periods` and
  `n_ramp_periods` (three-phase transition: free → ramp → binding);
  `PolicyRecord` gains `replant_actions: tuple[str, ...] | None` to
  control whether composition binds on target species (replant area) or
  source species (existing behavior).
- `outer/policy.py`: `_harvest_steps` yields acode and accepts
  `replant_actions` filter; `_resolve_species` determines species from
  action code or DTK; `_share_by_period` computes per-period effective
  tolerance from the three-phase schedule; `_composition_coeff` is
  period-aware with variable share; `policy_coeff_funcs` accepts
  `periods` and passes `replant_actions` through.
- `outer/grid.py`: `CompositionGridAxis` gains `n_free_periods` and
  `n_ramp_periods`, passed through to `CompositionTarget` in axis and
  points modes.
- `instance/baseline.py`, `scenario/fire_lp.py`: callers of
  `policy_coeff_funcs` pass `periods=model.periods`.
- `tests/test_replant_composition.py`: 16 tests (share_by_period,
  resolve_species, composition binding, three-phase transition,
  backward compat, grid expansion).

Known limitation: ws3 `compile_problem` silently drops actions at 7+
action codes (observed on synthetic 2-AU instance). Replant tests
use 2 species (SX + FD, 5 actions) to avoid this; 4-species tests
deferred to ws3 fix. Documented in `design/species-switching-replant.md`.

All 223 tests pass; lint clean.

## 0.1.0a1 — 2026-08-14

Phase 5 (orchestration, validation, calibration, release) complete on
`feature/p5-release`; version bumped to `0.1.0a1`.

- P5.1 Freshforge integration (`orchestration/`): `FuchsOrchestrationProvider`
  (freshforge `Provider` protocol, id `fuchs.orchestration`) with thin node
  types `build_model` / `scenario_run` / `policy_grid` / `policy_rank`
  wrapping the Python APIs; `fuchs_workflow_spec` builds the
  build_model -> scenario_run -> policy_grid -> policy_rank chain;
  `run_fuchs_workflow` / `run_fuchs_matrix` execute with the FUCHS registry
  and write `workflow_run_evidence_manifest` / `matrix_run_evidence_manifest`.
  `instance/synthetic.py` moves the public-safe synthetic instance into the
  package so the whole pipeline is reproducible from the provider without
  private data. freshforge pinned to commit `5bce95b` (the durable-evidence
  commit; the v0.1.0a5 tag predates `evidence.py`) as an `orchestration`
  extra and in `dev`; `freshforge.providers` entry point registered.
  Examples: `fuchs_workflow_template.yaml` + `fuchs_matrix.yaml` (PL
  area-share sweep, CI-safe). 7 tests, `importorskip`-guarded.
- P5.2 Validation (`planning/validation-report.md` Phase 5 section):
  consolidated deterministic anchors (managed land base 35,083.0 ha; 30-period
  even-flow mean harvest 35,451 m3/yr, +0.2% midpoint aging), fire-free vs
  deterministic parity (NPV-max anchor bit-level: 33,624.77 m3/yr,
  104,462.175 ha), cost-vs-volume baseline comparison, harvest-area
  discrepancy status (understood + bounded +3.8%, documented caveat), and a
  MC convergence study (`tests/test_mc_convergence.py`, synthetic n=5..320):
  CVaR(0.95) stable to < 0.15% by n=40, E[NPV] to < 0.17%; production
  catalogue guidance n ~ 80.
- P5.3 Calibration record (`planning/economics-calibration.md`): every
  economic constant with provenance; fresh-salvage cross-checks verified
  against the live surface (sawlog-basis salvage margin -11.95, transition-mix
  margin -21.31, green SPF 146/127/55, burned costs 56.25/38, discount 0.65,
  decay 0.85); subsidy/FESBC anchors reference-only (unsubsidized regime).
- P5.4 Documentation and release: README, Sphinx guides (quickstart, model
  semantics, CLI reference, architecture, development, installation) updated
  to v0.1.0a1; examples documented; CHANGE_LOG/RELEASE_NOTES/ROADMAP updated;
  version bumped to `0.1.0a1` (tag `v0.1.0a1` created on `main` after the
  PR merges).
- Full gate: ruff, 141 tests, sphinx docs, build, twine all green on both
  ws3 1.0.5 (PyPI) and 1.1.0a4 (editable).

## 0.1.0a1-pre — 2026-08-14

Phase 3 (full-MC scenario engine) complete on `feature/p3-scenario`; PR
[#23](https://github.com/UBC-FRESH/fresh-fuchs/pull/23) merged to `main`.

- P3.1 Scenario records and catalogue: typed `DisturbanceScenario` /
  `FireEvent` records, `ScenarioGenerationParams` with
  per-dimension `ParameterDistribution` (Gaussian/fixed, with provenance),
  seed-fixed Monte-Carlo catalogue generation, `scenario/records.py`.
- P3.2 Fire model: `scenario/fire.py` — per-zone `MFRI_YEARS_BY_ZONE`
  (SBPS 100 / IDF 200 / MS 150 / ESSF 200 / ICH 250 / SBS 125), annual burn
  rate 1/MFRI, severity ladder {Unburned 0, Low 0.30, Moderate 0.60,
  High 0.85}, ordering harvest -> fire -> salvage -> decay, default
  Moderate. Zone/stratum lookup fails fast on unknown names.
- P3.3 Scenario operability: `apply_salvage_operability` closes fire-free
  periods with an empty salvage age window so the Model I tree stays
  minimal; lookups by zone name keyed from the AU table stratum prefix;
  98 tests green. (Closed periods use `(0, -1)` rather than a `None`
  sentinel for PyPI ws3 1.0.5 compatibility.)
- P3.4 Fire encoding in the inner LP (`scenario/fire_lp.py`): fire as
  path-dependent coefficients — survival `Pi(1-p)` since regeneration,
  green volume `Y(age)*survival`, burn influx `p*exposed`, salvageable
  `severity_frac*influx`; `salvage` is a real Model I action with age-0
  regeneration and a free LP decision (default negative SPF margin -11.95
  -> no salvage; positive margins exercise the mechanism); salvage
  feasibility row `salvage_vol - salvageable_vol <= 0`; `min_salvage_age`
  (default 60) excludes regenerating stands and bounds Model I tree growth.
  Salvage area reported from the same leaf accounting as salvage volume.
  Real-bundle scaling: h=20 ~377k vars (~6 min), h=24+ tens of minutes per
  scenario under an all-periods burn worst case; fire-free h=30 ~4-14 min
  and bit-level reproduces the deterministic baseline.
- P3.5 Scenario -> LP pipeline (`scenario/pipeline.py`): fresh model per
  scenario, salvage action + operability, fire LP build/solve/apply, and a
  run record with per-period schedule, total NPV, status, and environment
  provenance (JSON + CSVs). Process-pool parallelism via the spawn start
  method (the parent is multi-threaded; forking was unsafe); parallel
  results bit-match sequential. CLI `scenario-run` wired end-to-end; sample
  run at `outputs/tsa29mini/scenario_run_h8/` (gitignored).
- P3.6 Acceptance (`tests/test_phase3_acceptance.py`, 3 tests):
  fire-free through the full pipeline reproduces the volume-max baseline
  exactly (synthetic); burn multiplier 0.0/0.5/1.0/2.0 -> strictly
  decreasing total NPV (synthetic test + real h=8 recorded: NPV
  23.35M/21.56M/19.90M/16.94M); seed-fixed pipeline runs bit-stable.
  Real bundle h=30 fire-free reproduces the NPV-max anchor exactly
  (33,624.77 m3/yr, 104,462.175 ha).
- Full gate: ruff, 98 tests, sphinx docs, build, twine all green.
  `ROADMAP.md` P3 complete; validation-report Phase 3 entry appended.

## 0.1.0a1-pre — 2026-08-14

Phase 4 (outer policy layer) complete on `feature/p4-outer`; PR
[#30](https://github.com/UBC-FRESH/fresh-fuchs/pull/30) merged to `main`.

- P4.1 Policy records and LP constraints (`outer/records.py`,
  `outer/policy.py`): `CompositionTarget`, `HarvestPolicyMode` (AAC /
  rotation constraints), `HarvestPolicy`, `PolicyRecord` (harvest policy
  optional — composition-only policies allowed); composition rows
  (target ± tolerance on area share by species) and AAC/rotation rows
  (age-window-based, compatible with PyPI ws3 1.0.5) added to the
  even-flow and fire LPs; policies folded through `run_scenario_lp` /
  `run_scenario_pipeline` (parallel payload 8th element). Infeasible
  policies surface clean diagnostics; rotation floor 140 skips PL
  entirely (test: baseline harvests young PL, constrained never does).
- P4.2 Grid search driver (`outer/grid.py`): `CompositionGridAxis`,
  `HarvestGridAxis`, `PolicyGrid` (cross-product expansion plus an
  optional unconstrained baseline), `run_grid` (nested spawn policy pool)
  with failed-point capture (`status="failed"`, grid completes), typed
  `GridRunRecord` + `write_grid_record` (`grid_summary.csv/json`), CLI
  `policy-grid`, `examples/policy-grid.tsa29mini.json`. Real-bundle smoke
  (h=6, 2 scenarios): unconstrained 21.19M NPV / 57,361 m3/yr -> PL 85%
  11.38M / 22,691 -> PL 90% 10.32M / 18,951; PL 85% + AAC 50,000 recorded
  as failed (infeasible).
- P4.3 Risk metrics (`outer/risk.py`): `expected_npv`, `npv_volatility`,
  `value_at_risk` (inverted-CDF quantile), `conditional_value_at_risk`
  (mean of the worst tail), `shortfall_probability`, and a Gaussian
  comparison (A&S 26.2.23 + Newton on `math.erf`, no scipy);
  `RiskReport`/`RiskMetrics` records, `risk_report`,
  `risk_reports_from_grid`.
- P4.4 Ranking and report (`outer/ranking.py`, `outer/report.py`):
  `RankingCriterion.E_NPV_CVAR` (lexicographic E[NPV] then CVaR) and
  `MEAN_CVAR` (weighted score; 0/1 recover pure-CVaR / pure-E), volatility
  tie-break, `PolicyRanking` with recommended (rank-1) policy; `build_report`
  with coarse-vs-fine grid-resolution `SensitivityResult`; `write_report`
  (`ranking.csv/json`, `report.json`, `tradeoff.png` only when matplotlib
  is importable); `rank_from_grid_summary` re-derives rankings from a grid
  record without re-solving; CLI `policy-rank`. Real-bundle ranking smoke:
  unconstrained 21.19M -> PL 85% 11.38M -> PL 90% 10.32M.
- P4.5 Acceptance (`tests/test_phase4_acceptance.py`, 4 tests):
  synthetic end-to-end grid -> full-MC -> risk -> ranking is seed-fixed
  reproducible (NPV samples and ranking bit-identical across runs);
  tightening PL composition lowers both E[NPV] and CVaR monotonically
  (CVaR <= E[NPV] for every policy) with the unconstrained baseline
  recommended; pure-CVaR ranking matches a direct CVaR sort; grid records
  and report artifacts written end-to-end.
- Full gate: ruff, 132 tests, sphinx docs, build, twine all green on both
  ws3 1.0.5 (PyPI) and 1.1.0a4 (editable). `ROADMAP.md` P4 complete;
  validation-report Phase 4 entry appended.

## 0.1.0a1-pre — 2026-08-14

Phase 2 (economic valuation layer) complete on `feature/p2-economy`; PR to
`main` pending.

- P2.1 Typed economic surface: `economy/` Pydantic records (`Provenance`,
  `PriceRecord` by product/price group, `HarvestCostRecord`,
  `ReplantingCostRecord`, `SalvageRecord`, `DiscountRate`, `EconomicSurface`,
  `NpvConfig`), every constant carrying provenance. `interior_surface()`
  composes the default TSA29 surface anchored to the fresh-salvage economics
  calibration (reference only): SPF sawlog $127/m3, harvest $45/m3
  (incl. silviculture allocation), transport $30/$38, stumpage $15/m3 green /
  0.25 x price burned, burned-price discount 0.65, +25% salvage cost premium,
  decay 0.85/yr, discount 3%, downgrade-only grade transition. Coast price
  matrix reserved as a template (not imported).
- P2.2 Harvest cost via fhops: `HarvestCostModel` (single feller-buncher pass
  $7.15/m3; 4-pass system $23.22/m3 for the default interior stand), optional
  `fhops` extra with explicit diagnostic. fhops 1.0.0 installed editable.
- P2.3 Replanting cost: flat per-ha by species (PL 2200 / SX 2400 / FD 2600 /
  OT 2200, assumption-flagged); NOT charged in the LP by default
  (`charge_replant_in_npv`) because $45/m3 carries the silviculture
  allocation — avoids double-count.
- P2.4 Salvage economics: cash-flow functions + anchor tests — SPF
  sawlog-basis margin -11.95 (calibration approx -11.7), SPF transition-mix
  -21.31 within the fresh-salvage -21..-24 $/m3 band (DF sawlog-basis -27.55
  recorded with caveat).
- P2.5 NPV objective in the inner LP: `economy/npv.py` (per-prescription
  discounted cash flow; even-flow band stays on harvest volume), CLI
  `economy-run`. Cross-validation: zero discount + no price differential
  reproduces the volume-max schedule exactly; 3% + no differential within 1%.
  Real bundle: NPV-max 33,625 m3/yr over 104,462 ha (96.6 m3/ha) vs
  volume-max 35,451 m3/yr over 94,890 ha (112.1 m3/ha) — divergence is the
  first-order effect of species price differentials + discounting.
- 54 tests passing (25 new for P2), docs updated, validation-report Phase 2
  section recorded.
- CI fix: ws3 1.0.5 (PyPI) requires `pulp` for the solver status path even
  under HiGHS; added `pulp` to the core dependencies (pre-existing CI
  failure on `main`, not introduced by P2).

## 0.1.0a1-pre — 2026-08-13

Phase 1 (instance and model integration) complete; branch
`feature/p1-instance-model` merged to `main`:

- P1.1 Bundle -> ws3 model bridge: `instance/{types,bundle,woodstock,
  baseline}.py`, `build-model` and `baseline-run` CLI, hermetic synthetic
  tests, docs. Validated on the real tsa29mini bundle (21 AUs, 108 curves,
  73 development types, managed land base 35,083.015 ha after retention
  split). Maintainer direction applied: exactly five themes (no LU/land-use
  theme, asserted in `bootstrap_model`) and initial ages smashed to 10-year
  ageclass midpoints (264 -> 37 distinct ages) to keep the Model I LP tight.
- P1.2 Deterministic baseline anchors recorded: 30-period volume-max even-flow
  LP 35,451 m3/yr vs ~35,381 m3/yr raw-age reference (+0.2%, PASS); oldest-
  first heuristic 91,718 m3/yr; even-flow verified within the 5% band. GitHub
  remote created (UBC-FRESH/fresh-fuchs); parent issue #1 + child issues
  #2..#6 opened; P1.1/P1.2 closed.
- P1.3 Species dimension (re-scoped): the mini bundle has no species-proportion
  curves (all 108 curves treated/untreated; no fragment species attribute), so
  species enters as a static primary-species class per AU from the AU table's
  `canfi_species` code (`instance/species.py`, `instance/composition.py`,
  `species-composition` CLI). Managed composition FD 57.6% / PL 42.0% / SX 0.4%,
  reconciling to the 35,083.0 ha anchor; the ws3 model stays five-theme.
- P1.4 Harvest-area discrepancy vs Patchworks investigated and closed: ws3 LP
  harvests +31.9% area at -21% volume/ha vs Patchworks; mechanism confirmed
  as a formulation artifact of the volume even-flow band (the LP harvests
  sub-merchantable stands, down to ~36 m3/ha, to hold the band; band
  sensitivity 0.0/0.05/0.10 -> 97,026/94,890/93,324 ha). Yield-strata ruled
  out; mitigation directions recorded; caveat carried (no Patchworks solve
  logs in the bundle). No model-side fix in P1.
- Phase closeout: 29 hermetic tests (ruff + sphinx -W + build + twine green),
  `CHANGE_LOG.md`/`ROADMAP.md`/planning/validation-report synchronized,
  PR merged to `main`, parent issue #1 closed.

## 0.1.0a0 — 2026-08-13

Phase 0 (skeleton scaffold) complete:

- Governance scaffold complete (`README.md`, `ROADMAP.md`, `AGENTS.md`,
  `LICENSE`, `CITATION.cff`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`).
- Package and CLI skeleton: `pyproject.toml` (deps `ws3`/`highspy`/PyPI;
  domain packages as source-dependency extras where published), module
  stubs `fresh_fuchs.{instance,economy,scenario,inner,outer,orchestration}`,
  Typer CLI with stub commands `build-model`, `scenario-run`, `inner-run`,
  `outer-run`, `pipeline-run`.
- Sphinx docs skeleton (7 pages) and GitHub Actions CI (ruff/pytest/
  sphinx/build/twine on 3.11+3.12), docs Pages, and release-artifact
  workflows.
- All Phase-0 acceptance checks green: ruff, pytest (6 passed),
  sphinx-build -W, build, twine check.

Prior scaffold commit recorded the master plan:
`planning/v0.1.0a1-plan.md` (Phase 0..5 to `v0.1.0a1`), locked design
decisions, and validation anchors.
