fresh-fuchs
===========

``fresh-fuchs`` (the FUCHS project) builds a stochastic, risk-aware forest
landscape planning prototype on the ``femic-tsa29mini-instance`` bundle: a
~100,000 ha square subset of Williams Lake TSA29 (90,499.8 ha total;
35,083.0 ha managed land base after the proportional retention split).

The research design is a nested decision problem:

- **Outer problem (policy / administration).** Landscape-scale policy on
  (1) target species / development-type composition by area share and
  (2) harvest policy — AAC as a function of development type and rotation
  age. Evaluated risk-sensitively on the distribution of outcomes using
  downside-risk measures (CVaR).
- **Inner problem (enterprise / implementation).** Harvest scheduling and
  replanting decisions (which species to plant) maximizing NPV subject to
  the outer policy constraints, formulated as a Model I linear program.

The outer problem runs as a full Monte-Carlo: disturbance (fire) — and,
later, wood-price — realizations are sampled, the inner LP is solved once
per scenario (full foresight within a scenario), and each policy is
evaluated on the resulting NPV distribution.

The package reuses the UBC-FRESH ecosystem rather than re-implementing it:

- ``ws3`` — wood-supply engine and LP machinery (inner solver).
- ``femic`` — tsa29mini instance bundle, Woodstock bridge, BTC log-grade
  and FAN$IER yield/revenue-curve orchestration.
- ``fhops`` — harvest-cost estimation.
- ``nemora`` — diameter distribution fit and sampling for stochastic
  drivers.
- ``freshforge`` — workflow and matrix orchestration plus evidence
  manifests.
- ``fresh-salvage`` — economic calibration anchors (reference only).

Status: Phase 0 (skeleton scaffold). The detailed master plan to the
``v0.1.0a1`` release lives in ``planning/v0.1.0a1-plan.md`` in the
repository; ``ROADMAP.md`` is the condensed issue-tracker view.

Documentation Map
-----------------

.. list-table::
   :header-rows: 1

   * - Page
     - What it answers
   * - :doc:`installation`
     - How do I get a working environment (including the external ws3 and
       femic source dependencies) and verify it?
   * - :doc:`quickstart`
     - How do I go from a clean checkout to a first pipeline result, and
       where do the outputs land?
   * - :doc:`model_semantics`
     - What exactly does the model compute — the nested inner/outer
       formulation, the MC scenario engine, and known limitations?
   * - :doc:`cli`
     - What does each command read, write, and exit with?
   * - :doc:`architecture`
     - How are the modules organized and what are the design invariants?
   * - :doc:`development`
     - How do I test, lint, extend the model, and get a PR accepted?

.. toctree::
   :maxdepth: 2
   :caption: Contents

   installation
   quickstart
   model_semantics
   cli
   architecture
   development
