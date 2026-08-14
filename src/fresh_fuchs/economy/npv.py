"""NPV objective wiring for the inner Model I LP (P2.5).

The ws3 even-flow LP machinery maximizes a per-prescription ``z``
coefficient. For the NPV objective, ``z`` is the discounted net cash flow of
a prescription path: at each harvest node the per-ha volume times the
species' green net revenue (minus the optional per-ha replant charge),
discounted to period 0 with the surface discount rate. The even-flow band
(constraint) stays on harvest volume -- the AAC proxy -- exactly as in the
volume-max baseline.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import ws3.forest
import ws3.opt

from fresh_fuchs.instance.species import SpeciesClass

from .cashflow import harvest_cash_flow
from .types import EconomicSurface, NpvConfig

DevelopmentTypeKey = tuple[str, str, str, str, str]


def species_by_dtk_from_areas(areas: pd.DataFrame) -> dict[DevelopmentTypeKey, SpeciesClass]:
    """Map ws3 development-type keys to species classes from area records.

    The ws3 dtk is the tuple ``(tsa, ifm, au_id, origin, silv_state)`` with
    string theme values (AU values are written as strings in the ``.lan``
    section). ``areas`` must carry the ``species`` column (added by
    :func:`fresh_fuchs.instance.bundle.apply_retention_split`).
    """
    if "species" not in areas.columns:
        raise ValueError(
            "areas is missing the 'species' column; pass species_by_au to "
            "apply_retention_split when building the area records"
        )
    mapping: dict[DevelopmentTypeKey, SpeciesClass] = {}
    for _, row in areas.iterrows():
        key: DevelopmentTypeKey = (
            str(row["tsa"]),
            str(row["ifm"]),
            str(row["au_id"]),
            str(row["origin"]),
            str(row["silv_state"]),
        )
        mapping.setdefault(key, SpeciesClass(row["species"]))
    return mapping


def _compile_path_npv(
    fm: ws3.forest.ForestModel,
    path: Any,
    *,
    surface: EconomicSurface,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
    period_length: int,
) -> float:
    """Objective coefficient: discounted net cash flow along a prescription path."""
    result = 0.0
    for t, n in enumerate(path, start=1):
        d = n.data()
        if fm.is_harvest(d["acode"]):
            vol_per_ha = fm.compile_product(
                t, "totvol", d["acode"], [d["dtk"]], d["age"], coeff=False
            )
            species = species_by_dtk.get(d["dtk"], SpeciesClass.OTHER)
            flow = harvest_cash_flow(surface, volume_m3=vol_per_ha, area_ha=1.0, species=species)
            result += surface.discount_factor(t, period_length=period_length) * flow
    return result


def _compile_path_caa(
    fm: ws3.forest.ForestModel,
    path: Any,
    expr: str,
    acodes: tuple[str, ...],
) -> dict[int, float]:
    """Constraint coefficient: product by period for actions in ``acodes``."""
    result: dict[int, float] = {}
    for t, n in enumerate(path, start=1):
        d = n.data()
        if d["acode"] in acodes:
            result[t] = fm.compile_product(t, expr, d["acode"], [d["dtk"]], d["age"], coeff=False)
    return result


def add_npv_problem(
    model: ws3.forest.ForestModel,
    config: NpvConfig,
    *,
    surface: EconomicSurface,
    species_by_dtk: dict[DevelopmentTypeKey, SpeciesClass],
) -> Any:
    """Add the NPV-max even-flow LP to ``model`` and return the problem."""
    period_length = model.period_length

    def coeff_c_z(fm: ws3.forest.ForestModel, path: Any) -> float:
        return _compile_path_npv(
            fm,
            path,
            surface=surface,
            species_by_dtk=species_by_dtk,
            period_length=period_length,
        )

    def coeff_c_caa(fm: ws3.forest.ForestModel, path: Any) -> dict[int, float]:
        return _compile_path_caa(fm, path, config.product, ("harvest",))

    coeff_funcs = {
        "z": coeff_c_z,
        "cflw_hv": coeff_c_caa,
    }
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
        cgen_data=None,
        acodes=config.action_codes,
        sense=ws3.opt.SENSE_MAXIMIZE,
        mask=config.mask,
        workers=config.workers,
        verbose=False,
    )


def solve_npv(
    model: ws3.forest.ForestModel,
    problem: Any,
) -> pd.DataFrame:
    """Solve the NPV LP, compile and apply the schedule, return per-period results.

    Reuses the same schedule application path as the volume-max baseline
    (:func:`fresh_fuchs.instance.baseline.solve_even_flow`), so the resulting
    frames share schema.
    """
    from fresh_fuchs.instance.baseline import solve_even_flow

    return solve_even_flow(model, problem)


__all__ = [
    "add_npv_problem",
    "solve_npv",
    "species_by_dtk_from_areas",
]
