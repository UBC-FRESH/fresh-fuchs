# fresh-fuchs Change Log

Append-only project narrative, reverse-chronological.

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
