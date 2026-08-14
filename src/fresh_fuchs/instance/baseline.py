"""Deterministic baselines: volume-max even-flow LP and oldest-first heuristic.

Ports the tsa29mini ``profile_ws3_evenflow.py`` LP (maximize total harvest
volume on the managed land base with per-period harvest volume within
``flow_coefficient`` of period 1) and the demo notebook's priority-queue
oldest-first heuristic. These are the regression anchors for later phases.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import ws3.forest
import ws3.opt

from .types import BaselineConfig


def _compile_path_z(fm: ws3.forest.ForestModel, path: Any, expr: str) -> float:
    """Objective coefficient: total harvest volume along a prescription path."""
    result = 0.0
    for t, n in enumerate(path, start=1):
        d = n.data()
        if fm.is_harvest(d["acode"]):
            result += fm.compile_product(t, expr, d["acode"], [d["dtk"]], d["age"], coeff=False)
    return result


def _compile_path_caa(
    fm: ws3.forest.ForestModel,
    path: Any,
    expr: str,
    acodes: tuple[str, ...],
    mask: tuple[str, ...] | None,
) -> dict[int, float]:
    """Constraint coefficient: product by period for actions in ``acodes``."""
    result: dict[int, float] = {}
    for t, n in enumerate(path, start=1):
        d = n.data()
        if mask and not fm.match_mask(mask, d["dtk"]):
            continue
        if d["acode"] in acodes:
            result[t] = fm.compile_product(t, expr, d["acode"], [d["dtk"]], d["age"], coeff=False)
    return result


def add_even_flow_problem(
    model: ws3.forest.ForestModel,
    config: BaselineConfig,
    *,
    policy: Any = None,
    species_by_dtk: dict[Any, Any] | None = None,
) -> Any:
    """Add the volume-max even-flow LP to ``model`` and return the problem.

    With ``policy`` (a :class:`fresh_fuchs.outer.records.PolicyRecord`), the
    policy's composition/AAC general rows are folded into the problem.
    """
    expr = config.product

    def coeff_c_z(fm, path):
        return _compile_path_z(fm, path, expr)

    def coeff_c_caa(fm, path):
        return _compile_path_caa(fm, path, expr, ("harvest",), mask=None)

    coeff_funcs = {
        "z": coeff_c_z,
        "cflw_hv": coeff_c_caa,
    }
    cgen_data: dict[str, dict[str, Any]] | None = None
    if policy is not None:
        from fresh_fuchs.outer.policy import policy_cgen_data, policy_coeff_funcs

        if policy.composition_targets and species_by_dtk is None:
            raise ValueError("composition targets require species_by_dtk")
        coeff_funcs.update(policy_coeff_funcs(policy, species_by_dtk=species_by_dtk or {}))
        cgen_data = policy_cgen_data(
            policy, period_length=model.period_length, periods=model.periods
        )
    cflw_e = {
        "cflw_hv": (
            {p: config.flow_coefficient for p in model.periods},
            1,
        )
    }
    return model.add_problem(
        name=config.name,
        coeff_funcs=coeff_funcs,
        cflw_e=cflw_e,
        cgen_data=cgen_data,
        acodes=config.action_codes,
        sense=ws3.opt.SENSE_MAXIMIZE,
        mask=config.mask,
        workers=config.workers,
        verbose=False,
    )


def solve_even_flow(
    model: ws3.forest.ForestModel,
    problem: Any,
) -> pd.DataFrame:
    """Solve the LP, compile and apply the schedule, return per-period results."""
    problem.solve(verbose=False)
    schedule = model.compile_schedule(problem)
    model.reset()
    model.apply_schedule(
        schedule,
        force_integral_area=False,
        override_operability=False,
        fuzzy_age=False,
        recourse_enabled=False,
        verbose=False,
        compile_c_ycomps=True,
    )
    return pd.DataFrame(
        {
            "period": model.periods,
            "harvest_area_ha": [
                model.compile_product(p, "1.", acode="harvest") for p in model.periods
            ],
            "harvest_volume_m3": [
                model.compile_product(p, "totvol", acode="harvest") for p in model.periods
            ],
            "growing_stock_m3": [model.inventory(p, "totvol") for p in model.periods],
        }
    )


def run_oldest_first_heuristic(
    model: ws3.forest.ForestModel,
) -> pd.DataFrame:
    """Priority-queue oldest-first harvest on even-flow per-DT targets.

    Deterministic: per development type the target is ``(1 / MAI) *
    period_length * area``; within a period oldest ages are harvested first.
    """
    period_length = model.period_length
    dt_targets: dict[Any, float] = {}
    for dtk, dt in model.dtypes.items():
        mai = dt.ycomp("totvol").mai()
        yield_at_zero = mai.ytp().lookup(0)
        rotation = yield_at_zero if yield_at_zero != 0 else 100
        area = dt.area(period=0)
        dt_targets[dtk] = (1.0 / rotation) * period_length * area

    period_areas: list[float] = []
    period_vols: list[float] = []
    for period in range(1, model.horizon + 1):
        total_area = 0.0
        total_vol = 0.0
        for dtk, dt in model.dtypes.items():
            target = dt_targets[dtk]
            oper_lower, oper_upper = dt.operability["harvest"][period]
            candidates = [
                (age, area)
                for age, area in dt._areas[period - 1].items()
                if area > 0 and oper_lower <= age <= oper_upper
            ]
            candidates.sort(key=lambda x: -x[0])
            harvested_area = 0.0
            harvested_vol = 0.0
            for age, avail_area in candidates:
                if harvested_area >= target:
                    break
                take = min(avail_area, target - harvested_area)
                if take <= 0:
                    continue
                vol_per_ha = dt.ycomp("totvol")[age]
                model.apply_action(
                    dtype_key=dtk,
                    acode="harvest",
                    period=period,
                    age=age,
                    area=take,
                    compile_c_ycomps=True,
                )
                harvested_area += take
                harvested_vol += take * vol_per_ha
            total_area += harvested_area
            total_vol += harvested_vol
        model.commit_actions(period=period)
        period_areas.append(total_area)
        period_vols.append(total_vol)
        model.grow()

    return pd.DataFrame(
        {
            "period": range(1, model.horizon + 1),
            "harvest_area_ha": period_areas,
            "harvest_volume_m3": period_vols,
        }
    )


def summarize(results: pd.DataFrame, *, period_length: int) -> dict[str, float]:
    """Anchor metrics from a per-period results frame."""
    return {
        "total_harvested_area_ha": float(results["harvest_area_ha"].sum()),
        "total_harvested_volume_m3": float(results["harvest_volume_m3"].sum()),
        "mean_harvest_volume_m3_per_period": float(results["harvest_volume_m3"].mean()),
        "mean_annual_harvest_m3_per_yr": float(results["harvest_volume_m3"].mean()) / period_length,
    }
