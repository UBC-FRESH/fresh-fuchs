"""Fire dynamics for the tsa29mini instance (Phase 3, P3.1).

Burn rates, zone mapping, severity, and the annual dynamics ordering follow
the fresh-salvage fire module (``fresh-salvage/src/fresh_salvage/fire.py``)
as the calibration reference. Per the reuse boundary in ``AGENTS.md`` the
fresh-salvage constants are reference only — no import — so the values are
carried here with provenance and parity-tested against the reference.

Zone mapping
------------
tsa29mini AU tables carry ``stratum_code`` values of the form
``{BEC_ZONE}_{leading_species}`` (``SBPS_PLI``, ``IDF_FD``, ...). The BEC
zone prefix maps each AU to a mean fire return interval; only SBPS (MFRI
100) and IDF (MFRI 200) occur in the mini bundle, but the full ladder is
carried so a future bundle with more zones works unchanged.

Annual burn probability of a development type is ``1 / MFRI`` of its BEC
zone. A 10-year LP period therefore sees a burn fraction
``1 - (1 - R)^period_length``.

Annual dynamics (per 1-year timestep ``t``, per cohort)
-------------------------------------------------------
Ordering within one timestep is harvest -> fire -> salvage -> decay
(fresh-salvage contract):

- exposed-to-burn volume ``V_rem[t] = V[t-1] - H[t]`` (harvest first);
- burn influx ``BURN_IN[t] = R * V_rem[t]`` with ``R = 1 / MFRI[zone]``;
- live balance ``V[t] = V[t-1] - H[t] - BURN_IN[t]``;
- salvage feasibility ``S[t] <= B[t-1] + BURN_IN[t]``;
- burned inventory ``B[t] = (B[t-1] + BURN_IN[t] - S[t]) * decay_rate`` with
  ``decay_rate = 0.85``.

Severity
--------
The burned fraction of live volume converted to salvageable stock follows the
fresh-salvage severity ladder (Unburned 0.0, Low 0.30, Moderate 0.60, High
0.85). The tsa29mini bundle has no burn-severity polygon data, so severity
is a scenario parameter (P3.3) with ``Moderate`` as the default. All helpers
are pure functions: no I/O, no hidden state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

# Mean fire return interval (years) per BEC zone. Reference:
# fresh-salvage/src/fresh_salvage/fire.py ``MFRI_YEARS_BY_ZONE``.
MFRI_YEARS_BY_ZONE: dict[str, int] = {
    "SBPS": 100,
    "IDF": 200,
    "MS": 150,
    "ESSF": 200,
    "ICH": 250,
    "SBS": 125,
}

# Annual burn probability per BEC zone: R[zone] = 1 / MFRI[zone].
ANNUAL_BURN_RATE_BY_ZONE: dict[str, float] = {
    zone: 1.0 / mfri for zone, mfri in MFRI_YEARS_BY_ZONE.items()
}

# Annual retention fraction of unsalvaged burned volume (decay 0.15/yr).
# Reference: fresh-salvage ``DEFAULT_BURNED_DECAY_RATE``.
DEFAULT_BURNED_DECAY_RATE = 0.85

# Burn severity -> fraction of live volume that becomes salvageable.
# Reference: fresh-salvage ``SEVERITY_TO_BURNED_FRAC``.
SEVERITY_TO_BURNED_FRAC: dict[str, float] = {
    "Unburned": 0.0,
    "Low": 0.30,
    "Moderate": 0.60,
    "High": 0.85,
}

# tsa29mini has no burn-severity polygon data; the scenario defaults to the
# mid ladder tier.
DEFAULT_SEVERITY = "Moderate"

# Float dust tolerated when checking harvest/salvage schedule feasibility.
SCHEDULE_TOLERANCE = 1e-9


class UnknownBurnRateError(ValueError):
    """Raised when a BEC zone or stratum has no MFRI table entry."""


class FireDynamicsError(ValueError):
    """Raised when a fire-dynamics input or schedule is infeasible."""


@dataclass(frozen=True)
class FireYearState:
    """Trusted state snapshot of one cohort after one annual timestep.

    Volumes share the caller's unit (m3 or fractions of the initial standing
    volume). ``live_after``/``burned_after`` feed the next year's
    ``live_before``/``burned_before``.
    """

    year: int
    live_before: float
    harvested: float
    exposed: float
    burn_influx: float
    burned_before: float
    salvageable: float
    salvaged: float
    decayed: float
    live_after: float
    burned_after: float


def annual_burn_rate(bec_zone: str) -> float:
    """Return the annual burn probability ``1 / MFRI`` of a BEC zone.

    Zone matching is case-insensitive. Raises :class:`UnknownBurnRateError`
    for blank or unmapped zones: an unknown fire regime must halt the
    pipeline, never silently default to a neighbouring zone's rate.
    """
    zone = str(bec_zone).strip().upper()
    if not zone:
        raise UnknownBurnRateError("BEC zone must be a non-empty string")
    if zone not in ANNUAL_BURN_RATE_BY_ZONE:
        known = ", ".join(sorted(ANNUAL_BURN_RATE_BY_ZONE))
        raise UnknownBurnRateError(f"no MFRI entry for BEC zone {zone!r}; mapped zones: {known}")
    return ANNUAL_BURN_RATE_BY_ZONE[zone]


def bec_zone_from_stratum(stratum_code: str) -> str:
    """Extract the BEC zone prefix of a tsa29mini stratum code.

    Stratum codes are ``{bec_zone}_{leading_species}`` (``SBPS_PLI`` ->
    ``SBPS``, ``IDF_FD`` -> ``IDF``). Raises :class:`UnknownBurnRateError`
    for malformed codes.
    """
    text = str(stratum_code).strip()
    prefix, separator, _species = text.partition("_")
    if not separator or not prefix:
        raise UnknownBurnRateError(
            f"stratum code {stratum_code!r} does not follow '{{bec_zone}}_{{leading_species}}'"
        )
    return prefix.upper()


def annual_burn_rate_for_stratum(stratum_code: str) -> float:
    """Return the annual burn probability of a tsa29mini stratum code."""
    return annual_burn_rate(bec_zone_from_stratum(stratum_code))


def load_burn_rate_by_au(bundle_dir: Path) -> dict[int, float]:
    """Read ``au_table.csv`` and return ``au_id -> annual burn rate``.

    Uses the ``au_id`` and ``stratum_code`` columns; each AU's BEC zone
    prefix sets its burn probability. Unmapped zones raise
    :class:`UnknownBurnRateError` naming the offending codes.
    """
    au_table = pd.read_csv(bundle_dir / "au_table.csv")
    if "au_id" not in au_table.columns or "stratum_code" not in au_table.columns:
        raise ValueError(
            "au_table.csv must provide 'au_id' and 'stratum_code' columns to "
            "derive the fire zone classification"
        )
    rates: dict[int, float] = {}
    for au_id, stratum in zip(au_table["au_id"].astype(int), au_table["stratum_code"], strict=True):
        rates[int(au_id)] = annual_burn_rate_for_stratum(stratum)
    return rates


def period_burn_probability(burn_rate: float, period_length: int) -> float:
    """Return the probability of at least one burn over a period.

    ``1 - (1 - R) ** period_length`` with ``R`` the annual burn probability
    and ``period_length`` in years (tsa29mini LP periods are 10 years).
    """
    _require_fraction(burn_rate, "burn_rate")
    if period_length < 1:
        raise FireDynamicsError(f"period_length must be >= 1: {period_length}")
    return 1.0 - (1.0 - burn_rate) ** period_length


def severity_burned_fraction(severity: str) -> float:
    """Return the salvageable fraction of live volume for a severity tier.

    The tsa29mini bundle has no burn-severity polygons, so the scenario
    picks a tier from the reference ladder. Matching is case-insensitive;
    unknown tiers fail fast.
    """
    text = str(severity).strip().lower()
    for tier, fraction in SEVERITY_TO_BURNED_FRAC.items():
        if tier.lower() == text:
            return fraction
    known = ", ".join(sorted(SEVERITY_TO_BURNED_FRAC))
    raise FireDynamicsError(f"unknown severity {severity!r}; known tiers: {known}")


def burn_influx(remaining_live: float, burn_rate: float) -> float:
    """Return ``BURN_IN[t] = burn_rate * V_rem[t]`` (fire after harvest)."""
    _require_fraction(burn_rate, "burn_rate")
    if remaining_live < 0.0:
        raise FireDynamicsError(f"exposed live volume cannot be negative: {remaining_live}")
    return burn_rate * remaining_live


def salvageable_volume(burned_before: float, influx: float) -> float:
    """Return the salvage ceiling ``B[t-1] + BURN_IN[t]`` for one year."""
    if burned_before < 0.0:
        raise FireDynamicsError(f"burned inventory cannot be negative: {burned_before}")
    if influx < 0.0:
        raise FireDynamicsError(f"burn influx cannot be negative: {influx}")
    return burned_before + influx


def live_volume_after(live_before: float, harvested: float, influx: float) -> float:
    """Return the live balance ``V[t] = V[t-1] - H[t] - BURN_IN[t]``."""
    if live_before < 0.0:
        raise FireDynamicsError(f"live volume cannot be negative: {live_before}")
    if harvested < 0.0:
        raise FireDynamicsError(f"harvested volume cannot be negative: {harvested}")
    if influx < 0.0:
        raise FireDynamicsError(f"burn influx cannot be negative: {influx}")
    return live_before - harvested - influx


def burned_volume_after(
    burned_before: float,
    influx: float,
    salvaged: float,
    decay_rate: float,
) -> float:
    """Return ``B[t] = (B[t-1] + BURN_IN[t] - S[t]) * decay_rate``."""
    _require_fraction(decay_rate, "decay_rate")
    if salvaged < 0.0:
        raise FireDynamicsError(f"salvaged volume cannot be negative: {salvaged}")
    ceiling = salvageable_volume(burned_before, influx)
    if salvaged > ceiling + SCHEDULE_TOLERANCE:
        raise FireDynamicsError(
            f"salvage {salvaged} exceeds the available burned inventory {ceiling}"
        )
    unsalvaged = ceiling - salvaged
    return unsalvaged * decay_rate


def simulate_cohort_years(
    *,
    initial_live: float,
    burn_rate: float,
    harvest_schedule: list[float] | tuple[float, ...],
    salvage_schedule: list[float] | tuple[float, ...],
    decay_rate: float = DEFAULT_BURNED_DECAY_RATE,
    initial_burned: float = 0.0,
) -> list[FireYearState]:
    """Simulate the annual harvest -> fire -> salvage -> decay ordering.

    Pure driver over the primitives above: given per-year harvest and
    salvage schedules (same length, same unit as ``initial_live``), return
    one :class:`FireYearState` per year. Raises :class:`FireDynamicsError`
    when a schedule harvests more than the standing live volume or salvages
    more than the on-hand burned inventory (beyond float dust).
    """
    _require_fraction(burn_rate, "burn_rate")
    _require_fraction(decay_rate, "decay_rate")
    if initial_live < 0.0:
        raise FireDynamicsError(f"initial live volume cannot be negative: {initial_live}")
    if initial_burned < 0.0:
        raise FireDynamicsError(f"initial burned inventory cannot be negative: {initial_burned}")
    if len(harvest_schedule) != len(salvage_schedule):
        raise FireDynamicsError(
            "harvest and salvage schedules must have equal length: "
            f"{len(harvest_schedule)} != {len(salvage_schedule)}"
        )

    states: list[FireYearState] = []
    live = float(initial_live)
    burned = float(initial_burned)
    for year_index, (harvested, salvaged) in enumerate(
        zip(harvest_schedule, salvage_schedule, strict=True), start=1
    ):
        if harvested < -SCHEDULE_TOLERANCE:
            raise FireDynamicsError(f"year {year_index}: negative harvest {harvested}")
        if salvaged < -SCHEDULE_TOLERANCE:
            raise FireDynamicsError(f"year {year_index}: negative salvage {salvaged}")
        harvested = max(0.0, harvested)
        salvaged = max(0.0, salvaged)
        if harvested > live + SCHEDULE_TOLERANCE:
            raise FireDynamicsError(
                f"year {year_index}: harvest {harvested} exceeds the standing live volume {live}"
            )
        harvested = min(harvested, live)
        influx = burn_influx(live - harvested, burn_rate)
        salvageable = salvageable_volume(burned, influx)
        if salvaged > salvageable + SCHEDULE_TOLERANCE:
            raise FireDynamicsError(
                f"year {year_index}: salvage {salvaged} exceeds the available "
                f"burned inventory {salvageable}"
            )
        salvaged = min(salvaged, salvageable)
        next_live = live_volume_after(live, harvested, influx)
        next_burned = burned_volume_after(burned, influx, salvaged, decay_rate)
        states.append(
            FireYearState(
                year=year_index,
                live_before=live,
                harvested=harvested,
                exposed=live - harvested,
                burn_influx=influx,
                burned_before=burned,
                salvageable=salvageable,
                salvaged=salvaged,
                decayed=(salvageable - salvaged) * (1.0 - decay_rate),
                live_after=next_live,
                burned_after=next_burned,
            )
        )
        live = next_live
        burned = next_burned
    return states


def _require_fraction(value: float, name: str) -> None:
    """Fail fast when a rate/retention parameter lies outside ``[0, 1]``."""
    if not 0.0 <= value <= 1.0:
        raise FireDynamicsError(f"{name} must lie in [0, 1]: {value}")


__all__ = [
    "ANNUAL_BURN_RATE_BY_ZONE",
    "DEFAULT_BURNED_DECAY_RATE",
    "DEFAULT_SEVERITY",
    "MFRI_YEARS_BY_ZONE",
    "SCHEDULE_TOLERANCE",
    "SEVERITY_TO_BURNED_FRAC",
    "FireDynamicsError",
    "FireYearState",
    "UnknownBurnRateError",
    "annual_burn_rate",
    "annual_burn_rate_for_stratum",
    "bec_zone_from_stratum",
    "burn_influx",
    "burned_volume_after",
    "live_volume_after",
    "load_burn_rate_by_au",
    "period_burn_probability",
    "salvageable_volume",
    "severity_burned_fraction",
    "simulate_cohort_years",
]
