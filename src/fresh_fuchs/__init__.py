"""fresh-fuchs: stochastic, risk-aware forest landscape planning.

A full-Monte-Carlo outer policy problem (species-composition targets,
AAC/rotation policy, CVaR evaluation) wrapped around a per-scenario Model I
inner LP (NPV-max harvest + replant scheduling) on the TSA29 mini instance.
"""

from __future__ import annotations

__version__ = "0.1.0a1"
