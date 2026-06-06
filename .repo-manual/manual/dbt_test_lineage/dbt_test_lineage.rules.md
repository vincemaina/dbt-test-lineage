---
id: dbt_test_lineage.rules
title: "dbt_test_lineage.rules"
section: dbt_test_lineage
importance: medium
source: skeleton
status: todo
generated_at: null
related_pages: [dbt_test_lineage.verdict]
relevant_files:
  - path: src/dbt_test_lineage/rules.py
    hash: ""
---

<!-- repo-manual:generated:start -->
<!-- repo-manual:TODO  Orchestrator: replace this generated region with the page narrative.
     Read the relevant source files below (and plan.json, page id "dbt_test_lineage.rules"), then write
     the chapter per docs/generation-recipe.md: source-grounded, cite every claim
     (Sources: [file:Lstart-end]), vertical mermaid diagrams, progressive disclosure.
     Leave the human region untouched. -->

# dbt_test_lineage.rules

> _Skeleton — awaiting narrative. The facts below are deterministic; the prose is not yet written._

<details>
<summary>Relevant source files</summary>

- [`src/dbt_test_lineage/rules.py`](../../../src/dbt_test_lineage/rules.py)

</details>

## Symbols defined here

- `_is_nonnull_literal(token: str) -> bool  [L37-47] — True only when a COALESCE default argument is unambiguously a non-null constant. Conservative:`
- `_coalesce_has_nonnull_default(default_sql: str) -> bool  [L50-53]`
- `not_null_effect(step: TransformStep) -> Effect  [L56-89] — How one transform step affects a propagating not_null guarantee (architecture §4.1).`
- `is_injective_chain(transforms: tuple[TransformStep, ...]) -> bool  [L103-107] — True if a column's value passes through unchanged-up-to-relabelling (uniqueness-preserving).`

## Connects to

- [dbt_test_lineage.verdict](./dbt_test_lineage.verdict.md)
<!-- repo-manual:generated:end -->

<!-- repo-manual:human:start -->
<!-- Human notes for this page are preserved across regeneration. Add yours below. -->
<!-- repo-manual:human:end -->
