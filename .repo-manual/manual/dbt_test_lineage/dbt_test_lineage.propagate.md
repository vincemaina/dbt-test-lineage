---
id: dbt_test_lineage.propagate
title: "dbt_test_lineage.propagate"
section: dbt_test_lineage
importance: medium
source: skeleton
status: todo
generated_at: null
related_pages: [dbt_test_lineage.rules, dbt_test_lineage.tests_loader, dbt_test_lineage.verdict]
relevant_files:
  - path: src/dbt_test_lineage/propagate.py
    hash: ""
---

<!-- repo-manual:generated:start -->
<!-- repo-manual:TODO  Orchestrator: replace this generated region with the page narrative.
     Read the relevant source files below (and plan.json, page id "dbt_test_lineage.propagate"), then write
     the chapter per docs/generation-recipe.md: source-grounded, cite every claim
     (Sources: [file:Lstart-end]), vertical mermaid diagrams, progressive disclosure.
     Leave the human region untouched. -->

# dbt_test_lineage.propagate

> _Skeleton — awaiting narrative. The facts below are deterministic; the prose is not yet written._

<details>
<summary>Relevant source files</summary>

- [`src/dbt_test_lineage/propagate.py`](../../../src/dbt_test_lineage/propagate.py)

</details>

## Symbols defined here

- `_model_topo_order(edges: Iterable[LineageEdge]) -> list[str]  [L38-59] — Kahn topological sort of the model-level DAG implied by the edges (self-edges ignored). Any node`
- `_edge_is_uncertain(edge: LineageEdge) -> bool  [L62-69] — The engine couldn't fully pin this edge down — an UNKNOWN transform step, an unresolved schema,`
- `column_confidence(result: LineageResult) -> dict[_Key, Confidence]  [L72-91] — Per-column confidence in the LINEAGE the verdicts rest on (kind-independent). LOW if any incoming`
- `_to3(v: Verdict) -> str  [L94-97]`
- `_from3(state: str, established: bool) -> Verdict  [L100-103]`
- `_step_detail(step) -> str  [L106-108]`
- `_fold_not_null(input_verdict: Verdict, edge: LineageEdge) -> tuple[Verdict, list[PropagationStep]]  [L111-131] — Fold one edge's chain. Effects are lattice functions; BREAK/ESTABLISH/UNKNOWN are constants, so`
- `_and(verdicts: list[Verdict]) -> Verdict  [L137-146] — not_null holds only if ALL inputs hold (UNION branches, independent contributors, CASE THENs).`
- `_or(verdicts: list[Verdict]) -> Verdict  [L149-160] — not_null holds if ANY input holds (COALESCE arguments); else unknown if any unknown, else the`
- `_has_kind(edge: LineageEdge, kind: TransformKind) -> bool  [L163-164]`
- `_union_branch(edge: LineageEdge) -> int | None  [L167-171]`
- `_combine_group(folded: list[tuple[LineageEdge, Verdict]]) -> Verdict  [L174-178]`
- `_combine_not_null(edges: list[LineageEdge], upstream: Callable[[str, str], Verdict]) -> tuple[Verdict, list[PropagationStep]]  [L181-195]`
- `propagate(result: LineageResult, guarantees: Iterable[DeclaredGuarantee], kind: GuaranteeKind=GuaranteeKind.NOT_NULL) -> dict[_Key, ColumnVerdict]  [L198-208] — Compute the verdict for every column the lineage reaches, for one guarantee `kind`.`
- `_propagate_not_null(result: LineageResult, guarantees: Iterable[DeclaredGuarantee]) -> dict[_Key, ColumnVerdict]  [L211-242]`
- `_propagate_unique(result: LineageResult, guarantees: Iterable[DeclaredGuarantee]) -> dict[_Key, ColumnVerdict]  [L248-322] — Track each model's unique KEYS (sets of output columns provably unique). Establish from the`

## Connects to

- [dbt_test_lineage.rules](./dbt_test_lineage.rules.md)
- [dbt_test_lineage.tests_loader](./dbt_test_lineage.tests_loader.md)
- [dbt_test_lineage.verdict](./dbt_test_lineage.verdict.md)
<!-- repo-manual:generated:end -->

<!-- repo-manual:human:start -->
<!-- Human notes for this page are preserved across regeneration. Add yours below. -->
<!-- repo-manual:human:end -->
