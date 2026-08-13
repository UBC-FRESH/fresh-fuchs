# fresh-fuchs Change Log

Append-only project narrative, reverse-chronological.

## 0.1.0a0 — 2026-08-13

Initial scaffold for the FUCHS project (`fresh-fuchs`):

- Created the repository at `planning/v0.1.0a1-plan.md` master plan
  (Phase 0..5 to the `v0.1.0a1` release): full-MC outer policy problem
  (species-composition targets, AAC/rotation policy, CVaR evaluation)
  wrapped around a per-scenario Model I inner LP (NPV-max harvest +
  replant scheduling), reusing `ws3`, `femic`, `fhops`, `nemora`,
  `freshforge`, and `fresh-salvage` calibration anchors.
- Added governance scaffold (`README.md`, `ROADMAP.md`, `AGENTS.md`,
  `LICENSE`, `pyproject.toml`), package skeleton (`src/fresh_fuchs/`), and
  empty `docs/`, `examples/`, `tests/`, `tmp/`.
- Recorded the locked design decisions and validation anchors (tsa29mini
  deterministic baseline; fresh-salvage salvage-margin and MFRI constants).
