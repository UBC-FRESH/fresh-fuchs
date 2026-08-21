# Design Documents

This folder collects design notes for model development and new features
in the FUCHS project. These are living documents — they capture the
rationale, architecture, and phased implementation plan for features
that touch the ws3 model structure, the inner LP, or the outer policy
layer.

## Documents

| Document | Status | Summary |
|----------|--------|---------|
| [composition-constraints.md](composition-constraints.md) | Implemented | Multi-species harvest-area composition targets via `composition_points` and `composition_axes` |
| [species-switching-replant.md](species-switching-replant.md) | Design | Harvest → replant with a different species; separate harvest actions per replant species, policy-driven |
| [yield-curve-framework.md](yield-curve-framework.md) | Implemented | Multi-species yield curve data structure and synthetic fallback; bundle dependency flagged |

## Conventions

- One document per major feature or architectural decision.
- Each document includes: motivation, ws3 mechanics, implementation
  plan (phased), open questions, and verification approach.
- Phase numbering follows the project roadmap conventions.
- Status keywords: **Design**, **In Progress**, **Implemented**, **Deferred**.
