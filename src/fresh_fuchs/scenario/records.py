"""Scenario records and generator (Phase 3, P3.3).

``DisturbanceScenario`` carries a seed, per-period fire events by BEC zone
(annual burn rate x severity), and a price realization, plus provenance
through ``to_dict``. ``generate_scenarios`` draws each scenario's uncertainty
vector (P3.2 registry) under a derived seed and expands the deterministic
zone burn rates into per-period events.

The record shape mirrors ws3's ``StochasticScenario`` (name, probability,
``parameters``) as a naming/structure reference; nothing depends on the
gated solver surface of ``ws3.advanced_modeling``.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.scenario.distributions import (
    UncertaintyDimension,
    UncertaintyVector,
    draw_vector,
)
from fresh_fuchs.scenario.fire import DEFAULT_SEVERITY, severity_burned_fraction


class FireEvent(BaseModel):
    """One period-zone fire event.

    ``annual_burn_rate`` is the fraction of that period's exposed live
    volume burned per year (``zone rate x scenario burn multiplier``);
    ``severity`` sets the salvageable fraction (P3.1 ladder).
    """

    period: int = Field(ge=1, description="1-based LP period.")
    zone: str = Field(description="BEC zone of the burn.")
    annual_burn_rate: float = Field(
        ge=0, le=1, description="Fraction of exposed live volume burned per year."
    )
    severity: str = Field(default=DEFAULT_SEVERITY, description="Severity tier.")

    @model_validator(mode="after")
    def _validate_severity(self) -> FireEvent:
        severity_burned_fraction(self.severity)
        return self


class DisturbanceScenario(BaseModel):
    """One fire scenario for the inner LP (full foresight).

    ``events`` are the per-period per-zone burn events applied to the model;
    ``price_factor`` is carried for the fire + price vector (only fire is
    active in v0.1.0a1). ``to_dict`` follows the ws3 ``StochasticScenario``
    shape (name, probability, parameters).
    """

    name: str
    seed: int = Field(description="Master seed that generated this scenario.")
    probability: float = Field(gt=0, le=1, description="Scenario weight (1/n).")
    burn_rate_multiplier: float = Field(
        ge=0, description="Scenario-wide burn-rate multiplier applied to every period."
    )
    price_factor: float = Field(default=1.0, ge=0)
    severity: str = Field(default=DEFAULT_SEVERITY)
    events: tuple[FireEvent, ...] = Field(
        default_factory=tuple, description="Per-period per-zone burn events."
    )

    @model_validator(mode="after")
    def _validate_severity(self) -> DisturbanceScenario:
        severity_burned_fraction(self.severity)
        return self

    def to_dict(self) -> dict:
        """ws3 ``StochasticScenario``-style dict with parameters + provenance."""
        return {
            "name": self.name,
            "probability": self.probability,
            "parameters": {
                "seed": self.seed,
                "burn_rate_multiplier": self.burn_rate_multiplier,
                "price_factor": self.price_factor,
                "severity": self.severity,
                "events": [event.model_dump() for event in self.events],
            },
        }

    @classmethod
    def from_dict(cls, payload: dict) -> DisturbanceScenario:
        """Rebuild a scenario from a :meth:`to_dict` payload (round-trip)."""
        parameters = dict(payload["parameters"])
        events = parameters.pop("events")
        return cls(
            name=payload["name"], probability=payload["probability"], events=events, **parameters
        )


class ScenarioGenerationParams(BaseModel):
    """Inputs to ``generate_scenarios`` (provenance recorded on the catalogue)."""

    n_scenarios: int = Field(ge=1)
    master_seed: int = Field(description="Master seed; scenario i uses master_seed + i.")
    horizon: int = Field(ge=1, description="Number of LP periods.")
    period_length: int = Field(default=10, ge=1, description="Years per period.")
    zone_burn_rates: dict[str, float] = Field(
        description="Deterministic per-zone annual burn rates (fire module)."
    )
    vector: UncertaintyVector = Field(
        description="Uncertainty vector drawn per scenario (fire + price dimensions)."
    )
    severity: str = Field(default=DEFAULT_SEVERITY)
    provenance: Provenance


def build_scenario(
    *,
    index: int,
    params: ScenarioGenerationParams,
) -> DisturbanceScenario:
    """Build one scenario by drawing its uncertainty vector under its seed.

    Scenario ``i`` uses ``master_seed + i``; the draw is bit-stable under a
    fixed master seed. Events are expanded in deterministic order (sorted
    zones x periods 1..horizon) so a seed-fixed catalogue is reproducible.
    """
    seed = params.master_seed + index
    draws = draw_vector(params.vector, seed=seed)
    multiplier = float(draws[UncertaintyDimension.FIRE_BURN_RATE])
    price_factor = float(draws[UncertaintyDimension.PRICE])

    events: list[FireEvent] = []
    for zone in sorted(params.zone_burn_rates):
        for period in range(1, params.horizon + 1):
            events.append(
                FireEvent(
                    period=period,
                    zone=zone,
                    annual_burn_rate=params.zone_burn_rates[zone] * multiplier,
                    severity=params.severity,
                )
            )

    return DisturbanceScenario(
        name=f"scenario_{index:04d}",
        seed=seed,
        probability=1.0 / params.n_scenarios,
        burn_rate_multiplier=multiplier,
        price_factor=price_factor,
        severity=params.severity,
        events=tuple(events),
    )


def generate_scenarios(params: ScenarioGenerationParams) -> list[DisturbanceScenario]:
    """Generate the full scenario catalogue (deterministic under the master seed)."""
    return [build_scenario(index=i, params=params) for i in range(params.n_scenarios)]


def write_scenario_catalogue(
    scenarios: list[DisturbanceScenario],
    params: ScenarioGenerationParams,
    path: Path,
) -> Path:
    """Write the catalogue as JSON with provenance."""
    catalogue = {
        "catalogue": [scenario.to_dict() for scenario in scenarios],
        "provenance": {
            "source": params.provenance.source,
            "as_of": params.provenance.as_of,
            "master_seed": params.master_seed,
            "n_scenarios": params.n_scenarios,
            "horizon": params.horizon,
            "period_length": params.period_length,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalogue, indent=2, sort_keys=True))
    return path


__all__ = [
    "DisturbanceScenario",
    "FireEvent",
    "ScenarioGenerationParams",
    "build_scenario",
    "generate_scenarios",
    "write_scenario_catalogue",
]
