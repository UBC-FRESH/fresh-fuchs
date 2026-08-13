"""Typed configuration records for the instance and model integration layer."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class InstanceConfig(BaseModel):
    """Inputs and constants for building a ws3 ``ForestModel`` from a bundle.

    The femic tsa29mini bundle is the v0.1.0a1 case study (see
    ``planning/v0.1.0a1-plan.md``): base year 2026, 30 periods of 10 years,
    Patchworks-compatible max age 300 and minimum harvest age 60.
    """

    model_name: str = Field(
        default="tsa29mini",
        description="Name handed to ws3; becomes the prefix of the Woodstock files.",
    )
    model_path: Path = Field(
        default=Path("outputs") / "tsa29mini" / "ws3_woodstock_bootstrap_model",
        description="Directory where Woodstock-format sections are written.",
    )
    bundle_dir: Path | None = Field(
        default=None,
        description="Bundle directory holding au_table.csv, curve_table.csv, "
        "curve_points_table.csv. Required for real-bundle builds.",
    )
    fragments_path: Path | None = Field(
        default=None,
        description="Path to the fragments shapefile (AREA_HA/RETENTION/IFM/AU...). "
        "Required for real-bundle builds; synthetic builds can supply an "
        "areas frame directly.",
    )
    tsa_list: list[str] = Field(default_factory=lambda: ["29"])
    base_year: int = Field(default=2026)
    horizon: int = Field(default=30, description="Number of periods.")
    period_length: int = Field(default=10, description="Years per period.")
    max_age: int = Field(default=300, description="Patchworks-compatible max age.")
    min_harvest_age: int = Field(default=60)
    max_harvest_age: int = Field(default=300)
    workers: int = Field(default=1, ge=1)


class BaselineConfig(BaseModel):
    """Specification of the deterministic volume-max even-flow baseline.

    Mirrors the reference profiler: maximize total harvest volume on the
    managed land base with harvest volume per period constrained to within
    ``flow_coefficient`` of the first-period harvest volume.
    """

    name: str = Field(default="evenflow-max-hv-managed")
    sense: Literal["maximize"] = "maximize"
    flow_coefficient: float = Field(default=0.05, gt=0.0)
    mask: tuple[str, str, str, str, str] = Field(default=("?", "managed", "?", "?", "?"))
    product: str = Field(default="totvol")
    action_codes: tuple[str, str] = Field(default=("null", "harvest"))
    workers: int = Field(default=1, ge=1)
