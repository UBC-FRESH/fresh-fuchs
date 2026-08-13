# AGENTS.md

This file is the working contract for AI coding agents in this repository.

## Project Purpose

`fresh-fuchs` (the FUCHS project) builds a stochastic, risk-aware forest
landscape planning prototype on the `femic-tsa29mini-instance` bundle
(~100,000 ha subset of TSA29, Williams Lake). The research design is a
nested decision problem:

- **Outer (policy/administration):** landscape-scale policy on target
  species/development-type composition by area share and on harvest policy
  (AAC as f(development type, rotation age)), evaluated risk-sensitively on
  Monte-Carlo distributions of NPV using downside-risk measures (CVaR).
- **Inner (enterprise/implementation):** harvest scheduling and replanting
  decisions maximizing NPV subject to outer policy constraints, formulated
  as a Model I linear program.

The durable source of truth is typed data records, an extended ws3 model,
explicit LP formulations, MC scenario records, and verification evidence —
not one-off script chains.

## Reuse Boundary

This package stays aligned with the FRESH ecosystem and must not re-implement
domain packages:

- Consume `ws3` (`ForestModel`, LP machinery, Model I even-flow,
  actions/transitions), `femic` (tsa29mini bundle, `fmg/woodstock.py`,
  `ws3_bridge.py`, BTC log-grades, FANSIER, price matrices), `fhops`
  (harvest-cost estimation, salvage modes, road costs), `nemora` (DBH
  distribution fit and sampling), `freshforge` (workflow + matrix
  orchestration, evidence), and `fresh-salvage` calibration anchors
  (reference only; no import).
- Do not re-implement WS3, FHOPS, FEMIC, Nemora, or FreshForge.

## Current Repo State

`fresh-fuchs` is at Phase 0 (scaffold). Expected layout (track the active
phase in `ROADMAP.md`):

- `README.md`: concise public overview and current status.
- `ROADMAP.md`: phase/task roadmap and issue tracker map.
- `planning/`: focused design notes — `v0.1.0a1-plan.md` is the master
  plan; validation and calibration records are added per phase.
- `CHANGE_LOG.md`: append-only project narrative (reverse-chronological).
- `RELEASE_NOTES.md`: release history.
- `pyproject.toml`: package metadata and optional dependency groups.
- `src/fresh_fuchs/`: package modules — `instance`, `economy`, `scenario`,
  `inner`, `outer`, `orchestration`, and the wired CLI.
- `tests/`: package-backed tests across all layers (synthetic/public-safe
  fixtures only).
- `docs/`: Sphinx documentation.
- `examples/`: public-safe example configs for every command.
- `.github/workflows/`: CI, docs, and release-artifact checks.
- `tmp/`: ignored local working area.

## Workflow Specs And Generated Outputs

Model inputs, compiled schedules, run records, generated reports, and
scratch execution logs are local working material unless the maintainer
explicitly asks to track a sanitized artifact.

Rules:

- Keep `tmp/`, `local/`, `data/private/`, and `outputs/` ignored.
- Do not commit private project data, raw transcripts, local workflow
  outputs, credentials, machine-specific paths, or unpublished documents.
- Do not vendor the annex bundle or other large/private datasets; bundle
  paths come from config and are never tracked.
- Tracked examples and tests must use synthetic or public-safe fixtures.
- Record provenance for every interpreted data source, ws3 bridge file, LP
  formulation, MC scenario, solver run, environment, and validation result.
- Keep model-specific assumptions explicit rather than silently baking them
  into generic core logic.

## Working Principles

- Read `AGENTS.md`, `ROADMAP.md`, `CHANGE_LOG.md`, and
  `planning/v0.1.0a1-plan.md` before making project-shaping changes.
- Keep CLI commands thin wrappers over Python APIs.
- Parse inputs at the boundary into typed Pydantic records; keep core logic
  free of defensive re-validation.
- Keep the inner problem linear: continuous LP, no binaries, no thresholding
  or rounding of decision outputs (unless a later phase records otherwise).
- Emit explicit diagnostics for missing data, unsupported ws3 features,
  failed solves, uncertain provenance, and failed validation.
- Preserve uncertainty. A model result is only as strong as its declared
  inputs, formulations, seeds, and verification evidence.
- Keep public repo content clean of private, irrelevant, or unpublished
  references. Prefer sanitized summaries over raw pasted notes.
- Keep changes scoped to the active roadmap phase and issue.

## Planning Workflow

This repo follows the UBC-FRESH phase/task/subtask workflow:

- `ROADMAP.md` is the current plan and issue tracker map;
  `planning/v0.1.0a1-plan.md` is the detailed master plan.
- One roadmap phase maps to one GitHub parent issue and one feature branch.
- One roadmap task maps to one child issue linked from the parent issue
  body.
- Use at most three issue levels: phase, task, implementation subtask.
- Record issue numbers beside roadmap phases and tasks once created.
- Keep `ROADMAP.md`, `CHANGE_LOG.md`, planning notes, issue bodies, and PR
  descriptions synchronized.
- Open a PR from the phase branch to `main` only after phase tasks, tests,
  docs, and closeout notes are complete or explicitly deferred.

## Strict Development Workflow

- One active roadmap phase corresponds to one GitHub parent issue and one
  feature branch; create the parent issue before starting the phase.
- Work child issues one at a time, usually in roadmap order.
- Before closing a child issue, update every issue-body checklist item to
  checked, or rewrite the issue body to make clear which items were
  superseded or are not applicable.
- Close each child issue only after its repo changes, documentation,
  issue-body checklist, and verification are complete.
- Open a PR from the phase branch to `main` when the parent issue's child
  issues are complete or explicitly deferred; close the parent issue only
  after the PR merges.

## GitHub Issue And Comment Formatting

Formatting matters. Issue bodies and comments must be readable as rendered
Markdown.

Rules:

- Use short section labels on their own lines, such as `Roadmap task:
  P1.1`, `Parent phase issue: #18`, `Status: active`, and `Checklist:`.
- Use real GitHub task-list syntax, one checklist item per line; never write
  inline pseudo-checklists.
- Wrap branch names, file paths, commands, and commit hashes in backticks.
- For parent phase issues, list child issues as task-list bullets with issue
  numbers and task IDs.
- Prepare issue bodies as multi-line Markdown strings or temporary body
  files before creating or editing several issues.

## GitHub Issue Body Quality Standard

Write issue bodies so a new lab student, external collaborator, or coding
agent can understand the task, implement it, verify it, and close it without
reading the original chat transcript. Parent phase issues must include phase
identifier, status, branch name, roadmap links, goal, scope, out-of-scope
boundaries, architecture notes, child task checklist, acceptance criteria,
verification, and closeout requirements. Child task issues must include task
identifier, parent phase issue, status, related planning links, goal, scope,
out-of-scope boundaries, subtasks, acceptance criteria, verification
commands, artifacts, risks, and completion metadata once closed. Do not
create placeholder issue bodies with only a title and a short checklist
unless the maintainer explicitly asks for a placeholder.

## Verification

Default local checks:

```bash
python -m ruff check .
python -m pytest
sphinx-build -b html docs _build/html -W
python -m build
twine check dist/*
```

Default CI must not require private project data, commercial GIS software,
local desktop applications (BatchTIPSY, FANSIER), credentials, Gurobi
licenses, or network downloads beyond package installation.
