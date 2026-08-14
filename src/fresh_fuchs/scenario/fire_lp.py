"""Fire encoding in the ws3 Model I inner LP (Phase 3, P3.4).

Fire enters the even-flow/NPV LP through *path-dependent coefficients*
rather than extra decision rows: the LP already chooses *when* to harvest a
cohort, so the expected fire impact of any prescription is computable along
its path (P3.1 dynamics). Concretely, for a scenario:

- **Survival-reduced green harvest.** A cohort exposed to a per-period burn
  probability ``p(t)`` (zone rate x scenario multiplier, P3.3 events) loses
  ``p(t)`` of its live volume each period it is not harvested. The green
  harvest volume realized in period ``t`` is the yield ``Y(a_t)`` times the
  fire survival ``product_{u < t}(1 - p(u))`` accumulated since the last
  regeneration (harvest or salvage resets the stand).
- **Salvage action.** ``salvage`` is a Model I action (operable only for
  stands at or above ``min_salvage_age`` in periods where the scenario burns
  that zone) that harvests the burned pool: salvageable volume in period
  ``t`` is ``severity_fraction x p(t) x exposed live``. Salvage carries the
  P2.4 salvage economics (burned price discount, cost premium, stumpage
  floor) and transitions to a regenerated stand, per the ws3
  disturbance-modelling ordering harvest -> fire -> salvage -> decay. The
  age floor excludes salvage of regenerating stands and, together with the
  per-period operability pruning, bounds Model I tree growth (a salvaged
  cohort only reopens the salvage branch once back above the threshold).
- **Salvage feasibility row.** A general row ``salvage_vol(t) -
  salvageable_vol(t) <= 0`` makes the "salvage <= burned stock" ceiling an
  explicit LP row. Because a Model I path's salvage volume *is* its computed
  salvageable ceiling, the row is structurally satisfied; it exists so the
  ceiling is testable from the solved problem and documented as an LP row.

The burned/decay pool is not tracked as a stock variable (v0.1.0a1): an
unsalvaged cohort keeps only the live balance, and the burned carryover
decays out of the model. Salvage is a free LP decision at the P2.4 margins:
with the default negative SPF margin the inner LP salvages nothing, exactly
as the fresh-salvage reference agent does at the same margin; the mechanism
is exercised with a positive (subsidised) margin in the tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
import ws3.forest
import ws3.opt
from pydantic import BaseModel, Field

from fresh_fuchs.economy.cashflow import (
    harvest_cash_flow,
    sawlog_basis_salvage_margin,
)
from fresh_fuchs.economy.npv import DevelopmentTypeKey
from fresh_fuchs.economy.types import EconomicSurface, price_group_for_species
from fresh_fuchs.instance.baseline import solve_even_flow
from fresh_fuchs.instance.species import SpeciesClass
from fresh_fuchs.scenario.fire import period_burn_probability, severity_burned_fraction
from fresh_fuchs.scenario.records import DisturbanceScenario


class FireLpConfig(BaseModel):
    """Specification of the fire-aware inner LP.

    Mirrors :class:`fresh_fuchs.economy.types.NpvConfig` (same even-flow band
    on post-fire green harvest volume, the AAC proxy) with the fire inputs of
    one scenario. ``zone_by_au`` maps each analysis unit to its BEC zone; the
    scenario events then fix the per-(zone, period) burn probability.
    """

    name: str = Field(default="fire-npv-managed")
    sense: Literal["maximize"] = "maximize"
    flow_coefficient: float = Field(default=0.05, gt=0.0)
    mask: tuple[str, str, str, str, str] = Field(default=("?", "managed", "?", "?", "?"))
    product: str = Field(default="totvol")
    action_codes: tuple[str, ...] = Field(default=("null", "harvest", "salvage"))
    workers: int = Field(default=1, ge=1)
    min_salvage_age: int = Field(
        default=60,
        ge=0,
        description=(
            "Minimum stand age for salvage operability. Salvage of regenerating "
            "stands below rotation age is not modelled (their burned volume is "
            "negligible), which also bounds the Model I tree: a salvaged cohort "
            "only reopens the salvage branch once it is back above the threshold."
        ),
    )
    zone_by_au: dict[int, str] = Field(
        description="au_id -> BEC zone (the scenario events are keyed by zone)."
    )


@dataclass(frozen=True)
class FirePathStep:
    """One period of a prescription path under fire (cohort-volume units).

    Volumes are in the model's cohort units (per-ha yield x the initial
    cohort area), matching ``compile_product`` coefficients so the walk can
    be summed straight into LP row values.
    """

    period: int
    acode: str
    dtk: tuple[str, ...]
    age: int
    yield_volume: float
    burn_prob: float
    survival_to: float
    green_volume: float
    burn_influx: float
    salvageable: float
    salvaged: float


def build_burn_prob_lookup(
    scenario: DisturbanceScenario,
    period_length: int,
) -> dict[tuple[str, int], float]:
    """Return ``{(zone, period): burn_probability}`` from the scenario events.

    Periods without an event for a zone (or with a zero annual rate) map to
    ``0.0``: no burn, no salvageable volume, no survival discount.
    """
    lookup: dict[tuple[str, int], float] = {}
    for event in scenario.events:
        zone = str(event.zone).strip().upper()
        prob = period_burn_probability(event.annual_burn_rate, period_length)
        lookup[(zone, event.period)] = prob
    return lookup


def _burn_prob_for_dtk(
    lookup: dict[tuple[str, int], float],
    zone_by_au: dict[int, str],
    dtk: tuple[str, ...],
    period: int,
) -> float:
    au_id = int(dtk[2])
    if au_id not in zone_by_au:
        known = ", ".join(sorted(str(a) for a in zone_by_au))
        raise ValueError(
            f"development type {dtk} references au_id {au_id} with no BEC zone; "
            f"mapped au_ids: {known}"
        )
    return lookup.get((zone_by_au[au_id].upper(), period), 0.0)


def path_fire_steps(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    scenario: DisturbanceScenario,
    zone_by_au: dict[int, str],
) -> list[FirePathStep]:
    """Walk a prescription path under the scenario's fire, one step per period.

    Per the P3.1 ordering harvest -> fire -> salvage -> decay, within a
    period: a harvest removes the live cohort (no burn that period, the stand
    regenerates); a salvage removes the burned pool that materialises that
    period (``severity x burn_influx``) and regenerates the stand; a null
    period leaves the cohort standing and compounds the survival factor.

    Volumes share the model's cohort units (per-ha yield x initial cohort
    area). The per-ha yield is read from the development type's ``totvol``
    curve (``ycomp``), not ``compile_product``, so the walk is independent of
    the model's transient applied-action state.
    """
    severity_frac = severity_burned_fraction(scenario.severity)
    lookup = build_burn_prob_lookup(scenario, fm.period_length)
    cohort_area = float(path[0].data("area"))
    steps: list[FirePathStep] = []
    survival = 1.0
    for t, node in enumerate(path, start=1):
        d = node.data()
        acode = d["acode"]
        dtk = tuple(d["dtk"])
        age = d["age"]
        ycomp = fm.dt(dtk).ycomp("totvol")
        if ycomp is None:
            raise ValueError(f"development type {dtk} has no 'totvol' yield component")
        yield_volume = float(ycomp[age]) * cohort_area
        prob = _burn_prob_for_dtk(lookup, zone_by_au, dtk, t)
        exposed = yield_volume * survival
        if acode == "harvest":
            steps.append(
                FirePathStep(
                    period=t,
                    acode=acode,
                    dtk=dtk,
                    age=age,
                    yield_volume=yield_volume,
                    burn_prob=prob,
                    survival_to=survival,
                    green_volume=exposed,
                    burn_influx=0.0,
                    salvageable=0.0,
                    salvaged=0.0,
                )
            )
            survival = 1.0  # regenerated stand: fresh fire exposure
        elif acode == "salvage":
            influx = prob * exposed
            salvageable = severity_frac * influx
            steps.append(
                FirePathStep(
                    period=t,
                    acode=acode,
                    dtk=dtk,
                    age=age,
                    yield_volume=yield_volume,
                    burn_prob=prob,
                    survival_to=survival,
                    green_volume=0.0,
                    burn_influx=influx,
                    salvageable=salvageable,
                    salvaged=salvageable,
                )
            )
            survival = 1.0  # regenerated stand after salvage
        else:  # null: the cohort stands and accumulates fire exposure
            influx = prob * exposed
            salvageable = severity_frac * influx
            steps.append(
                FirePathStep(
                    period=t,
                    acode=acode,
                    dtk=dtk,
                    age=age,
                    yield_volume=yield_volume,
                    burn_prob=prob,
                    survival_to=survival,
                    green_volume=0.0,
                    burn_influx=influx,
                    salvageable=salvageable,
                    salvaged=0.0,
                )
            )
            survival *= 1.0 - prob
    return steps


def add_salvage_action(
    model: ws3.forest.ForestModel,
    *,
    max_age: int | None = None,
    min_salvage_age: int = 60,
) -> ws3.forest.ForestModel:
    """Register the ``salvage`` action and its regeneration transition.

    Mirrors ``ws3.forest.ForestModel.add_null_action`` but the transition
    resets the stand to age 0 (regeneration after salvage), exactly like the
    harvest transition in the Woodstock ``.trn`` section. Operability is
    ``min_salvage_age <= age <= max_age``: below the threshold the salvage
    branch is closed, which both mirrors real practice (no salvage of
    regenerating stands) and bounds Model I tree growth.
    """
    mask = tuple("?" for _ in range(model.nthemes()))
    maxage = max_age if max_age is not None else model.max_age
    oper_expr = f"_age >= {min_salvage_age} and _age <= {maxage}"
    target = [(mask, 1.0, None, 0, None, None, None)]
    model.actions["salvage"] = ws3.forest.Action("salvage")
    model.oper_expr["salvage"] = {mask: oper_expr}
    model.transitions["salvage"] = {mask: {"": target}}
    for dtk in model.dtypes:
        dt = model.dtypes[dtk]
        dt.oper_expr["salvage"] = [oper_expr]
        dt.transitions["salvage", -1] = target
    for period in model.applied_actions:
        model.applied_actions[period]["salvage"] = {}
    return model


def apply_salvage_operability(
    model: ws3.forest.ForestModel,
    *,
    scenario: DisturbanceScenario,
    zone_by_au: dict[int, str],
) -> ws3.forest.ForestModel:
    """Restrict salvage operability to periods the scenario actually burns.

    Compiles the salvage action per development type, then nulls out periods
    with zero burn probability for that type's zone so the tree does not
    branch into (zero-volume) salvage decisions in fire-free periods. The
    age window (``min_salvage_age`` .. ``max_age``) comes from the
    ``oper_expr`` set by :func:`add_salvage_action`.
    """
    lookup = build_burn_prob_lookup(scenario, model.period_length)
    for dtk, dt in model.dtypes.items():
        au_id = int(dtk[2])
        if au_id not in zone_by_au:
            raise ValueError(f"development type {dtk} has no BEC zone for au_id {au_id}")
        zone = zone_by_au[au_id].upper()
        dt.compile_action("salvage")
        for period in model.periods:
            if lookup.get((zone, period), 0.0) == 0.0:
                dt.operability["salvage"][period] = None
    return model


def _compile_path_z(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    scenario: DisturbanceScenario,
    config: FireLpConfig,
    surface: EconomicSurface,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
) -> float:
    """Objective coefficient: discounted net cash flow along the path."""
    result = 0.0
    for step in path_fire_steps(fm, path, scenario=scenario, zone_by_au=config.zone_by_au):
        species = species_by_dtk.get(step.dtk, SpeciesClass.OTHER)
        if step.acode == "harvest":
            flow = harvest_cash_flow(
                surface, volume_m3=step.green_volume, area_ha=1.0, species=species
            )
        elif step.acode == "salvage":
            group = price_group_for_species(species)
            margin = sawlog_basis_salvage_margin(surface, group)
            flow = step.salvaged * margin
        else:
            continue
        discount = surface.discount_factor(step.period, period_length=fm.period_length)
        result += discount * flow * scenario.price_factor
    return result


def _compile_path_caa(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    scenario: DisturbanceScenario,
    config: FireLpConfig,
) -> dict[int, float]:
    """Even-flow row: post-fire green harvest volume by period."""
    result: dict[int, float] = {}
    for step in path_fire_steps(fm, path, scenario=scenario, zone_by_au=config.zone_by_au):
        if step.acode == "harvest":
            result[step.period] = step.green_volume
    return result


def _compile_path_salvage_vol(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    scenario: DisturbanceScenario,
    config: FireLpConfig,
) -> dict[int, float]:
    """Salvaged cohort volume by period (leaf row for schedule accounting)."""
    result: dict[int, float] = {}
    for step in path_fire_steps(fm, path, scenario=scenario, zone_by_au=config.zone_by_au):
        if step.acode == "salvage" and step.salvaged != 0.0:
            result[step.period] = step.salvaged
    return result


def _compile_path_salvageable_vol(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    scenario: DisturbanceScenario,
    config: FireLpConfig,
) -> dict[int, float]:
    """Salvageable (burned) cohort volume by period (the ceiling)."""
    result: dict[int, float] = {}
    for step in path_fire_steps(fm, path, scenario=scenario, zone_by_au=config.zone_by_au):
        if step.salvageable != 0.0:
            result[step.period] = step.salvageable
    return result


def _compile_path_salvage_feas(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    scenario: DisturbanceScenario,
    config: FireLpConfig,
) -> dict[int, float]:
    """Salvage-feasibility row: ``salvage_vol(t) - salvageable_vol(t)``.

    Structural by construction (a Model I path salvages at most its computed
    ceiling); the row makes the ceiling explicit and queryable from the
    solved problem (``salvage_vol - salvageable <= 0`` per period).
    """
    salvaged = _compile_path_salvage_vol(fm, path, scenario=scenario, config=config)
    salvageable = _compile_path_salvageable_vol(fm, path, scenario=scenario, config=config)
    return {
        t: salvaged.get(t, 0.0) - salvageable.get(t, 0.0)
        for t in sorted(set(salvaged) | set(salvageable))
    }


def add_fire_problem(
    model: ws3.forest.ForestModel,
    config: FireLpConfig,
    *,
    scenario: DisturbanceScenario,
    surface: EconomicSurface,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
) -> Any:
    """Add the fire-aware even-flow LP for one scenario and return the problem.

    The model must already have the ``salvage`` action registered
    (:func:`add_salvage_action`) and its operability applied
    (:func:`apply_salvage_operability`).
    """
    coeff_funcs: dict[str, Any] = {
        "z": lambda fm, path: _compile_path_z(
            fm,
            path,
            scenario=scenario,
            config=config,
            surface=surface,
            species_by_dtk=species_by_dtk,
        ),
        "cflw_hv": lambda fm, path: _compile_path_caa(fm, path, scenario=scenario, config=config),
        "salvage_vol": lambda fm, path: _compile_path_salvage_vol(
            fm, path, scenario=scenario, config=config
        ),
        "salvageable_vol": lambda fm, path: _compile_path_salvageable_vol(
            fm, path, scenario=scenario, config=config
        ),
        "salvage_feas": lambda fm, path: _compile_path_salvage_feas(
            fm, path, scenario=scenario, config=config
        ),
    }
    cflw_e = {
        "cflw_hv": (
            {p: config.flow_coefficient for p in model.periods},
            1,
        )
    }
    cgen_data: dict[str, dict[str, Any]] | None = None
    if "salvage" in config.action_codes:
        cgen_data = {
            "salvage_feas": {
                "lb": None,
                "ub": {t: 0.0 for t in model.periods},
            }
        }
    return model.add_problem(
        name=config.name,
        coeff_funcs=coeff_funcs,
        cflw_e=cflw_e,
        cgen_data=cgen_data,
        acodes=list(config.action_codes),
        sense=ws3.opt.SENSE_MAXIMIZE,
        mask=config.mask,
        workers=config.workers,
        verbose=False,
    )


def salvage_volumes_from_solution(
    model: ws3.forest.ForestModel,
    problem: Any,
    *,
    scenario: DisturbanceScenario,
    config: FireLpConfig,
) -> dict[str, dict[int, float]]:
    """Per-period salvaged and salvageable volumes from the LP solution.

    Iterates the Model I leaves and their stored ``salvage_vol`` /
    ``salvageable_vol`` rows, weighted by the solved path fractions. Returns
    ``{"salvaged": {period: m3}, "salvageable": {period: m3}}``.
    """
    salvaged: dict[int, float] = {t: 0.0 for t in model.periods}
    salvageable: dict[int, float] = {t: 0.0 for t in model.periods}
    for (_i, _j), tree in (problem.trees or {}).items():
        for path in tree.paths():
            leaf_id = path[-1].data("leaf_id")
            var = problem._vars.get(f"x_{leaf_id}")
            fraction = var.val if var is not None and var.val is not None else 0.0
            if fraction == 0.0:
                continue
            for t, vol in path[-1].data("salvage_vol").items():
                salvaged[t] += fraction * vol
            for t, vol in path[-1].data("salvageable_vol").items():
                salvageable[t] += fraction * vol
    return {"salvaged": salvaged, "salvageable": salvageable}


def solve_fire_lp(
    model: ws3.forest.ForestModel,
    problem: Any,
    *,
    scenario: DisturbanceScenario,
    config: FireLpConfig,
) -> pd.DataFrame:
    """Solve the fire-aware LP, apply the schedule, return per-period results.

    Extends the deterministic result frame (period, harvest area/volume,
    growing stock) with the salvage area/volume columns and the post-solve
    salvage-feasibility accounting (salvaged vs salvageable per period).
    """
    frame = solve_even_flow(model, problem)
    frame["salvage_area_ha"] = [
        model.compile_product(p, "1.", acode="salvage") for p in model.periods
    ]
    accounting = salvage_volumes_from_solution(model, problem, scenario=scenario, config=config)
    frame["salvage_volume_m3"] = [accounting["salvaged"].get(p, 0.0) for p in model.periods]
    frame["salvageable_volume_m3"] = [accounting["salvageable"].get(p, 0.0) for p in model.periods]
    return frame


__all__ = [
    "FireLpConfig",
    "FirePathStep",
    "add_fire_problem",
    "add_salvage_action",
    "apply_salvage_operability",
    "build_burn_prob_lookup",
    "path_fire_steps",
    "salvage_volumes_from_solution",
    "solve_fire_lp",
]
