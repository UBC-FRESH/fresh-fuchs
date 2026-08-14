"""Public-safe synthetic instance for tests, examples, and orchestration.

A tiny hand-built Woodstock-format landscape (two analysis units, one
managed / one unmanaged stand on AU1, a managed and an unmanaged stand on
AU2) with smooth saturating yield curves. No annex bundle or private data
is required, so the whole pipeline (model build -> scenario -> inner LP ->
policy grid -> ranking) is reproducible end-to-end in CI.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from fresh_fuchs.instance.species import SpeciesClass
from fresh_fuchs.instance.types import InstanceConfig

# Same shape as ``fresh_fuchs.economy.npv.DevelopmentTypeKey``; declared
# locally so this module stays importable from ``fresh_fuchs.instance``
# without pulling in the economy layer (which imports back into
# ``fresh_fuchs.instance.species``) and creating a cycle.
DevelopmentTypeKey = tuple[str, str, str, str, str]

AU1 = 1
AU2 = 2
TSA = "29"

#: Zone assignment per analysis unit (MFRI zones used by the fire model).
SYNTHETIC_ZONE_BY_AU: dict[int, str] = {AU1: "SBPS", AU2: "IDF"}

#: Annual burn rate per zone (1/MFRI): SBPS 100 yr, IDF 200 yr.
SYNTHETIC_ZONE_BURN_RATES: dict[str, float] = {"SBPS": 0.01, "IDF": 0.005}


def _yield_curve(age: int, au: int, ifm: str) -> float:
    peak = 420.0 if ifm == "managed" else 350.0
    shape = 80.0 if au == AU1 else 110.0
    return float(peak * (1.0 - np.exp(-age / shape)))


def _curve_rows(au: int, ifm: str, curve_id: str) -> list[dict[str, object]]:
    rows = []
    for age in range(0, 301, 10):
        rows.append(
            {
                "tsa": TSA,
                "au_id": au,
                "stratum_code": f"au{au}",
                "si_level": "x",
                "ifm": ifm,
                "curve_id": curve_id,
                "age": age,
                "volume": _yield_curve(age, au, ifm),
            }
        )
    return rows


def build_synthetic_yields() -> pd.DataFrame:
    """Return the synthetic yield table (Woodstock ``.yld`` source)."""
    rows: list[dict[str, object]] = []
    rows += _curve_rows(AU1, "managed", "c1")
    rows += _curve_rows(AU1, "unmanaged", "c2")
    rows += _curve_rows(AU2, "managed", "c3")
    rows += _curve_rows(AU2, "unmanaged", "c4")
    return pd.DataFrame(rows)


def build_synthetic_areas() -> pd.DataFrame:
    """Return the synthetic area records (Woodstock ``.lan`` source).

    Ages are already 10-year ageclass midpoints (the bridge smashes raw
    fragment ages to midpoints), matching the post-``apply_retention_split``
    shape.
    """
    return pd.DataFrame(
        [
            {
                "tsa": TSA,
                "au_id": AU1,
                "ifm": "managed",
                "origin": "natural",
                "silv_state": "baseline",
                "age": 75,
                "area_ha": 100.0,
            },
            {
                "tsa": TSA,
                "au_id": AU1,
                "ifm": "managed",
                "origin": "planted",
                "silv_state": "baseline",
                "age": 35,
                "area_ha": 50.0,
            },
            {
                "tsa": TSA,
                "au_id": AU2,
                "ifm": "managed",
                "origin": "natural",
                "silv_state": "baseline",
                "age": 95,
                "area_ha": 80.0,
            },
            {
                "tsa": TSA,
                "au_id": AU2,
                "ifm": "unmanaged",
                "origin": "natural",
                "silv_state": "baseline",
                "age": 125,
                "area_ha": 200.0,
            },
        ]
    )


def synthetic_species_by_dtk() -> dict[DevelopmentTypeKey, SpeciesClass]:
    """Return the synthetic development-type-key -> species-class map.

    ws3 dtk = ``(tsa, ifm, au_id, origin, silv_state)`` with string values.
    AU1 is lodgepole pine, AU2 is Douglas-fir (managed) / other (unmanaged).
    """
    return {
        (TSA, "managed", str(AU1), "natural", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        (TSA, "managed", str(AU1), "planted", "baseline"): SpeciesClass.LODGEPOLE_PINE,
        (TSA, "managed", str(AU2), "natural", "baseline"): SpeciesClass.DOUGLAS_FIR,
        (TSA, "unmanaged", str(AU2), "natural", "baseline"): SpeciesClass.OTHER,
    }


def synthetic_instance_config(
    model_path: Path,
    *,
    horizon: int = 2,
    period_length: int = 10,
) -> InstanceConfig:
    """Return the synthetic :class:`InstanceConfig` (writes to ``model_path``)."""
    return InstanceConfig(
        model_name="synthetic",
        model_path=model_path,
        horizon=horizon,
        period_length=period_length,
        max_age=300,
        min_harvest_age=60,
    )


def build_synthetic_model(
    model_path: Path,
    *,
    horizon: int = 2,
    period_length: int = 10,
) -> tuple[InstanceConfig, list[Path]]:
    """Write the synthetic Woodstock model files to ``model_path``.

    Returns the config and the written file paths.
    """
    from fresh_fuchs.instance.woodstock import write_woodstock_files

    config = synthetic_instance_config(model_path, horizon=horizon, period_length=period_length)
    files = write_woodstock_files(
        areas=build_synthetic_areas(),
        yields=build_synthetic_yields(),
        config=config,
    )
    return config, list(files)


__all__ = [
    "AU1",
    "AU2",
    "SYNTHETIC_ZONE_BY_AU",
    "SYNTHETIC_ZONE_BURN_RATES",
    "TSA",
    "build_synthetic_areas",
    "build_synthetic_model",
    "build_synthetic_yields",
    "synthetic_instance_config",
    "synthetic_species_by_dtk",
]
