# fresh-fuchs

Stochastic, risk-aware forest landscape planning on the TSA29 mini instance
(~100,000 ha subset of Williams Lake TSA29).

The research design is a nested decision problem:

- **Outer (policy / administration).** Landscape-scale policy on target
  species / development-type composition by area share and on harvest policy
  (AAC as f(development type, rotation age)), evaluated risk-sensitively on
  Monte-Carlo distributions of NPV using downside-risk measures (CVaR).
- **Inner (enterprise / implementation).** Harvest scheduling and replanting
  decisions (which species to plant) maximizing NPV subject to the outer
  policy constraints, formulated as a Model I linear program.

Full-Monte-Carlo outer problem: sample disturbance (fire) and — later —
price realizations; solve the inner LP once per scenario (full foresight
within a scenario); evaluate each policy on the resulting NPV distribution.

Reuses the UBC-FRESH ecosystem rather than re-implementing it: `ws3`
(wood-supply engine and LP machinery), `femic` (tsa29mini instance bundle and
model bridge), `fhops` (harvest-cost estimation), `nemora` (DBH distribution
fit and sampling), and `freshforge` (workflow + matrix orchestration and
evidence). `fresh-salvage` provides economic calibration anchors (reference
only).

## Status

Phase 0 (skeleton scaffold). See `ROADMAP.md` for the phase/issue tracker
map and `planning/v0.1.0a1-plan.md` for the detailed master plan.

## Quick Start

(placeholder — fill in when the CLI lands in Phase 0/1)

```bash
pip install -e ".[dev]"
fresh-fuchs --help
```

## Documentation

Sphinx docs under `docs/` (skeleton in Phase 0).

## License

MIT, Copyright (c) 2026 UBC FRESH Lab.
