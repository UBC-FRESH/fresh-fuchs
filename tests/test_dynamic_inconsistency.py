"""Dynamic-inconsistency characterization test (Daugherty 1991).

Documents, on the public-safe synthetic instance, that the as-implemented
inner LP — maximize discounted NPV subject to an even-flow harvest-volume
constraint — is **dynamically inconsistent** (an open-loop formulation whose
tail a future planner re-solving from the realized state would not follow).

Method (sequential replanning):

1. Solve the open-loop NPV-max even-flow LP over horizon H.
2. Apply only period 1 of the compiled schedule (state advancement is real:
   the post-period-1 inventory departs from the pristine trajectory).
3. Re-solve a fresh NPV-max LP from the realized state over the remaining
   H-1 periods, holding the even-flow band at the **committed** period-1
   level (the same policy the original planner faced), discounting from the
   replanner's present (the "same goals").
4. Align replan period k with open-loop period k+1 and compare.

Findings recorded (synthetic instance, 5 x 10-yr horizon): the period-1->2
transition is followed, but the plan's periods 3-5 tail is not (~9.5%
volume divergence); and the divergence is **identical at 0% and 3%
discount**, i.e. on this instance the driver is the even-flow band's
replanning asymmetry, not the discount rate. See
`planning/dynamic-inconsistency-note.md`.

These are characterization tests: they encode the *observed* behaviour of
the current formulation as a tripwire, so a future change that alters the
inconsistency (e.g. a consistent-solution formulation) fails loudly and
forces a conscious review.
"""

from __future__ import annotations

from pathlib import Path

import ws3

from fresh_fuchs.economy import interior_surface
from fresh_fuchs.economy.cashflow import harvest_cash_flow
from fresh_fuchs.instance import bootstrap_model, prepare_optimization
from fresh_fuchs.instance.baseline import solve_even_flow
from fresh_fuchs.instance.species import SpeciesClass
from fresh_fuchs.instance.synthetic import (
    build_synthetic_model,
    synthetic_instance_config,
    synthetic_species_by_dtk,
)

H = 5
PERIOD_LENGTH = 10
FLOW_TOL = 0.05
SPECIES_BY_DTK = None  # resolved lazily (module-level dict is fine to share)


def _species_by_dtk():
    global SPECIES_BY_DTK
    if SPECIES_BY_DTK is None:
        SPECIES_BY_DTK = synthetic_species_by_dtk()
    return SPECIES_BY_DTK


def _build(tmp: Path, horizon: int):
    config = synthetic_instance_config(tmp / "model", horizon=horizon, period_length=PERIOD_LENGTH)
    build_synthetic_model(tmp / "model", horizon=horizon, period_length=PERIOD_LENGTH)
    return prepare_optimization(bootstrap_model(config), max_initial_age=300, config=config)


def _surface(rate: float):
    surface = interior_surface()
    discount = surface.discount.model_copy(update={"annual_rate": rate})
    return surface.model_copy(update={"discount": discount})


def _npv_problem(model, name, surface, anchor_vol=None):
    """NPV-max problem mirroring ``economy.npv.add_npv_problem``.

    The objective is discounted net cash flow (discount factors taken from the
    model's own period index, so a replanned sub-problem discounts from its
    own present). The even-flow band on harvest volume is either tied to this
    problem's period 1 (open-loop) or pinned to an absolute committed level
    (replan, via general lb/ub rows).
    """
    period_length = model.period_length
    species_by_dtk = _species_by_dtk()

    def coeff_c_z(fm, path):
        result = 0.0
        for t, n in enumerate(path, start=1):
            d = n.data()
            if fm.is_harvest(d["acode"]):
                vol = fm.compile_product(t, "totvol", d["acode"], [d["dtk"]], d["age"], coeff=False)
                sp = species_by_dtk.get(d["dtk"], SpeciesClass.OTHER)
                flow = harvest_cash_flow(surface, volume_m3=vol, area_ha=1.0, species=sp)
                result += surface.discount_factor(t, period_length=period_length) * flow
        return result

    def coeff_c_hv(fm, path):
        out: dict[int, float] = {}
        for t, n in enumerate(path, start=1):
            d = n.data()
            if d["acode"] == "harvest":
                vol = fm.compile_product(t, "totvol", d["acode"], [d["dtk"]], d["age"], coeff=False)
                if vol:
                    out[t] = vol
        return out

    coeff_funcs = {"z": coeff_c_z, "cflw_hv": coeff_c_hv}
    cflw_e = None
    cgen_data = None
    if anchor_vol is None:
        cflw_e = {"cflw_hv": ({p: FLOW_TOL for p in model.periods}, 1)}
    else:
        cgen_data = {
            "cflw_hv": {
                "lb": {p: (1 - FLOW_TOL) * anchor_vol for p in model.periods},
                "ub": {p: (1 + FLOW_TOL) * anchor_vol for p in model.periods},
            }
        }
    return model.add_problem(
        name=name,
        coeff_funcs=coeff_funcs,
        cflw_e=cflw_e,
        cgen_data=cgen_data,
        acodes=("null", "harvest"),
        sense=ws3.opt.SENSE_MAXIMIZE,
        mask=("?", "managed", "?", "?", "?"),
        workers=1,
        verbose=False,
    )


def _vols(df) -> dict[int, float]:
    return dict(zip(df["period"], df["harvest_volume_m3"]))


def _sequential_replan(tmp: Path, rate: float):
    """Return (open-loop volumes, replan volumes) aligned on absolute period."""
    surface = _surface(rate)
    # Open-loop over horizon H.
    model = _build(tmp, H)
    p0 = _npv_problem(model, "open", surface)
    df0 = solve_even_flow(model, p0)
    v0 = _vols(df0)
    committed = v0[1]

    # Replan: identical period-1 schedule applied to a fresh H-1 model, then
    # re-solve the remaining H-1 periods with the even-flow held at the
    # committed period-1 level.
    model2 = _build(tmp, H - 1)
    p0b = _npv_problem(model2, "open_tmp", surface)
    solve_even_flow(model2, p0b)
    sched = model2.compile_schedule(p0b)
    model2.reset()
    model2.apply_schedule(
        sched,
        max_period=1,
        force_integral_area=False,
        override_operability=False,
        fuzzy_age=False,
        recourse_enabled=False,
        verbose=False,
    )
    p1 = _npv_problem(model2, "replan", surface, anchor_vol=committed)
    df1 = solve_even_flow(model2, p1)
    v1 = _vols(df1)  # replan period k == absolute period k+1
    return v0, v1


def _max_tail_divergence(v0, v1) -> float:
    return max(
        abs(v0.get(k + 1, 0.0) - v1.get(k, 0.0))
        / max(abs(v0.get(k + 1, 0.0)), abs(v1.get(k, 0.0)), 1.0)
        for k in range(1, H)
    )


def test_open_loop_tail_is_not_followed_on_replan(tmp_path: Path) -> None:
    """The open-loop plan is dynamically inconsistent: its period-3+ tail is
    not what a future planner re-solving from the realized state chooses."""
    v0, v1 = _sequential_replan(tmp_path, rate=0.03)
    # The period-1 -> 2 transition IS followed (the immediate next period is
    # consistent); the inconsistency appears deeper in the tail.
    transition_diff = abs(v1[1] - v0[2]) / max(abs(v0[2]), 1.0)
    assert transition_diff < 0.01
    # The tail diverges materially (documented ~9.5% on this instance).
    assert _max_tail_divergence(v0, v1) > 0.05


def test_inconsistency_not_driven_by_discount_rate(tmp_path: Path) -> None:
    """On this instance the divergence is ~identical at 0% and 3% discount:
    the driver is the even-flow replanning asymmetry, not the discount rate.
    """
    v0_zero, v1_zero = _sequential_replan(tmp_path / "zero", rate=0.0)
    v0_disc, v1_disc = _sequential_replan(tmp_path / "disc", rate=0.03)
    div_zero = _max_tail_divergence(v0_zero, v1_zero)
    div_disc = _max_tail_divergence(v0_disc, v1_disc)
    # Both inconsistent, and the magnitudes match within a small tolerance.
    assert div_zero > 0.05
    assert div_disc > 0.05
    assert abs(div_zero - div_disc) < 0.01
