"""Risk metrics over per-policy NPV samples (Phase 4, P4.3).

Downside measures are empirical by default (no distributional assumption).
``RiskReport`` records point estimates, empirical VaR/CVaR/shortfall, and
an explicitly labeled Gaussian fitted comparison (the notes' extreme-event
checks): the Gaussian numbers are a comparison, not the metric.

Definitions (all consistent with "loss = low NPV"):

- ``value_at_risk(alpha)``: the ``alpha``-quantile of the NPV sample
  (``np.quantile``, ``inverted_cdf``): with probability ``1 - alpha`` the
  NPV falls at or below this level.
- ``conditional_value_at_risk(alpha)``: the mean of the worst
  ``floor((1 - alpha) * n)`` observations (the ``1 - alpha`` worst tail).
- ``shortfall_probability(threshold)``: the fraction of observations
  strictly below ``threshold``.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict, Field

from fresh_fuchs.economy.types import Provenance
from fresh_fuchs.outer.grid import GridRunRecord
from fresh_fuchs.outer.records import PolicyRecord


def expected_npv(sample: npt.ArrayLike) -> float:
    """Arithmetic mean of the NPV sample (E[NPV])."""
    return float(np.mean(sample))


def npv_volatility(sample: npt.ArrayLike, *, ddof: int = 1) -> float:
    """Sample standard deviation of the NPV sample (CV source of risk)."""
    return float(np.std(sample, ddof=ddof))


def value_at_risk(sample: npt.ArrayLike, alpha: float) -> float:
    """Empirical ``alpha``-quantile of the NPV sample.

    The alpha-quantile is the level below which the worst ``1 - alpha``
    probability mass sits; lower NPV is the tail we care about.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly in (0, 1)")
    return float(np.quantile(sample, alpha, method="inverted_cdf"))


def conditional_value_at_risk(sample: npt.ArrayLike, alpha: float) -> float:
    """Empirical CVaR: mean of the worst ``1 - alpha`` tail of the sample.

    The tail is the ``k = max(1, floor((1 - alpha) * n))`` smallest
    observations, so CVaR is well-defined even for small samples.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly in (0, 1)")
    values = np.asarray(sample, dtype=float)
    if values.size == 0:
        raise ValueError("sample must not be empty")
    k = max(1, int(np.floor((1.0 - alpha) * values.size)))
    ordered = np.sort(values)
    return float(np.mean(ordered[:k]))


def shortfall_probability(sample: npt.ArrayLike, threshold: float) -> float:
    """Fraction of observations strictly below ``threshold`` (P[NPV < t])."""
    values = np.asarray(sample, dtype=float)
    if values.size == 0:
        raise ValueError("sample must not be empty")
    return float(np.mean(values < threshold))


class RiskMetrics(BaseModel):
    """Empirical point estimates and tail metrics for one NPV sample."""

    model_config = ConfigDict(frozen=True)

    n: int = Field(description="Sample size.")
    alpha: float = Field(description="Tail probability used for VaR/CVaR.")
    expected_npv: float
    npv_volatility: float
    value_at_risk: float
    conditional_value_at_risk: float
    shortfall_probability: float | None = Field(
        default=None, description="P[NPV < shortfall_threshold], if a threshold was given."
    )


class GaussianComparison(BaseModel):
    """Gaussian fitted tail metrics — a comparison, not the reported metric."""

    model_config = ConfigDict(frozen=True)

    fitted_mean: float
    fitted_std: float
    value_at_risk: float
    conditional_value_at_risk: float
    provenance: Provenance


def _normal_quantile(alpha: float) -> float:
    """Standard Normal quantile Phi^{-1}(alpha) via Newton on erf.

    Initial guess from Abramowitz & Stegun 26.2.23 (|error| ~ 1e-3),
    refined by Newton's method on f(z) = erf(z/sqrt(2)) - p; converges to
    machine precision in a few iterations. Avoids a scipy dependency.
    """
    import math

    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly in (0, 1)")
    p = min(alpha, 1.0 - alpha)  # tail probability in (0, 0.5]
    t = math.sqrt(-2.0 * math.log(p))
    magnitude = t - (2.30753 + 0.27061 * t) / (1.0 + 0.99229 * t + 0.04481 * t * t)
    z = magnitude if alpha >= 0.5 else -magnitude
    for _ in range(6):
        f = math.erf(z / math.sqrt(2.0)) - (2.0 * alpha - 1.0)
        fp = math.sqrt(2.0 / math.pi) * math.exp(-(z**2) / 2.0)
        z -= f / fp
    return z


def gaussian_tail_metrics(
    sample: npt.ArrayLike,
    alpha: float,
    *,
    provenance: Provenance,
) -> GaussianComparison:
    """Analytic VaR/CVaR for a Normal fitted to the sample's moments.

    For NPV ~ Normal(mu, sigma): VaR = mu + sigma * z_alpha and
    CVaR = mu - sigma * phi(z_alpha) / (1 - alpha), with
    z_alpha = Phi^{-1}(alpha) and phi the standard Normal density.
    """
    import math

    values = np.asarray(sample, dtype=float)
    if values.size == 0:
        raise ValueError("sample must not be empty")
    mu = float(np.mean(values))
    sigma = float(np.std(values, ddof=1))
    z = _normal_quantile(alpha)
    phi_z = math.exp(-(z**2) / 2.0) / math.sqrt(2.0 * math.pi)
    return GaussianComparison(
        fitted_mean=mu,
        fitted_std=sigma,
        value_at_risk=mu + sigma * z,
        conditional_value_at_risk=mu - sigma * phi_z / (1.0 - alpha),
        provenance=provenance,
    )


class RiskReport(BaseModel):
    """Risk profile of one policy's NPV distribution."""

    model_config = ConfigDict(frozen=True)

    policy: PolicyRecord
    n: int
    alpha: float
    metrics: RiskMetrics
    gaussian: GaussianComparison
    provenance: Provenance


def risk_report(
    policy: PolicyRecord,
    npv_samples: npt.ArrayLike,
    *,
    alpha: float = 0.95,
    shortfall_threshold: float | None = None,
    provenance: Provenance,
) -> RiskReport:
    """Build a :class:`RiskReport` for one policy's NPV samples."""
    samples = tuple(float(v) for v in npv_samples)
    if not samples:
        raise ValueError("npv_samples must not be empty")
    metrics = RiskMetrics(
        n=len(samples),
        alpha=alpha,
        expected_npv=expected_npv(samples),
        npv_volatility=npv_volatility(samples),
        value_at_risk=value_at_risk(samples, alpha),
        conditional_value_at_risk=conditional_value_at_risk(samples, alpha),
        shortfall_probability=(
            shortfall_probability(samples, shortfall_threshold)
            if shortfall_threshold is not None
            else None
        ),
    )
    return RiskReport(
        policy=policy,
        n=len(samples),
        alpha=alpha,
        metrics=metrics,
        gaussian=gaussian_tail_metrics(samples, alpha, provenance=provenance),
        provenance=provenance,
    )


def risk_reports_from_grid(
    record: GridRunRecord,
    *,
    alpha: float = 0.95,
    shortfall_threshold: float | None = None,
    provenance: Provenance,
) -> tuple[RiskReport, ...]:
    """One :class:`RiskReport` per evaluated grid point.

    Grid points that failed to solve (``status`` not ``ok``) are skipped.
    """
    reports = []
    for result in record.results:
        if result.status != "ok" or result.run is None:
            continue
        reports.append(
            risk_report(
                result.policy,
                result.npv_samples,
                alpha=alpha,
                shortfall_threshold=shortfall_threshold,
                provenance=provenance,
            )
        )
    return tuple(reports)


__all__ = [
    "GaussianComparison",
    "RiskMetrics",
    "RiskReport",
    "conditional_value_at_risk",
    "expected_npv",
    "gaussian_tail_metrics",
    "npv_volatility",
    "risk_report",
    "risk_reports_from_grid",
    "shortfall_probability",
    "value_at_risk",
]
