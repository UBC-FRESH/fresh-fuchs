# Fire Regime in fresh-fuchs

Status: **Implemented** (zone-based regime, v0.1.0a1) · species-specific
parameterization: **Design**.

This note records why and how wildfire enters the FUCHS planning problem:
the real-world quantities the regime represents, how they map onto the ws3
Model I inner LP, the verification evidence gathered so far, the known
limitations of the v0.1.0a1 formulation, and what a future
species-specific parameterization needs. Function-level details live in
`src/fresh_fuchs/scenario/fire.py`, `scenario/fire_lp.py`,
`scenario/records.py`; calibration and test records live in
`planning/validation-report.md` (P3.x sections).

## Motivation: what the regime represents

Wildfire is the dominant natural disturbance on the tsa29mini landscape
(SBPS and IDF biogeoclimatic zones near Williams Lake) and therefore the
principal source of downside risk for harvest-schedule NPV. The regime is
built from four real-world ingredients:

1. **Zone-level fire frequency.** Each analysis unit inherits its BEC
   zone's mean fire return interval (MFRI):

   | BEC zone | MFRI (years) | Annual burn probability R |
   |----------|--------------|---------------------------|
   | SBPS     | 100          | 0.010                     |
   | IDF      | 200          | 0.005                     |
   | MS       | 150          | 0.0067                    |
   | ESSF     | 200          | 0.005                     |
   | ICH      | 250          | 0.004                     |
   | SBS      | 125          | 0.008                     |

   Treating ignition as a memoryless Poisson process gives an annual burn
   probability `R = 1/MFRI`, homogeneous in space, time, and stand state.
   A 10-year LP period sees a burn fraction `1 - (1 - R)^10` (~9.6 % SBPS,
   ~4.9 % IDF). Only SBPS and IDF occur in tsa29mini; the full ladder is
   carried so future bundles work unchanged, and unmapped zones fail fast.

2. **Severity ladder.** Burned live volume converts to *salvageable*
   deadwood by a severity tier: Unburned 0.0, Low 0.30, Moderate 0.60,
   High 0.85. Severity proxies fire intensity/consumption class. tsa29mini
   has no burn-severity polygons, so severity is a scenario parameter with
   **Moderate** as default.

3. **Decay of dead wood.** Unsalvaged burned volume retains 0.85 of its
   value-volume per year (checking, insect attack) — burned timber left
   standing depreciates quickly, which motivates prompt-salvage economics
   rather than open-ended salvage windows.

4. **Ordering contract** harvest → fire → salvage → decay within each
   annual timestep: a stand harvested in year *t* is not exposed to fire
   that year, and any harvest or salvage regenerates the stand, resetting
   its accumulated fire exposure.

Uncertainty is handled Monte-Carlo style: each scenario fixes an entire
fire path up front (deterministic expected-value burns scaled by a single
Gaussian multiplier, mean 1.0, std 0.2), the inner LP solves against that
known path with full foresight, and risk is measured ex-post over the
scenario NPV distribution (empirical CVaR/VaR in the outer layer). The
scenario catalogue is seed-fixed (`master_seed + i`), so runs are bit-stable.

## How fire enters the inner LP

Fire does not add decision variables; it modifies the coefficients of the
existing Model I prescription paths:

- **Survival-reduced green harvest.** Green volume realized in period *t*
  equals the yield curve value times the cumulative survival
  `product_{u<t} (1 - p(u))` accumulated over every period the cohort
  stood unharvested since last regeneration. A null period compounds the
  survival discount; a harvest or salvage resets it (fresh stand).
- **Salvage as a genuine action.** `salvage` is a Model I action with a
  regeneration transition to age 0, operable only where the scenario's
  zone actually burns in that period and only above a minimum stand age of
  60 years (no salvage of regenerating stands; also bounds Model I tree
  growth). Salvageable volume in a burning period is
  `severity_fraction x p(t) x exposed_live`.
- **Explicit feasibility row.** `salvage_vol(t) - salvageable_vol(t) <= 0`
  is added as a general LP row so the burned-pool ceiling is queryable from
  the solved problem (it is structurally satisfied by construction).
- **Salvage economics decide.** Salvage earns the prompt-salvage margin
  (burned price = green sawlog x 0.65; harvest cost +25 %; haul $38/m³;
  stumpage floor $0.25/m³). With the default surface the SPF sawlog-basis
  margin is about −11.95 CAD/m³, so the LP salvages nothing — matching the
  behaviour of the fresh-salvage reference agent at the same margins. A
  subsidised (positive) margin exercises the mechanism in tests.
- **Burned carryover is not an LP stock** (v0.1.0a1): unsalvaged burned
  volume decays out of the model rather than being tracked period to
  period; the annual-dynamics module tracks it for accounting and tests.

## Validation evidence

Summarised from `planning/validation-report.md` (P3.1–P3.6 and the
cross-phase checks); see there for full records and commands.

- **Parity with the calibration reference**: 14 unit tests assert the MFRI
  ladder, severity fractions, decay rate, and the dynamics ordering against
  values carried from the fresh-salvage fire module (reference only, no
  import).
- **Internal consistency**: a fire-free scenario through the full pipeline
  reproduces the deterministic NPV-max anchor bit-level (mean annual
  harvest 33,624.77 m³/yr, total harvested area 104,462.175 ha, per-period
  differences < 1e-6 at horizon 30).
- **Monotonicity in burn rate** (real bundle, h=8, all zones burning):

  | Multiplier | NPV (CAD)     | Harvest (m³/yr) | Harvested area (ha) | Salvageable pool (m³) |
  |------------|---------------|-----------------|---------------------|-----------------------|
  | 0.0        | 23,350,932    | 49,596          | 40,768              | 0                     |
  | 0.5        | 21,557,788    | 49,803          | 40,657              | 123,462               |
  | 1.0        | 19,899,102    | 50,033          | 40,424              | 243,092               |
  | 2.0        | 16,941,297    | 50,128          | 40,318              | 468,926               |

  NPV strictly decreases with the burn multiplier; the salvageable pool
  grows monotonically; the even-flow band holds.
- **MC convergence** (synthetic instance, h=2): CVaR(0.95) is stable to
  < 0.23 % across catalogue sizes n = 5…320; guidance is n ≈ 40 on that
  instance. Caveat recorded: the tail there is *thin* because fire is a
  low-probability event over two zones and two periods; the real
  30-period bundle needs larger catalogues.
- **Computational bound**: dense-burn scenarios are the worst case
  (h=20 ≈ 377k variables, ~6 min build; h≥24 grows to tens of minutes per
  scenario), which caps practical catalogue sizes at horizon 30. Fire-free
  scenarios cost the same as the plain NPV LP (~773k vars, ~4 min at h=30).

## Limitations

Recorded so results are interpreted with the right caveats:

- **No spatial structure.** Hazard is zone-homogeneous: no ignition
  locations, no spread, no adjacency between harvested and standing
  cohorts.
- **Age-independent hazard.** Every stand burns with probability R
  regardless of age, whereas real ignition-to-stand replacement depends on
  fuel accumulation and stand flammability.
- **Within-scenario determinism.** One scenario is an expected-value flow
  (exactly `R x exposed` volume burns each year). All variance comes from
  one zone-wide multiplier applied uniformly across zones and periods —
  i.e., perfectly correlated fire years, no inter-annual or inter-zonal
  dispersion inside a realization.
- **One uniform severity tier** per catalogue (default Moderate): no
  polygons, no weather, no drought interaction.
- **Burned carryover untracked in the LP.** Unsalvaged burned volume
  decays out rather than remaining as a stock a later period can still
  salvage.
- **Flat prompt-salvage regime.** One price discount, cost premium, haul,
  and stumpage floor apply regardless of time-since-burn beyond the decay
  rate; the 60-year age floor excludes young-stand salvage entirely.
- **Static regime.** MFRIs are historical literature estimates; no climate
  trend or non-stationarity.
- **Price uncertainty inactive.** The PRICE dimension is carried in the
  uncertainty vector and multiplies LP cash flows, but defaults to fixed
  1.0.

## Species-specific parameterization (roadmap, Design)

The current regime keys hazard to the BEC zone prefix of the AU stratum
code. Because stratum codes already carry the leading species
(`SBPS_PLI`, `IDF_FD`, …), upgrading to species-specific fire is a
localized structural change: replace the `(zone -> MFRI)` lookup with a
`(stratum -> rate)` lookup and make severity/decay species-aware. What a
good parameterization needs:

1. **Hazard by fuel type / leading species.** Lodgepole-pine-dominated
   stands (SBPS_PLI) ignite and carry crown fire far more readily than
   mature Douglas-fir (IDF_FD). Sources: BC Fire Behaviour Prediction
   (FBP) fuel types mapped from leading species, Natural Disturbance Type
   (NDT) classifications, and empirical ignition/burn-rate estimation
   from BC Wildfire Service fire perimeters joined to VRI leading-species
   and BEC layers.
2. **Post-fire mortality by species × age.** Thick-barked mature
   Douglas-fir survives low-intensity surface fire; lodgepole pine
   typically top-kills at any age. This would replace the flat survival
   discount with a species- and age-dependent survival function.
3. **Salvageability and deterioration by species.** Burned spruce checks
   and degrades within a few years; Douglas-fir retains value longest;
   pine is intermediate. Today a single 0.85/yr retention applies to all
   species; a species ladder would refine salvage timing and economics.
4. **Severity distributions per fuel type** instead of one global tier,
   ideally conditioned on seasonal drought indices if data allows.

Provenance requirements follow the repo convention: any adopted
species-specific constants need a named source, vintage, units, and basis
record, and the parity-test pattern (reference values carried in-module)
is the template for regression anchors.

## Open questions

- Should the burn-rate multiplier stay zone-uniform, or should zones draw
  independent multipliers (dispersed fire years) once species-specific
  hazards break the zone symmetry?
- Is a two-tier salvage window (prompt vs deferred margins) worth the
  extra action complexity before species-specific decay exists?
- How should climate non-stationarity enter: scenario-conditioned MFRIs or
  a trend multiplier on R?

## Verification approach

Existing anchors (kept green by the test suite):

- `tests/test_fire.py`: parity of constants and dynamics ordering.
- `tests/test_fire_lp.py`: survival compounding/reset, salvage ceiling,
  fire-free equivalence at LP level, negative-margin suppression,
  fail-fast zone mapping.
- `tests/test_pipeline.py` / `tests/test_phase3_acceptance.py`:
  pipeline record shape, parallel bit-stability, fire-free schedule
  reproduction, NPV monotonicity in the burn multiplier.

Any species-specific extension must preserve these anchors for the
zone-default case and add stratum-keyed parity tests following the same
pattern.
