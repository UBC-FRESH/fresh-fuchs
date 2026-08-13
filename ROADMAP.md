# fresh-fuchs Roadmap

This roadmap is the condensed issue-tracker view of the current project
plan. The detailed plan, design decisions, acceptance criteria, and
validation anchors live in `planning/v0.1.0a1-plan.md`. Keep this roadmap
synchronized with GitHub issues, planning notes, pull requests, and
`CHANGE_LOG.md`.

## Issue Tracker Map

| Phase | Parent issue | Branch | Status |
| --- | --- | --- | --- |
| P0 Skeleton scaffold | TBD | `feature/p0-skeleton-scaffold` | Planned |
| P1 Instance and model integration | TBD | `feature/p1-instance-model` | Planned |
| P2 Economic valuation layer | TBD | `feature/p2-economy` | Planned |
| P3 Full-MC scenario engine | TBD | `feature/p3-scenario` | Planned |
| P4 Outer policy layer | TBD | `feature/p4-outer` | Planned |
| P5 Orchestration, validation, calibration, release | TBD | `feature/p5-release` | Planned |

## Project One-Liner

Stochastic, risk-aware forest landscape planning on the TSA29 mini instance:
a full-Monte-Carlo outer policy problem (species-composition targets and
AAC/rotation policy, evaluated on NPV distributions with CVaR) wrapped
around a per-scenario Model I inner LP (NPV-max harvest + replant
scheduling), reusing `ws3`, `femic`, `fhops`, `nemora`, and `freshforge`.

## Locked Design Decisions

1. Outer = full MC; inner = Model I LP maximizing NPV.
2. Full foresight within a scenario (fire events are fixed per scenario);
   recourse/rolling-horizon is post-v0.1.0a1.
3. Species dimension added to the ws3 bridge (species-proportion curves).
4. Base case: tsa29mini bundle (90,499.8 ha; 35,083.0 ha managed; 21 AU;
   72 DT; 30 x 10-yr horizon).
5. NPV surface is greenfield but anchored to fresh-salvage calibration.

## v0.1.0a1 Definition of Done (summary)

End-to-end pipeline (bundle -> extended model -> MC scenarios -> inner LP
per scenario -> NPV distribution -> policy grid search -> CVaR ranking),
deterministic regression anchors, outer/inner coupling demonstrated,
validation + economics-calibration reports, governance/docs/CI/release
artifacts. See `planning/v0.1.0a1-plan.md` section 3 for the full list.

## Out of Scope for v0.1.0a1

Recourse planning, Interior log-grade revenue curves (BTC/FANSIER),
transition-dependent replanting costs, PaCal acceleration, min/max-rotation
outer variables, full-TSA/BC scale-up, DE/CH country comparison.
