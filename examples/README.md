# fresh-fuchs examples

Public-safe example configs, added per phase. All examples use synthetic or
public-safe fixtures — never private or bundled data.

- `policy-grid.tsa29mini.json` — a `PolicyGrid` definition for the
  `fresh-fuchs policy-grid` CLI (PL area-share composition axis x AAC axis +
  an unconstrained baseline).
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
