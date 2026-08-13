"""Phase 1 tests: bundle bridge, retention split, model bootstrap, baselines.

All fixtures are synthetic (no annex bundle, no femic/geopandas runtime
requirement): hand-built yields and area frames feed the Woodstock writer,
ws3 bootstrap, even-flow LP, and oldest-first heuristic directly.
"""

from __future__ import annotations

import pandas as pd
import pytest

import fresh_fuchs.instance as instance
from fresh_fuchs.instance import (
    BaselineConfig,
    InstanceConfig,
    add_even_flow_problem,
    apply_retention_split,
    bootstrap_model,
    build_model,
    prepare_optimization,
    run_oldest_first_heuristic,
    solve_even_flow,
    summarize,
)
from fresh_fuchs.instance.woodstock import write_woodstock_files


def _build_optimized(config, model):
    prepare_optimization(model, max_initial_age=300, config=config)
    return model


def test_write_woodstock_files_creates_sections(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    paths = write_woodstock_files(areas=areas, yields=yields, config=config)

    assert len(paths) == 5
    for path in paths:
        assert path.exists()

    lan = (config.model_path / "synthetic.lan").read_text()
    assert "*THEME TSA\n29\n" in lan
    assert "managed\n" in lan and "unmanaged\n" in lan
    assert "natural\n" in lan and "planted\n" in lan
    assert "*THEME AU\n1\n2\n" in lan

    act = (config.model_path / "synthetic.act").read_text()
    assert "_AGE >= 60" in act and "_AGE <= 300" in act

    trn = (config.model_path / "synthetic.trn").read_text()
    assert "*CASE harvest" in trn

    are = (config.model_path / "synthetic.are").read_text()
    assert are.count("*A ") == 4


def test_bootstrap_model_conserves_area(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    model = bootstrap_model(config)

    expected = float(areas["area_ha"].sum())
    assert model.inventory(period=0) == pytest.approx(expected, abs=0.01)
    assert model.nthemes() == 5
    assert set(model.actions.keys()) == {"harvest"}


def test_even_flow_lp_optimal_and_smooth(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    model = _build_optimized(config, bootstrap_model(config))

    problem = add_even_flow_problem(model, BaselineConfig())
    results = solve_even_flow(model, problem)

    assert problem.status() == "optimal"
    assert len(results) == config.horizon
    assert not results["harvest_volume_m3"].isna().any()
    assert (results["harvest_volume_m3"] >= 0).all()

    first = results["harvest_volume_m3"].iloc[0]
    if first > 0:
        assert ((results["harvest_volume_m3"] / first - 1.0).abs() <= 0.05 + 1e-6).all()


def test_oldest_first_heuristic_deterministic(synthetic_bundle) -> None:
    config, yields, areas = synthetic_bundle
    write_woodstock_files(areas=areas, yields=yields, config=config)
    model = _build_optimized(config, bootstrap_model(config))

    first = run_oldest_first_heuristic(model)
    second = run_oldest_first_heuristic(model)

    pd.testing.assert_frame_equal(first, second)
    assert (first["harvest_area_ha"] >= 0).all()
    assert (first["harvest_volume_m3"] >= 0).all()


def test_summarize_anchors(synthetic_bundle) -> None:
    config, _, _ = synthetic_bundle
    results = pd.DataFrame(
        {
            "period": [1, 2, 3],
            "harvest_area_ha": [10.0, 20.0, 30.0],
            "harvest_volume_m3": [100.0, 200.0, 300.0],
        }
    )
    summary = summarize(results, period_length=config.period_length)
    assert summary["total_harvested_volume_m3"] == pytest.approx(600.0)
    assert summary["mean_annual_harvest_m3_per_yr"] == pytest.approx(20.0)


def test_retention_split_conserves_area() -> None:
    fragments = pd.DataFrame(
        [
            {
                "TSA": "29",
                "AU": 1,
                "ORIGIN": "natural",
                "SILV_STATE": "baseline",
                "F_AGE": 70,
                "IFM": "managed",
                "area_ha": 100.0,
                "retention": 0.2,
            },
            {
                "tsa": "29",
                "AU": 2,
                "ORIGIN": "natural",
                "SILV_STATE": "baseline",
                "F_AGE": 90,
                "IFM": "unmanaged",
                "area_ha": 50.0,
                "retention": 0.5,
            },
            {
                "tsa": "29",
                "AU": 3,
                "ORIGIN": "natural",
                "SILV_STATE": "baseline",
                "F_AGE": 40,
                "IFM": "managed",
                "area_ha": 40.0,
                "retention": 0.0,
            },
        ]
    )
    areas = apply_retention_split(fragments)

    assert areas["area_ha"].sum() == pytest.approx(190.0)
    managed = areas[areas["ifm"] == "managed"]
    unmanaged = areas[areas["ifm"] == "unmanaged"]
    assert managed["area_ha"].sum() == pytest.approx(100.0 * 0.8 + 40.0)
    assert unmanaged["area_ha"].sum() == pytest.approx(100.0 * 0.2 + 50.0)


def test_build_model_requires_bundle_paths(tmp_path) -> None:
    config = InstanceConfig(model_path=tmp_path)
    with pytest.raises(ValueError, match="bundle_dir and .*fragments_path"):
        build_model(config)


def test_instance_module_docstring() -> None:
    assert instance.__doc__
