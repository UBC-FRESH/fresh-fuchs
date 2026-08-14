# Dynamic inconsistency of the inner LP (Daugherty 1991) — assessment note

Status: analysis record (2026-08-14). Raised by J. Fuchs (Basecamp, after the
v0.1.0a1 announcement). Reference: Daugherty, P. J. (1991), *Credibility of
Long Term Forest Planning: Dynamic Inconsistency in Linear Programming Based
Forest Planning Models*, PhD thesis, UC Berkeley (`tmp/daugherty1991credibility.pdf`,
scanned, 172 pp.).

## The claim

The inner problem is formulated as: **maximize NPV (3% discount) subject to
an even-flow harvest-volume constraint.** Daugherty (1991) proves that
LP-based forest planning models solved as **open-loop** formulations admit
**dynamically inconsistent** solutions — plans that will not be followed when
reconsidered at a later time under the same goals — and that such plans are
not a credible basis for policy. The concern is that our inner LP falls in
this class.

## What Daugherty actually shows (read from the thesis)

- **Definition** (abstract): dynamic inconsistency is the failure to satisfy
  Bellman's principle of optimality; in forest planning, the open-loop plan's
  tail is not what a future planner re-solving from the realized state would
  choose.
- **Mechanism** (ch. 3, "Consistent Solutions", eq. 3-34): current
  formulations let the current planner **precommit future planners** to the
  derived schedule; nothing forces future decisions to satisfy the future
  planners' own optimality conditions. A consistent (credible) solution is
  the subgame-perfect one: at every period the remaining plan is re-optimal
  from the realized state.
- **On the discount rate** (ch. 3, "Interest Rate Effects", p.58-59): the
  relationship is *not* the naive one. The discount-factor shift between
  successive periods is uniform and "drops out of the consistency
  requirements"; the actual drivers are the **harvest-flow constraint**
  (the explicit between-period link), **disequilibrium forest structure**,
  and **negatively-valued strata**. Daugherty explicitly notes the
  counter-intuitive result that raising the discount rate does not
  necessarily raise inconsistency.
- **On remedies** (ch. 7, "Alternatives"): precommitment is generally
  non-credible (loss of flexibility) *except* legal/regulatory requirements —
  notably a **regeneration requirement is a credible precommitment** that
  mitigates inconsistency by transferring capital to future planners.
  Sequential/rolling harvest-flow constraints remove the *explicit*
  between-period link but leave *implicit* links via future supply, so they
  do not fully solve it.
- **On stakes** (ch. 7, "Credibility"): trade-off/shadow-price analysis from
  inconsistent solutions is not credible; the cost of a constraint (e.g.
  preserving habitat) computed from an inconsistent LP is biased.

## Our formulation's exposure

The inner LP (`fresh_fuchs.economy.npv.add_npv_problem` /
`fresh_fuchs.instance.baseline.add_even_flow_problem`) is exactly the flagged
combination:

- objective `z` = discounted net cash flow at the surface discount rate
  (default **3%**, `EconomicSurface.discount`);
- constraint `cflw_hv` = even-flow on harvest volume: every period within
  `flow_coefficient` (5%) of the **period-1** harvest level (ws3 `cflw_e`
  with `ref_period = 1`).

So the model is structurally exposed. The outer policy layer (composition /
AAC trade-offs, CVaR ranking) inherits the exposure because its NPV
distributions rest on inner-LP schedules.

## Empirical test on the synthetic instance (sequential replanning)

Reproducible method (`tmp/inconsistency_test.py`, synthetic instance,
horizon 5, period length 10):

1. Solve the open-loop NPV-max even-flow LP over horizon H → per-period
   harvest volumes and the compiled schedule.
2. Apply **only period 1** of that schedule (state advancement verified: the
   post-period-1 inventory differs from the pristine trajectory).
3. Re-solve a fresh NPV-max even-flow LP from the realized state over the
   remaining H−1 periods, with the even-flow band held at the **committed**
   period-1 level (the same policy the original planner faced) and the
   discount rate applied from the replanner's present (the "same goals").
4. Align replan period k with open-loop period k+1 and compare.

Result (synthetic instance, 3% discount):

| abs. period | open-loop volume | replan volume |
| --- | --- | --- |
| 2 | 13,071.4 | 13,071.4 |
| 3 | 11,826.5 | 13,071.4 |
| 4 | 11,826.5 | 13,071.4 |
| 5 | 11,826.5 | 13,071.4 |

The period-1→2 transition **is** followed, but the plan's periods 3-5 tail
(locked to the 5% band floor under the period-1 anchor) is **not** what the
future planner chooses; the replanner re-centres to the top of the band.
Maximum tail divergence ≈ **9.5%** of volume.

**Key control result:** the identical test at **0% discount** yields the
*same* ≈ 9.5% divergence. On this synthetic instance the inconsistency is
real but is **not** driven by the discount rate — it is driven by the
even-flow band's replanning asymmetry (the open-loop solver uses the ±5%
band asymmetrically across periods to shade the objective; the replanner
re-centres). This is consistent with Daugherty's own subtlety (the discount
factor "drops out"; the flow constraint is the operative link), and it
**does not** support the stronger one-line claim that "drop the discount
rate to 0 and the problem goes away."

## Interpretation and caveats

- The synthetic instance is a *minimal* fixture (flat prices, two zones,
  smooth saturating yields, no negatively-valued strata, near-equilibrium
  age structure). Daugherty finds the *magnitude* grows with disequilibrium,
  negatively-valued strata, and range of choices — all of which the real
  tsa29mini bundle has more of. The synthetic result is a lower bound, not a
  clean measurement of the real instance.
- The measured magnitude depends on how the even-flow anchor is treated
  under replanning (held at the committed level vs re-anchored). Both are
  defensible readings of "same goals"; they change the number, not the
  existence. A defensible production measurement needs a proper
  sequential-replanning simulator (the subject of the paper Jasper
  proposes).
- Bottom line for v0.1.0a1: the as-implemented inner LP is **open-loop and
  is dynamically inconsistent on our test instance**, so its long-horizon
  harvest projections — and the outer-layer NPV distributions and policy
  rankings built on them — should be read as **not credible as
  intertemporal plans**. This is now a documented known limitation.

## Design options (for discussion / follow-on work)

1. **Document and scope-limit** (v0.1.0a1 stance): keep the formulation for
   the prototype, but record the dynamic-inconsistency caveat prominently
   (this note + `docs/model_semantics.rst` + validation report), and stop
   presenting open-loop NPV trajectories as credible plans.
2. **Regeneration requirement as credible precommitment**: Daugherty notes a
   legally-binding regeneration requirement is one of the few credible
   precommitments. Our inner LP already has regeneration transitions; making
   regeneration *mandatory* (and charging its cost) is both more realistic
   and partially inconsistency-mitigating. (Currently replant cost is not
   charged by default.)
3. **Sequential/rolling replanning (receding horizon)**: solve period 1,
   apply, re-solve. Removes the explicit flow link but leaves implicit links
   — and it is a *different* (and more expensive) decision procedure than
   the open-loop LP we evaluate, so it changes the object being studied.
4. **Consistent-solution construct (subgame-perfect / MPE)**: the proper fix
   is the recursive consistent solution (Daugherty eq. 3-34), i.e. a
   game-theoretic / Markov-perfect formulation. This is a research
   contribution, not a patch — precisely the Daugherty-reproduction paper
   Jasper proposes.
5. **Drop the even-flow constraint or drop the discount rate**: each makes
   the remaining problem time-consistent in the narrow sense, but changes
   the economic question being asked (Jasper's own framing). Our data do not
   support the claim that zero discount restores consistency on this
   instance (the even-flow replanning asymmetry persists).

## Recommended next step

Treat this as a research direction, not a v0.1.0a1 patch: (a) adopt option 1
now (document + scope-limit); (b) build the sequential-replanning simulator
and the consistent-solution formulation as the proposed Daugherty-
reproduction study, using fresh-fuchs/ws3 as the open, reproducible stack.

## Follow-on side quest

This is tracked as a dedicated side quest — **reproduce Daugherty (1991) in
ws3, openly and citably, and write the peer-reviewed paper** — in
`ROADMAP.md` and issue
[#40](https://github.com/UBC-FRESH/fresh-fuchs/issues/40). The thesis is
effectively inaccessible (archival hard-copy only, ~$200 custom print), so
the reproduction + paper is what makes the result citable in the fresh-fuchs
paper and lets the field stop rediscovering the trap. fresh-fuchs provides
the real test instance (tsa29mini) and the CI-safe characterization test
(`tests/test_dynamic_inconsistency.py`) as a starting point.
