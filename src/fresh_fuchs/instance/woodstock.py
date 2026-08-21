"""Woodstock-format section writing and ws3 ``ForestModel`` bootstrap.

Ports the tsa29mini demo/``profile_ws3_evenflow.py`` bootstrap: write the
``.lan``/``.are``/``.yld``/``.act``/``.trn`` sections from the long-format
yields/areas tables, load them into ``ws3.forest.ForestModel``, and prepare
the optimization environment (null action with horizon-long operability).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import ws3.forest

from .replant import SpeciesClass, replant_au_id
from .types import InstanceConfig
from .yields_multi import MultiSpeciesYieldTable

INTENDED_THEME_COUNT = 5  # TSA, IFM, AU, ORIGIN, SILV_STATE


def _landscape_section(
    config: InstanceConfig,
    au_ids: list[int],
    *,
    replant_au_ids: list[str] | None = None,
) -> str:
    tsa_block = "\n".join(str(tsa) for tsa in config.tsa_list) + "\n"
    au_lines = [f"{au}\n" for au in au_ids]
    if replant_au_ids:
        au_lines.extend(f"{rau}\n" for rau in sorted(replant_au_ids))
    au_block = "".join(au_lines)
    return (
        "*THEME TSA\n"
        f"{tsa_block}\n"
        "*THEME IFM\n"
        "managed\n"
        "unmanaged\n\n"
        "*THEME AU\n"
        f"{au_block}\n"
        "*THEME ORIGIN\n"
        "natural\n"
        "planted\n\n"
        "*THEME SILV_STATE\n"
        "baseline\n"
        "cc_pl\n\n"
    )


def write_woodstock_files(
    *,
    areas: pd.DataFrame,
    yields: pd.DataFrame,
    config: InstanceConfig,
    replant_yields: MultiSpeciesYieldTable | None = None,
    replant_species: tuple[SpeciesClass, ...] | None = None,
) -> list[Path]:
    """Write the five Woodstock-format sections into ``config.model_path``.

    Parameters
    ----------
    areas :
        Long-format area inventory (columns: tsa, ifm, au_id, origin,
        silv_state, age, area_ha).
    yields :
        Long-format yield curves (columns: tsa, au_id, ifm, curve_id,
        age, volume).
    config :
        Instance configuration.
    replant_yields :
        Multi-species yield table for replant AUs. When provided together
        with *replant_species*, replant AU codes and their yield curves are
        appended to the landscape and yields sections.
    replant_species :
        Species classes to create replant AUs for.
    """
    model_path = Path(config.model_path)
    model_path.mkdir(parents=True, exist_ok=True)
    au_ids = sorted(areas["au_id"].unique().tolist())

    # Build replant AU code list and map for yield lookup.
    replant_au_ids: list[str] | None = None
    if replant_yields is not None and replant_species:
        replant_au_ids = sorted(
            replant_au_id(au, sp)
            for au in au_ids
            for sp in replant_species
        )

    (model_path / f"{config.model_name}.lan").write_text(
        _landscape_section(config, au_ids, replant_au_ids=replant_au_ids)
    )

    with open(model_path / f"{config.model_name}.are", "w") as f:
        for _, row in areas.iterrows():
            if float(row["area_ha"]) <= 0:
                continue
            f.write(
                f"*A {row['tsa']} {row['ifm']} {row['au_id']} {row['origin']} "
                f"{row['silv_state']} {int(row['age'])} {float(row['area_ha']):.6f}\n"
            )

    with open(model_path / f"{config.model_name}.yld", "w") as f:
        # Original yield curves.
        for (tsa, au_id, ifm, curve_id), group in yields.groupby(
            ["tsa", "au_id", "ifm", "curve_id"]
        ):
            f.write(f"*Y ? {ifm} {au_id} ? ?\n")
            f.write("_AGE totvol\n")
            for _, row in group.sort_values("age").iterrows():
                f.write(f"{int(row['age'])} {float(row['volume']):.6f}\n")
            f.write("\n")

        # Replant AU yield curves.
        if replant_yields is not None and replant_species:
            for au in au_ids:
                for sp in replant_species:
                    curve = replant_yields.get(au, sp)
                    if curve is None:
                        continue
                    rau = replant_au_id(au, sp)
                    f.write(f"*Y ? managed {rau} ? ?\n")
                    f.write("_AGE totvol\n")
                    for age, vol in zip(curve.ages, curve.volumes):
                        f.write(f"{age} {vol:.6f}\n")
                    f.write("\n")

    with open(model_path / f"{config.model_name}.act", "w") as f:
        f.write("*ACTION harvest Y\n")
        f.write("*OPERABLE harvest\n")
        f.write(
            f"? ? ? ? ? _AGE >= {config.min_harvest_age} and _AGE <= {config.max_harvest_age}\n"
        )

    with open(model_path / f"{config.model_name}.trn", "w") as f:
        f.write("*CASE harvest\n")
        f.write("*SOURCE ? ? ? ? ?\n")
        f.write("*TARGET ? ? ? ? ? 100 _AGE 0\n")

    return [
        model_path / f"{config.model_name}.{suffix}"
        for suffix in ("lan", "are", "yld", "act", "trn")
    ]


def bootstrap_model(config: InstanceConfig) -> ws3.forest.ForestModel:
    """Load the Woodstock sections into a ws3 ``ForestModel``."""
    model = ws3.forest.ForestModel(
        model_name=config.model_name,
        model_path=str(config.model_path),
        base_year=config.base_year,
        horizon=config.horizon,
        period_length=config.period_length,
        max_age=config.max_age,
    )
    model.import_landscape_section()
    model.import_areas_section()
    model.import_yields_section()
    model.import_actions_section()
    model.import_transitions_section()
    model.compile_actions()
    model.reset()

    if model.nthemes() != INTENDED_THEME_COUNT:
        raise ValueError(
            f"expected exactly {INTENDED_THEME_COUNT} themes (TSA, IFM, AU, ORIGIN, "
            f"SILV_STATE), got {model.nthemes()}; no LU/land-use theme is part of the "
            "Woodstock dataset"
        )
    return model


def prepare_optimization(
    model: ws3.forest.ForestModel,
    *,
    max_initial_age: int,
    config: InstanceConfig,
    replant_species: tuple[SpeciesClass, ...] | None = None,
) -> ws3.forest.ForestModel:
    """Add the null action, extend operability, and optionally register replant actions.

    Initial fragment ages can exceed ``max_age`` (tsa29mini max ~436) and
    unharvested stands age through the horizon, so the null action's
    operability upper bound must extend to ``max_initial_age +
    horizon * period_length``.

    When *replant_species* is provided, registers species-switching
    harvest actions (``harvest_SX``, ``harvest_PL``, etc.) that transition
    stands to a replant AU at age 0.
    """
    from .replant import add_replant_actions

    null_max_age = max_initial_age + config.horizon * config.period_length
    null_oe = f"_age >= 0 and _age <= {null_max_age}"
    wildcard_mask = tuple(["?" for _ in range(model.nthemes())])
    model.add_null_action()
    model.oper_expr["null"] = {wildcard_mask: null_oe}
    for dt in model.dtypes.values():
        dt._max_age = null_max_age
        dt.oper_expr["null"] = [null_oe]
        dt.operability.pop("null", None)

    model.reset_actions()
    model.actions["harvest"].is_harvest = True

    if replant_species:
        add_replant_actions(
            model,
            target_species=replant_species,
            min_harvest_age=config.min_harvest_age,
            max_harvest_age=config.max_harvest_age,
        )

    return model
