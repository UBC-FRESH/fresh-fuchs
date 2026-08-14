# fresh-fuchs Change Log

Append-only project narrative, reverse-chronological.

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
