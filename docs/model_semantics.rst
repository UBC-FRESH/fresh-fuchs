Model Semantics
===============

(Under construction — Phase 0.)

High-level formulation (recorded in
``planning/v0.1.0a1-plan.md``):

- **Inner LP (Model I).** Per scenario, maximize NPV over harvest and
  replant decisions subject to even flow, outer policy constraints
  (composition targets, AAC/rotation), salvage feasibility, and replant
  transitions. Solved with ws3 LP machinery + HiGHS.
- **Outer policy problem.** Grid search over composition targets and
  AAC/rotation policy, each evaluated on a full-MC distribution of NPV with
  downside-risk measures (expected NPV, CVaR, shortfall).
- **Scenario engine.** Fire occurrence/extent/severity from MFRI-by-zone
  burn rates; fire encoded as scheduled ws3 actions/transitions; one inner
  LP solve per scenario (full foresight within a scenario).

Known limitations (v0.1.0a1): full-foresight optimism, Interior price
surface provenance, harvest-area discrepancy vs Patchworks (tracked in the
validation report).
