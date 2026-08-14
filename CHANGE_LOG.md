# fresh-fuchs Change Log

Append-only project narrative, reverse-chronological.

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

Phase 4 (outer policy layer) complete on `feature/p4-outer`; PR to `main`
pending.

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
