# fresh-fuchs Release Notes

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
