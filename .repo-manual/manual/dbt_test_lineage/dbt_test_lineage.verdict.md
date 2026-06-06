---
id: dbt_test_lineage.verdict
title: "dbt_test_lineage.verdict"
section: dbt_test_lineage
importance: high
source: skeleton
status: todo
generated_at: null
related_pages: []
relevant_files:
  - path: src/dbt_test_lineage/verdict.py
    hash: ""
---

<!-- repo-manual:generated:start -->
<!-- repo-manual:TODO  Orchestrator: replace this generated region with the page narrative.
     Read the relevant source files below (and plan.json, page id "dbt_test_lineage.verdict"), then write
     the chapter per docs/generation-recipe.md: source-grounded, cite every claim
     (Sources: [file:Lstart-end]), vertical mermaid diagrams, progressive disclosure.
     Leave the human region untouched. -->

# dbt_test_lineage.verdict

> _Skeleton — awaiting narrative. The facts below are deterministic; the prose is not yet written._

<details>
<summary>Relevant source files</summary>

- [`src/dbt_test_lineage/verdict.py`](../../../src/dbt_test_lineage/verdict.py)

</details>

## Symbols defined here

- `GuaranteeKind  [L13-17] — A dbt test guarantee we propagate. MVP = not_null + unique (architecture §2).`
- `Verdict  [L20-30]`
- `Verdict.holds(self) -> bool  [L28-30] — True when the guarantee is provably satisfied (PROVEN or ESTABLISHED).`
- `Effect  [L33-41] — How one transform step (or a seed/combine) acts on a guarantee as it propagates.`
- `PropagationStep  [L45-51] — One hop in a verdict's explanation: the upstream column, how the guarantee was affected, and a`
- `ColumnVerdict  [L55-65] — The propagated verdict for one (column, guarantee) pair, with the path that explains it.`
- `ColumnVerdict.__str__(self) -> str  [L64-65]`
- `verdict_to_dict(v: ColumnVerdict) -> dict  [L68-75]`
<!-- repo-manual:generated:end -->

<!-- repo-manual:human:start -->
<!-- Human notes for this page are preserved across regeneration. Add yours below. -->
<!-- repo-manual:human:end -->
