"""BTC replant curve store tests (P6.7): loader, resolution order, and
real-curve wiring into replant DTKs.

All fixtures are synthetic/hand-written — no annex bundle or TIPSY runtime
required.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fresh_fuchs.instance import (
    SpeciesClass,
    bootstrap_model,
    prepare_optimization,
)
from fresh_fuchs.instance.replant import replant_au_id
from fresh_fuchs.instance.woodstock import write_woodstock_files
from fresh_fuchs.instance.yields_multi import (
    MultiSpeciesYieldTable,
    YieldCurve,
    build_multi_species_yields,
    load_replant_curves_from_btc,
)

# ---------------------------------------------------------------------------
# Hand-written synthetic BTC fixtures
# ---------------------------------------------------------------------------

CURVE_ROWS = []
for fid, base in ((700010, 100.0), (700011, 200.0), (700012, 50.0)):
    CURVE_ROWS.extend(
        {"AU": fid, "Age": age, "Yield": base * (age / 100.0)}
        for age in range(0, 351, 10)
    )

MANIFEST_ROWS = [
    {"feature_id": 700010, "au_id": 1, "target_species": "PL", "stratum_code": "SBPS_PLI",
     "si_level": "L"},
    {"feature_id": 700011, "au_id": 1, "target_species": "SW", "stratum_code": "SBPS_PLI",
     "si_level": "L"},
    {"feature_id": 700012, "au_id": 1, "target_species": "FD", "stratum_code": "SBPS_PLI",
     "si_level": "L"},
]


def _write_btc_fixtures(tmp_path):
    curves_csv = tmp_path / "tipsy_curves.csv"
    manifest_csv = tmp_path / "manifest.csv"
    pd.DataFrame(CURVE_ROWS).to_csv(curves_csv, index=False)
    pd.DataFrame(MANIFEST_ROWS).to_csv(manifest_csv, index=False)
    return curves_csv, manifest_csv


class TestLoadReplantCurvesFromBtc:
    def test_loads_keyed_by_au_and_species(self, tmp_path) -> None:
        curves_csv, manifest_csv = _write_btc_fixtures(tmp_path)
        table = load_replant_curves_from_btc(curves_csv, manifest_csv)
        assert table.curve_count == 3
        pl = table.get(1, SpeciesClass.LODGEPOLE_PINE)
        sw = table.get(1, SpeciesClass.SPRUCE)
        fd = table.get(1, SpeciesClass.DOUGLAS_FIR)
        assert pl is not None and sw is not None and fd is not None
        assert pl.volume_at_age(100) == pytest.approx(100.0)
        # SW manifest code maps to SpeciesClass.SPRUCE
        assert sw.volume_at_age(100) == pytest.approx(200.0)
        assert fd.volume_at_age(100) == pytest.approx(50.0)

    def test_max_age_clips(self, tmp_path) -> None:
        curves_csv, manifest_csv = _write_btc_fixtures(tmp_path)
        table = load_replant_curves_from_btc(curves_csv, manifest_csv, max_age=300)
        assert table.get(1, SpeciesClass.LODGEPOLE_PINE).ages[-1] == 300

    def test_missing_column_raises(self, tmp_path) -> None:
        curves_csv, manifest_csv = _write_btc_fixtures(tmp_path)
        bad = tmp_path / "bad.csv"
        pd.DataFrame(CURVE_ROWS).rename(columns={"Yield": "Volume"}).to_csv(bad, index=False)
        with pytest.raises(ValueError, match="Yield"):
            load_replant_curves_from_btc(bad, manifest_csv)

    def test_unmapped_species_raises(self, tmp_path) -> None:
        one = tmp_path / "one.csv"
        pd.DataFrame([r for r in CURVE_ROWS if r["AU"] == 700010]).to_csv(one, index=False)
        bad = tmp_path / "bad_manifest.csv"
        pd.DataFrame([{**MANIFEST_ROWS[0], "target_species": "XX"}]).to_csv(bad, index=False)
        with pytest.raises(ValueError, match="unmapped target_species"):
            load_replant_curves_from_btc(one, bad)


# ---------------------------------------------------------------------------
# Resolution order: real BTC store > synthetic fallback
# ---------------------------------------------------------------------------


class TestResolutionOrder:
    def test_real_curve_wins_and_missing_warns(self, tmp_path) -> None:
        curves_csv, manifest_csv = _write_btc_fixtures(tmp_path)
        store = load_replant_curves_from_btc(curves_csv, manifest_csv)
        au_table = pd.DataFrame({"au_id": [1], "si_level": ["L"]})
        with pytest.warns(UserWarning, match="synthetic"):
            table = build_multi_species_yields(
                au_table=au_table,
                replant_curves=store,
                target_species=list(SpeciesClass),  # incl. OTHER (not in store)
            )
        # real curve for PL (from store), synthetic for OTHER
        assert table.get(1, SpeciesClass.LODGEPOLE_PINE).volume_at_age(100) == pytest.approx(100.0)
        synth_ot = table.get(1, SpeciesClass.OTHER)
        assert synth_ot is not None
        # Chapman-Richards synthetic, not the store curve
        assert synth_ot.volume_at_age(100) != pytest.approx(100.0)

    def test_no_store_is_pure_synthetic_no_warning(self) -> None:
        au_table = pd.DataFrame({"au_id": [1], "si_level": ["L"]})
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            table = build_multi_species_yields(au_table=au_table)
        assert table.curve_count == len(list(SpeciesClass))

    def test_store_overlay_restricts_to_target_species(self, tmp_path) -> None:
        curves_csv, manifest_csv = _write_btc_fixtures(tmp_path)
        store = load_replant_curves_from_btc(curves_csv, manifest_csv)
        au_table = pd.DataFrame({"au_id": [1], "si_level": ["L"]})
        table = build_multi_species_yields(
            au_table=au_table,
            replant_curves=store,
            target_species=[SpeciesClass.SPRUCE],  # only SX requested
        )
        assert table.curve_count == 1
        assert table.get(1, SpeciesClass.SPRUCE).volume_at_age(100) == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# Replant DTKs pick up real curves from the yields stash
# ---------------------------------------------------------------------------


class TestReplantDtkRealCurves:
    def test_precreated_dtk_uses_stashed_real_curve(self, synthetic_bundle) -> None:
        config, yields, areas = synthetic_bundle
        # Distinctive real curve: 777 m3/ha at age 100 for AU 1 + SPRUCE.
        real_curve = YieldCurve(
            ages=tuple(range(0, 351, 10)),
            volumes=tuple(0.0 if a == 0 else 777.0 for a in range(0, 351, 10)),
        )
        replant_table = MultiSpeciesYieldTable(
            curves={(1, SpeciesClass.SPRUCE): real_curve}
        )
        write_woodstock_files(
            areas=areas,
            yields=yields,
            config=config,
            replant_yields=replant_table,
            replant_species=(SpeciesClass.SPRUCE,),
        )
        model = prepare_optimization(
            bootstrap_model(config), max_initial_age=300, config=config,
            replant_species=(SpeciesClass.SPRUCE,),
        )
        rkey = ("29", "managed", replant_au_id("1", SpeciesClass.SPRUCE), "natural", "baseline")
        assert rkey in model.dtypes
        ycomp = model.dtypes[rkey].ycomp("totvol")
        assert ycomp is not None
        assert float(ycomp[100]) == pytest.approx(777.0)

    def test_precreated_dtk_falls_back_to_source_curves(self, synthetic_bundle) -> None:
        """No replant yields written -> placeholder copy of source curves."""
        config, yields, areas = synthetic_bundle
        write_woodstock_files(areas=areas, yields=yields, config=config)
        model = prepare_optimization(
            bootstrap_model(config), max_initial_age=300, config=config,
            replant_species=(SpeciesClass.SPRUCE,),
        )
        rkey = ("29", "managed", "1-SX", "natural", "baseline")
        source = model.dtypes[("29", "managed", "1", "natural", "baseline")]
        assert np.isclose(
            float(model.dtypes[rkey].ycomp("totvol")[100]),
            float(source.ycomp("totvol")[100]),
        )
