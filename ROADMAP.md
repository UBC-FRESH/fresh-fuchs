# fresh-fuchs Roadmap

This roadmap is the condensed issue-tracker view of the current project
plan. The detailed plan, design decisions, acceptance criteria, and
validation anchors live in `planning/v0.1.0a1-plan.md`. Keep this roadmap
synchronized with GitHub issues, planning notes, pull requests, and
`CHANGE_LOG.md`.

## Issue Tracker Map

| Phase | Parent issue | Branch | Status |
| --- | --- | --- | --- |
| P0 Skeleton scaffold | TBD | `feature/p0-skeleton-scaffold` | Complete |
| P1 Instance and model integration | [#1](https://github.com/UBC-FRESH/fresh-fuchs/issues/1) | `feature/p1-instance-model` | Complete (P1.1 [#2](https://github.com/UBC-FRESH/fresh-fuchs/issues/2), P1.2 [#3](https://github.com/UBC-FRESH/fresh-fuchs/issues/3), P1.3 [#4](https://github.com/UBC-FRESH/fresh-fuchs/issues/4), P1.4 [#5](https://github.com/UBC-FRESH/fresh-fuchs/issues/5), P1.5 [#6](https://github.com/UBC-FRESH/fresh-fuchs/issues/6)) |
| P2 Economic valuation layer | [#8](https://github.com/UBC-FRESH/fresh-fuchs/issues/8) | `feature/p2-economy` | Complete (P2.1 [#9](https://github.com/UBC-FRESH/fresh-fuchs/issues/9), P2.2 [#10](https://github.com/UBC-FRESH/fresh-fuchs/issues/10), P2.3 [#11](https://github.com/UBC-FRESH/fresh-fuchs/issues/11), P2.4 [#12](https://github.com/UBC-FRESH/fresh-fuchs/issues/12), P2.5 [#13](https://github.com/UBC-FRESH/fresh-fuchs/issues/13), P2.6 [#14](https://github.com/UBC-FRESH/fresh-fuchs/issues/14)) — PR pending |
| P3 Full-MC scenario engine | [#16](https://github.com/UBC-FRESH/fresh-fuchs/issues/16) | `feature/p3-scenario` | Complete (P3.1 [#17](https://github.com/UBC-FRESH/fresh-fuchs/issues/17), P3.2 [#18](https://github.com/UBC-FRESH/fresh-fuchs/issues/18), P3.3 [#19](https://github.com/UBC-FRESH/fresh-fuchs/issues/19), P3.4 [#20](https://github.com/UBC-FRESH/fresh-fuchs/issues/20), P3.5 [#21](https://github.com/UBC-FRESH/fresh-fuchs/issues/21), P3.6 [#22](https://github.com/UBC-FRESH/fresh-fuchs/issues/22); PR [#23](https://github.com/UBC-FRESH/fresh-fuchs/pull/23) merged to `main`) |
| P4 Outer policy layer | [#24](https://github.com/UBC-FRESH/fresh-fuchs/issues/24) | `feature/p4-outer` | Active — P4.1 [#25](https://github.com/UBC-FRESH/fresh-fuchs/issues/25) done, P4.2 [#26](https://github.com/UBC-FRESH/fresh-fuchs/issues/26) done, P4.3 [#27](https://github.com/UBC-FRESH/fresh-fuchs/issues/27) done, P4.4 [#28](https://github.com/UBC-FRESH/fresh-fuchs/issues/28) done, P4.5 [#29](https://github.com/UBC-FRESH/fresh-fuchs/issues/29) |
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
