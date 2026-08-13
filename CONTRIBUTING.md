# Contributing to fresh-fuchs

Thanks for contributing to `fresh-fuchs`, a UBC-FRESH project. Please read
`AGENTS.md` before making project-shaping changes — it is the working
contract for this repository.

## Project Structure

- `ROADMAP.md` — phase/task roadmap and issue tracker map.
- `planning/v0.1.0a1-plan.md` — the detailed master plan to the first
  release.
- `CHANGE_LOG.md` — append-only project narrative.
- `src/fresh_fuchs/` — package modules.
- `tests/` — package-backed tests.
- `docs/` — Sphinx documentation.

## Development Workflow

This repo follows the UBC-FRESH phase/task/subtask workflow:

1. One roadmap phase -> one GitHub parent issue -> one feature branch.
2. One roadmap task -> one child issue under the parent.
3. Work child issues in roadmap order; update issue checklists as you go.
4. Open a PR from the phase branch to `main` when the phase tasks, tests,
   docs, and closeout notes are complete or explicitly deferred.

Read `AGENTS.md` for the full strict-development workflow and issue-quality
standards.

## Local Checks

Run these before opening a PR:

```bash
python -m ruff check .
python -m pytest
sphinx-build -b html docs _build/html -W
python -m build
twine check dist/*
```

## What to Keep Out

Do not commit private project data, credentials, machine-specific paths,
unpublished documents, or large/annexed datasets. Tests and examples must
use synthetic or public-safe fixtures.

## Code of Conduct

Please review `CODE_OF_CONDUCT.md`; all contributors are expected to follow
it.
