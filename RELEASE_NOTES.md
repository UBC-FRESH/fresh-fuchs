# fresh-fuchs Release Notes

## 0.2.0a1 — 2026-08-28

Species-switching replant (Phase 6, issue
[#42](https://github.com/UBC-FRESH/fresh-fuchs/issues/42)): the inner LP
now chooses **what to replant**, not just when to harvest.

- **Replant actions**: per-species harvest and salvage actions
  (`harvest_PL`, `harvest_SX`, `harvest_FD`, `harvest_OT`; `salvage_*`
  likewise) transition a stand to age 0 of a replant development type
  carrying the target species' yield curve. Default policy
  (`replant_actions=None`) reproduces v0.1.0a2 behaviour exactly
  (real-instance anchor 35,451 m3/yr even-flow mean reproduced).
- **Economics**: source-species timber revenue plus target-species
  replant cost (per-ha, `charge_replant_in_npv`); salvage replant carries
  the burned-price margin plus replant cost.
- **Composition policy on replant area**: outer composition targets can
  bind on replant action area by target species, with a three-phase
  free → ramp → binding tolerance schedule
  (`CompositionTarget.n_free_periods` / `n_ramp_periods`) to avoid
  early-horizon infeasibility.
- **Real TIPSY curves**: 63 BatchTIPSY pure-plantation curves (21 AUs ×
  PL/SW/FD) generated under a self-contained Linux+Wine lane and loaded
  via `load_replant_curves_from_btc` + the `replant_curves` overlay in
  `build_multi_species_yields()` (synthetic fallback with diagnostic).
  Curves live in the `femic-tsa29mini-instance` dataset repo
  (`feature/replant-tipsy-curves`), never vendored here.
- **Outputs + CLI**: per-species harvest area/volume and replant area in
  scenario records; `build-model --replant-species` (+ BTC curve paths),
  `policy-grid --replant-species` / grid JSON `replant_actions`;
  parameterized Quarto report (`reports/replant_summary.qmd`).
- **Retired limitation**: the "ws3 drops actions at 7+ action counts"
  caveat was a fresh-fuchs bug (missing replant-DTK pre-creation), fixed
  in P6.2; 4-species policies verified on ws3 1.0.5 and 1.1.0a5 with
  regression tests.
- Evidence: `planning/replant-real-curve-validation.md` (real-instance
  composition-constrained runs), `design/species-switching-replant.md`.

## 0.1.0a1 — 2026-08-14

First public alpha. The end-to-end, reproducible, validated prototype:

- **End-to-end pipeline** on the tsa29mini instance (and on a public-safe
  synthetic instance in CI): extended ws3 model build -> full-MC fire
  scenarios -> per-scenario inner LP (NPV max) -> NPV distributions ->
  policy grid search -> CVaR-based ranking. Every step is runnable from the
  CLI (`fresh-fuchs build-model`, `scenario-run`, `policy-grid`,
  `policy-rank`) and from the Python API.
- **Inner LP (Phase 2-3)**: Model I NPV-max LP with even flow, salvage
  feasibility, and fire encoded as path-dependent coefficients (MFRI-by-zone
  burn rates, severity ladder, decay 0.85); salvage is a real action with a
  negative default margin.
- **Outer policy layer (Phase 4)**: species-composition targets and
  AAC/rotation policy folded into the inner LP; grid search with
  infeasible-point capture; risk metrics (E[NPV], VaR, CVaR, shortfall,
  Gaussian comparison); reproducible ranking with a recommended policy and
  grid-resolution sensitivity.
- **Orchestration (Phase 5)**: freshforge workflows/matrices with evidence
  manifests (`fuchs.orchestration` provider; `orchestration` extra).
- **Validation + calibration**: deterministic anchors (managed land base
  35,083.0 ha; 30-period even-flow mean harvest 35,451 m3/yr, +0.2%), fire-
  free vs deterministic parity (NPV-max anchor bit-level), MC convergence of
  CVaR, and `planning/economics-calibration.md` with fresh-salvage
  cross-checks.
- **Governance/docs/CI**: README, Sphinx guides, examples, CHANGE_LOG,
  CI (ruff/pytest/sphinx/build/twine), public-safe synthetic fixtures.

Known limitations are recorded in `docs/model_semantics.rst` and
`planning/validation-report.md` (full-foresight optimism, interior price
provenance, harvest-area discrepancy vs Patchworks, unsubsidized salvage).

## 0.1.0a0 — 2026-08-13

Initial repository scaffold and master plan. No functional pipeline yet.
