"""Shared synthetic fixtures: hand-built bundle tables, no annex data required.

The synthetic area/yield builders live in
:mod:`fresh_fuchs.instance.synthetic` (public-safe, reusable by the
orchestration provider and examples); they are re-exported here for the
existing tests.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fresh_fuchs.instance import InstanceConfig
from fresh_fuchs.instance.synthetic import (
    AU1,
    AU2,
    TSA,
    build_synthetic_areas,
    build_synthetic_yields,
)

__all__ = [
    "AU1",
    "AU2",
    "TSA",
    "build_synthetic_areas",
    "build_synthetic_yields",
]


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
