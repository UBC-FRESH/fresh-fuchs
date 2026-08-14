"""Fire-dynamics tests (P3.1).

Parity with the fresh-salvage reference: constants, zone mapping, and the
annual harvest -> fire -> salvage -> decay ordering are asserted against
reference values carried in this repo (fresh-salvage is reference only, not
importable here).
"""

from __future__ import annotations

import pandas as pd
import pytest

from fresh_fuchs.scenario.fire import (
    ANNUAL_BURN_RATE_BY_ZONE,
    DEFAULT_BURNED_DECAY_RATE,
    DEFAULT_SEVERITY,
    MFRI_YEARS_BY_ZONE,
    SEVERITY_TO_BURNED_FRAC,
    FireDynamicsError,
    UnknownBurnRateError,
    annual_burn_rate,
    annual_burn_rate_for_stratum,
    bec_zone_from_stratum,
    burn_influx,
    burned_volume_after,
    live_volume_after,
    load_burn_rate_by_au,
    period_burn_probability,
    salvageable_volume,
    severity_burned_fraction,
    simulate_cohort_years,
)


def test_mfri_and_burn_rate_reference_values() -> None:
    assert MFRI_YEARS_BY_ZONE == {
        "SBPS": 100,
        "IDF": 200,
        "MS": 150,
        "ESSF": 200,
        "ICH": 250,
        "SBS": 125,
    }
    assert ANNUAL_BURN_RATE_BY_ZONE["SBPS"] == pytest.approx(0.01)
    assert ANNUAL_BURN_RATE_BY_ZONE["IDF"] == pytest.approx(0.005)
    assert DEFAULT_BURNED_DECAY_RATE == pytest.approx(0.85)


def test_severity_ladder_reference_values() -> None:
    assert SEVERITY_TO_BURNED_FRAC == {
        "Unburned": 0.0,
        "Low": 0.30,
        "Moderate": 0.60,
        "High": 0.85,
    }
    assert severity_burned_fraction("Moderate") == pytest.approx(0.60)
    assert severity_burned_fraction("unburned") == pytest.approx(0.0)
    assert DEFAULT_SEVERITY == "Moderate"


def test_bec_zone_from_stratum() -> None:
    assert bec_zone_from_stratum("SBPS_PLI") == "SBPS"
    assert bec_zone_from_stratum("idf_fd") == "IDF"
    assert annual_burn_rate_for_stratum("SBPS_PLI") == pytest.approx(0.01)
    with pytest.raises(UnknownBurnRateError):
        bec_zone_from_stratum("NOPE")
    with pytest.raises(UnknownBurnRateError):
        annual_burn_rate_for_stratum("MISSING_ZONE_PLI")


def test_annual_burn_rate_fails_fast_on_unmapped_zone() -> None:
    with pytest.raises(UnknownBurnRateError):
        annual_burn_rate("XYY")
    with pytest.raises(UnknownBurnRateError):
        annual_burn_rate("")


def test_load_burn_rate_by_au(tmp_path) -> None:
    au_table = pd.DataFrame(
        [
            {"au_id": 2901000, "stratum_code": "SBPS_PLI"},
            {"au_id": 2902000, "stratum_code": "IDF_FD"},
        ]
    )
    au_table.to_csv(tmp_path / "au_table.csv", index=False)
    rates = load_burn_rate_by_au(tmp_path)
    assert rates == {2901000: 0.01, 2902000: 0.005}


def test_load_burn_rate_by_au_unmapped_zone_fails(tmp_path) -> None:
    au_table = pd.DataFrame([{"au_id": 1, "stratum_code": "XYY_PL"}])
    au_table.to_csv(tmp_path / "au_table.csv", index=False)
    with pytest.raises(UnknownBurnRateError):
        load_burn_rate_by_au(tmp_path)


def test_load_burn_rate_by_au_missing_columns(tmp_path) -> None:
    pd.DataFrame([{"au_id": 1}]).to_csv(tmp_path / "au_table.csv", index=False)
    with pytest.raises(ValueError):
        load_burn_rate_by_au(tmp_path)


def test_period_burn_probability() -> None:
    # SBPS over a 10-year period: 1 - 0.99**10 ~ 0.0956.
    assert period_burn_probability(0.01, 10) == pytest.approx(1 - 0.99**10)
    assert period_burn_probability(0.0, 10) == pytest.approx(0.0)
    with pytest.raises(FireDynamicsError):
        period_burn_probability(1.5, 10)
    with pytest.raises(FireDynamicsError):
        period_burn_probability(0.01, 0)


def test_burn_influx() -> None:
    assert burn_influx(100.0, 0.01) == pytest.approx(1.0)
    with pytest.raises(FireDynamicsError):
        burn_influx(-1.0, 0.01)


def test_salvageable_volume() -> None:
    assert salvageable_volume(5.0, 2.0) == pytest.approx(7.0)
    with pytest.raises(FireDynamicsError):
        salvageable_volume(-1.0, 2.0)


def test_live_and_burned_balances() -> None:
    assert live_volume_after(100.0, 10.0, 0.9) == pytest.approx(89.1)
    # B[t] = (B[t-1] + BURN_IN - S) * 0.85
    assert burned_volume_after(0.0, 0.9, 0.0, 0.85) == pytest.approx(0.765)
    assert burned_volume_after(0.0, 0.9, 0.9, 0.85) == pytest.approx(0.0)
    with pytest.raises(FireDynamicsError):
        burned_volume_after(0.0, 0.9, 1.0, 0.85)


def test_simulate_cohort_years_single_year() -> None:
    states = simulate_cohort_years(
        initial_live=100.0,
        burn_rate=0.01,
        harvest_schedule=[10.0],
        salvage_schedule=[0.0],
    )
    state = states[0]
    assert state.year == 1
    assert state.exposed == pytest.approx(90.0)
    assert state.burn_influx == pytest.approx(0.9)
    assert state.live_after == pytest.approx(89.1)
    assert state.salvageable == pytest.approx(0.9)
    assert state.decayed == pytest.approx(0.135)
    assert state.burned_after == pytest.approx(0.765)


def test_simulate_cohort_years_salvage_ceiling() -> None:
    states = simulate_cohort_years(
        initial_live=200.0,
        burn_rate=0.005,
        harvest_schedule=[20.0, 20.0],
        salvage_schedule=[0.9, 0.3],
    )
    assert len(states) == 2
    assert states[0].burn_influx == pytest.approx(0.9)
    # Year 1: burned after = (0.9 - 0.9) * 0.85 = 0.0
    assert states[0].burned_after == pytest.approx(0.0)
    # Year 2: influx = 0.005 * (live_before - 20); live_before = 179.1
    assert states[1].live_before == pytest.approx(179.1)
    assert states[1].burn_influx == pytest.approx(0.005 * (179.1 - 20.0))


def test_simulate_cohort_years_rejects_infeasible_schedules() -> None:
    with pytest.raises(FireDynamicsError):
        simulate_cohort_years(
            initial_live=10.0,
            burn_rate=0.01,
            harvest_schedule=[20.0],
            salvage_schedule=[0.0],
        )
    with pytest.raises(FireDynamicsError):
        simulate_cohort_years(
            initial_live=10.0,
            burn_rate=0.01,
            harvest_schedule=[0.0],
            salvage_schedule=[5.0],
        )
    with pytest.raises(FireDynamicsError):
        simulate_cohort_years(
            initial_live=10.0,
            burn_rate=0.01,
            harvest_schedule=[1.0, 1.0],
            salvage_schedule=[1.0],
        )
