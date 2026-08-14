Model Semantics
===============

The FUCHS model is a nested decision problem on the tsa29mini instance.
This page records exactly what the model computes, the formulation choices,
and the known limitations. The authoritative source is
``planning/v0.1.0a1-plan.md``.

The nested formulation
----------------------

**Inner problem (enterprise / implementation) — a Model I linear program.**
Per scenario, maximize discounted net revenue (NPV) over harvest and
replanting decisions subject to:

- an even-flow band on harvest volume (the AAC proxy): per-period harvest
  volume within 5% of period 1 on the managed land base;
- the outer policy constraints (species-composition area-share targets with
  tolerance; an optional harvest policy — AAC volume band or rotation-age
  floor/ceiling — folded in as rows);
- salvage feasibility (salvage <= burned stock);
- replanting transitions (regeneration after harvest or salvage).

The LP is a continuous Model I formulation (no binaries, no thresholding),
solved with the ws3 LP machinery + HiGHS. The objective coefficient is the
discounted net cash flow along each prescription path
(``fresh_fuchs.economy.npv``); the even-flow band stays on harvest volume.
With a zero discount rate and no cross-species price differential, the
NPV-max LP reproduces the volume-max baseline exactly (verified in
``tests/test_npv.py``).

**Outer problem (policy / administration) — a grid search over the NPV
distribution.** Landscape policy is a ``PolicyRecord``: species-composition
area-share targets (with tolerance) plus an optional harvest policy (AAC
proxy, or rotation-age floor/ceiling per species). A ``PolicyGrid`` expands
to its Cartesian product (plus an optional unconstrained baseline); each
grid point is evaluated on a full-Monte-Carlo distribution of NPV and
summarized with downside-risk measures — expected NPV, volatility, VaR,
CVaR (default 95%), and shortfall probability — with a Gaussian comparison.
Policies are ranked by a reproducible rule (lexicographic on (E[NPV], CVaR),
or a weighted mean-CVaR score), and a recommended policy plus a
coarse-vs-fine grid-resolution sensitivity are reported.

The scenario engine
-------------------

Fire occurrence, extent, and severity are sampled per scenario from
MFRI-by-zone annual burn rates (burn probability 1/MFRI) with a severity
ladder (Unburned 0 / Low 0.30 / Moderate 0.60 / High 0.85; default
Moderate). Fire is encoded in the inner LP as path-dependent coefficients —
survival ``Pi(1-p)`` since regeneration, green volume ``Y(age) x survival``,
burn influx ``p x exposed``, salvageable ``severity x influx`` — and
``salvage`` is a real Model I action with age-0 regeneration. Burned volume
decays at 0.85/yr; the within-timestep ordering is harvest -> fire ->
salvage -> decay. One inner LP is solved per scenario with **full
foresight** (the fire events are fixed within a scenario); recourse /
rolling-horizon is post-v0.1.0a1. The uncertainty vector pairs a Gaussian
burn-rate multiplier with a price factor (fixed at 1.0 in v0.1.0a1; the
dimension exists for the later stochastic-price work).

Orchestration
-------------

The whole pipeline is wrapped as freshforge workflows/matrices with
evidence manifests (``fresh_fuchs.orchestration``), reproducible on the
public-safe synthetic instance (``fresh_fuchs.instance.synthetic``) in CI.

Known limitations (v0.1.0a1)
----------------------------

- **Full-foresight optimism**: the inner LP sees the whole scenario's fire
  schedule in advance, so NPV is an upper bound on the recourse value.
- **Interior price-surface provenance**: flat Q4-2023 interior sawlog-basis
  prices; grade/peeler premia reserved for the log-grade follow-on.
- **Harvest-area discrepancy vs Patchworks**: ws3 mean annual harvest is
  ~3.8% above Patchworks (modelling-convention difference, understood and
  bounded; recorded in the validation report).
- **Unsubsidized salvage**: the default prompt-salvage regime has a negative
  margin, so salvage is suppressed (matching the fresh-salvage reference
  agent); subsidy/salvage-uptake scenarios are post-v0.1.0a1.
- **Replant costs**: flat per-ha assumptions, not charged by default (the
  $45/m3 harvest cost carries the silviculture allocation); transition-
  dependent replanting cost is post-v0.1.0a1.
