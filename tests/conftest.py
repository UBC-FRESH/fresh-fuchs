"""Shared synthetic fixtures: hand-built bundle tables, no annex data required."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from fresh_fuchs.instance import InstanceConfig

AU1 = 1
AU2 = 2
TSA = "29"


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
    rows: list[dict[str, object]] = []
    rows += _curve_rows(AU1, "managed", "c1")
    rows += _curve_rows(AU1, "unmanaged", "c2")
    rows += _curve_rows(AU2, "managed", "c3")
    rows += _curve_rows(AU2, "unmanaged", "c4")
    return pd.DataFrame(rows)


def build_synthetic_areas() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "tsa": TSA,
                "au_id": AU1,
                "ifm": "managed",
                "origin": "natural",
                "silv_state": "baseline",
                "age": 70,
                "area_ha": 100.0,
            },
            {
                "tsa": TSA,
                "au_id": AU1,
                "ifm": "managed",
                "origin": "planted",
                "silv_state": "baseline",
                "age": 30,
                "area_ha": 50.0,
            },
            {
                "tsa": TSA,
                "au_id": AU2,
                "ifm": "managed",
                "origin": "natural",
                "silv_state": "baseline",
                "age": 90,
                "area_ha": 80.0,
            },
            {
                "tsa": TSA,
                "au_id": AU2,
                "ifm": "unmanaged",
                "origin": "natural",
                "silv_state": "baseline",
                "age": 120,
                "area_ha": 200.0,
            },
        ]
    )


@pytest.fixture()
def synthetic_bundle(tmp_path: Path) -> tuple[InstanceConfig, pd.DataFrame, pd.DataFrame]:
    config = InstanceConfig(
        model_name="synthetic",
        model_path=tmp_path,
        horizon=3,
        period_length=10,
        max_age=300,
        min_harvest_age=60,
        max_harvest_age=300,
    )
    return config, build_synthetic_yields(), build_synthetic_areas()
