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

from .types import InstanceConfig


def _landscape_section(config: InstanceConfig, au_ids: list[int]) -> str:
    tsa_block = "\n".join(str(tsa) for tsa in config.tsa_list) + "\n"
    au_block = "".join(f"{au}\n" for au in au_ids)
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
) -> list[Path]:
    """Write the five Woodstock-format sections into ``config.model_path``."""
    model_path = Path(config.model_path)
    model_path.mkdir(parents=True, exist_ok=True)
    au_ids = sorted(areas["au_id"].unique().tolist())

    (model_path / f"{config.model_name}.lan").write_text(_landscape_section(config, au_ids))

    with open(model_path / f"{config.model_name}.are", "w") as f:
        for _, row in areas.iterrows():
            if float(row["area_ha"]) <= 0:
                continue
            f.write(
                f"*A {row['tsa']} {row['ifm']} {row['au_id']} {row['origin']} "
                f"{row['silv_state']} {int(row['age'])} {float(row['area_ha']):.6f}\n"
            )

    with open(model_path / f"{config.model_name}.yld", "w") as f:
        for (tsa, au_id, ifm, curve_id), group in yields.groupby(
            ["tsa", "au_id", "ifm", "curve_id"]
        ):
            f.write(f"*Y ? {ifm} {au_id} ? ?\n")
            f.write("_AGE totvol\n")
            for _, row in group.sort_values("age").iterrows():
                f.write(f"{int(row['age'])} {float(row['volume']):.6f}\n")
            f.write("\n")

    with open(model_path / f"{config.model_name}.act", "w") as f:
        f.write("*ACTION harvest Y\n")
        f.write("*OPERABLE harvest\n")
        f.write(
            f"? ? ? ? ? _AGE >= {config.min_harvest_age} "
            f"and _AGE <= {config.max_harvest_age}\n"
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
    return model


def prepare_optimization(
    model: ws3.forest.ForestModel,
    *,
    max_initial_age: int,
    config: InstanceConfig,
) -> ws3.forest.ForestModel:
    """Add the null action and extend operability across the full horizon.

    Initial fragment ages can exceed ``max_age`` (tsa29mini max ~436) and
    unharvested stands age through the horizon, so the null action's
    operability upper bound must extend to ``max_initial_age +
    horizon * period_length``.
    """
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
    return model
