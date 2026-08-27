# fresh-fuchs examples

Public-safe example configs, added per phase. All examples use synthetic or
public-safe fixtures — never private or bundled data.

- `policy-grid.tsa29mini.json` — a `PolicyGrid` definition for the
  `fresh-fuchs policy-grid` CLI (PL area-share composition axis x AAC axis +
  an unconstrained baseline).
- `policy-grid.replant-default.json` — species-switching replant family,
  default: no `replant_actions`, so the inner LP replants the same species
  (v0.1.0a2 behaviour).
- `policy-grid.replant-unconstrained.json` — `replant_actions:
  ["harvest_SX", "harvest_FD"]` with no composition targets: the LP chooses
  replant species purely on economics.
- `policy-grid.replant.json` — `replant_actions: ["harvest_SX",
  "harvest_FD"]` plus spruce replant-area composition targets on the
  three-phase schedule (`n_free_periods` / `n_ramp_periods`), with an
  unconstrained baseline using the same replant actions.

The replant grids pair with a model built via `build-model
--replant-species SX --replant-species FD` (ideally with
`--replant-curves-csv`/`--replant-manifest-csv` pointing at the P6.6 BTC
artifacts in the tsa29mini instance repo) so replant development types
carry real target-species yield curves.
- `fuchs_workflow_template.yaml` — the freshforge workflow template for the
  pipeline (build_model -> scenario_run -> policy_grid -> policy_rank) on the
  public-safe synthetic instance, with a `${matrix.pl_share}` placeholder in
  the policy-grid node.
- `fuchs_matrix.yaml` — a freshforge matrix that expands the workflow
  template over the PL area-share axis; run with
  `fresh_fuchs.orchestration.run_fuchs_matrix` (requires the `orchestration`
  extra).

The synthetic instance (`fresh_fuchs.instance.synthetic`) backs the
orchestration examples so they run end-to-end in CI without private data.
