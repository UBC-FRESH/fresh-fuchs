# FUCHS Economics Calibration Record (Phase 5, P5.3)

Every economic constant in `fresh_fuchs.economy` with its provenance, and
the fresh-salvage cross-checks. The FUCHS surface is greenfield but anchored
to the fresh-salvage economics calibration (reference only — no import) and
the BC Interior Log Market Report Q4-2023 price levels. Anchors are
*compared against*, not force-fit; every deviation is recorded with a
reason. All monetary values are CAD.

Conventions: `assumption = True` marks a flagged assumption with no direct
measurement (the calibration's "DERIVED"/"ASSUMPTION" convention). Sources
are named inline in the code via `Provenance` records; this document is the
consolidated index.

## 1. Log prices (`economy/types.py::_default_prices`)

Source: BC Interior Log Market Report Q4-2023 (market report); flat
sawlog-basis price used by the v0.1.0a1 LP objective (grade/peeler premia
reserved for later log-grade work). Provenance source string
`INTERIOR_PRICE_SOURCE`, as-of Q4-2023, units CAD/m3, assumption False.

| Price group | Peeler | Sawlog | Pulpwood |
| --- | --- | --- | --- |
| SPF (spruce, lodgepole pine) | 146.0 | 127.0 | 55.0 |
| Df-Larch (Douglas-fir) | 118.0 | 103.0 | 55.0 |
| HemBal | 138.0 | 120.0 | 55.0 |
| Cedar | 166.0 | 144.0 | 55.0 |
| Other (mixed-secondary basket) | — | 90.0 | — |

Species -> price group: Douglas-fir -> Df-Larch; spruce and lodgepole pine
-> SPF; everything else -> Other (`price_group_for_species`).

Cross-check (fresh-salvage): the calibration's green SPF prices are
146/127/55 (peeler/sawlog/pulpwood) — **match**. The LP objective uses the
sawlog basis; the peeler/pulpwood rows are carried for the reserved
log-grade phase.

## 2. Harvest / haul / stumpage (green)

| Constant | Value | Provenance | Assumption |
| --- | --- | --- | --- |
| Green harvest cost | 45.0 CAD/m3 | fresh-salvage calibration `GREEN_HARVEST_COST`; tree-to-truck ($30-40/m3) + road/admin/silviculture allocation; fhops machine-rate estimate (P2.2) is an alternative basis | True |
| Green haul (transport) | 30.0 CAD/m3 | interior haul practice (flat) | True |
| Green stumpage | 15.0 CAD/m3 | BC interior stumpage (flat) | True |
| Discount rate | 0.03 /yr, end-of-period | fresh-salvage calibration (predecessor default retained) | False |

The default $45/m3 harvest cost already carries a silviculture allocation,
so the LP does **not** charge the per-ha replant cost by default
(`charge_replant_in_npv = False`) — charging both would double-count.
`charge_replant_in_npv` exists so a later phase can switch to a
silviculture-exclusive $/m3 harvest cost and flip replant charging on.

fhops machine-rate alternative basis (`economy/fhops_costing.py`):
`default_clearcut_stand()` is a representative interior spruce/lodgepole
clearcut (0.3 m3 stems, ~180 m3/ha, 2000 stems/ha, 25% slope; assumption
True). Consumes `fhops.costing.estimate_unit_cost_from_stand` (Lahrsen
productivity + rental-rate costing); rental rates from fhops' bundled
machine-rate table. This is an *alternative* tree-to-truck basis, not the
default LP cost.

## 3. Replanting (regeneration) cost (`_default_replant`)

Source: fresh-fuchs assumption (no direct measurement); interior
planting/regen practice. as-of 2024, units CAD/ha, basis "flat per-ha
planting + free-to-grow establishment", assumption True. Not charged in the
default LP (silviculture inside the $45/m3 harvest cost).

| Species class | Cost (CAD/ha) |
| --- | --- |
| Lodgepole pine | 2,200.0 |
| Spruce | 2,400.0 |
| Douglas-fir | 2,600.0 |
| Other (default) | 2,200.0 |

Douglas-fir is above lodgepole pine/spruce for stocking risk. Flagged:
verify against a femic/fhops source before release. Transition-dependent
replanting cost (a different species costs more) is out of scope for
v0.1.0a1.

## 4. Salvage economics (`_default_salvage`, `economy/cashflow.py`)

Source: fresh-salvage `planning/economics-calibration.md` (reference only,
no import); prompt-salvage (year 1-3) regime; grade-transition erratum fixed
2026-08-13. Source string `SALVAGE_CALIBRATION_SOURCE`, as-of 2026-08-13,
units CAD/m3.

| Constant | Value | Meaning |
| --- | --- | --- |
| `burned_price_discount` | 0.65 | Fire-damaged timber realizes ~65% of green value |
| `burned_harvest_premium` | 0.25 | Fractional add-on over green harvest cost for prompt salvage |
| `burned_transport_per_m3` | 38.0 | Burned haul cost (+25% over green 30) |
| `burned_stumpage_per_m3` | 0.25 | Fire-damaged timber stumpage floor (BC Table 6-4a) |
| `volume_decay_rate` | 0.85 | Yearly retention of unsalvaged burned volume (15%/yr decay) |

Grade transition (downgrade-only; fire never upgrades grade; each row sums
to 1 so burned volume is conserved):

| Source product | -> Peeler | -> Sawlog | -> Pulpwood |
| --- | --- | --- | --- |
| Peeler | 0.55 | 0.35 | 0.10 |
| Sawlog | — | 0.80 | 0.20 |
| Pulpwood | — | — | 1.00 |

### Derived salvage margins (cross-checks)

- **Sawlog-basis salvage margin** (`sawlog_basis_salvage_margin`, zero
  subsidy): burned sawlog price − burned harvest − burned haul − burned
  stumpage. For SPF on the default surface: 127 x 0.65 = 82.55; minus
  burned harvest 45 x 1.25 = 56.25, minus haul 38, minus stumpage 0.25
  = **-11.95 CAD/m3**. Matches the fresh-salvage sawlog-basis anchor of
  ~ -11.7 CAD/m3 within rounding of the transport/stumpage floor.
- **Transition-mix burned price** (`transition_mix_burned_price`, SPF
  sawlog source): 0.65 x (0.80 x 127 + 0.20 x 55) = 0.65 x 112.6 =
  **73.19 CAD/m3**; the corresponding margin is the calibration's headline
  ~ **-21 CAD/m3** (73.19 - 56.25 - 38 - 0.25 = -21.31). **Match.**

### fresh-salvage headline anchors (reference only)

| Anchor | fresh-salvage value | FUCHS surface | Status |
| --- | --- | --- | --- |
| Salvage margin (unsubsidized, transition mix) | ~ -21 to -24 CAD/m3 | -21.31 (SPF sawlog source) | Match |
| Salvage margin (sawlog basis) | ~ -11.7 CAD/m3 | -11.95 (SPF) | Match |
| Subsidy flip turn-on | ~ 23.85 CAD/m3 (ramp 23.9-24.1) | not modelled (no subsidy in v0.1.0a1) | Reference |
| FESBC contribution | 14-15 CAD/m3 closes ~60% of the gap | not modelled | Reference |
| Burned price discount | 0.65 | 0.65 | Match |
| Volume decay | 0.85 | 0.85 | Match |
| Green SPF prices (peeler/sawlog/pulpwood) | 146 / 127 / 55 | 146 / 127 / 55 | Match |
| Burned harvest / haul costs | 56 / 38 | 56.25 / 38 | Match |

The subsidy flip (~23.85) and FESBC (14-15) anchors are reference-only:
v0.1.0a1 runs an *unsubsidized* prompt-salvage regime, so salvage is
economically suppressed on the default surface (negative margin), matching
the fresh-salvage reference agent. A subsidy/salvage-uptake scenario is a
post-v0.1.0a1 phase.

## 5. Fire dynamics constants (`scenario/fire.py`, reference only)

Not economic constants, but recorded here because they enter the NPV
distribution through the fire pools:

- MFRI by zone (`MFRI_YEARS_BY_ZONE`, fresh-salvage `fire.py`): SBPS 100,
  IDF 200, MS 150, ESSF 200, ICH 250, SBS 125; annual burn rate 1/MFRI.
- Severity -> salvageable fraction (`SEVERITY_TO_BURNED_FRAC`): Unburned
  0.0, Low 0.30, Moderate 0.60, High 0.85; default Moderate (the tsa29mini
  bundle has no burn-severity polygon data).
- Burned-volume decay 0.85 (matches the salvage `volume_decay_rate`).
- Ordering within a timestep: harvest -> fire -> salvage -> decay.

## 6. Deviations and caveats

- The default harvest cost ($45/m3) is a *calibration total* including
  silviculture; a silviculture-exclusive fhops basis plus explicit replant
  charging is the reserved alternative (not yet default).
- Replant per-ha costs are flagged assumptions awaiting a femic/fhops
  source.
- Coast-vs-interior price provenance: the LP uses interior Q4-2023 sawlog
  prices; the coast log-grade price matrix (femic) is the reserved template
  for the interior log-grade follow-on.
- Salvage subsidy/FESBC anchors are reference-only (unsubsidized regime in
  v0.1.0a1).
