---
id: dbt_test_lineage.tests_loader
title: "dbt_test_lineage.tests_loader"
section: dbt_test_lineage
importance: high
source: skeleton
status: todo
generated_at: null
related_pages: [dbt_test_lineage.verdict]
relevant_files:
  - path: src/dbt_test_lineage/tests_loader.py
    hash: ""
---

<!-- repo-manual:generated:start -->
<!-- repo-manual:TODO  Orchestrator: replace this generated region with the page narrative.
     Read the relevant source files below (and plan.json, page id "dbt_test_lineage.tests_loader"), then write
     the chapter per docs/generation-recipe.md: source-grounded, cite every claim
     (Sources: [file:Lstart-end]), vertical mermaid diagrams, progressive disclosure.
     Leave the human region untouched. -->

# dbt_test_lineage.tests_loader

> _Skeleton — awaiting narrative. The facts below are deterministic; the prose is not yet written._

<details>
<summary>Relevant source files</summary>

- [`src/dbt_test_lineage/tests_loader.py`](../../../src/dbt_test_lineage/tests_loader.py)

</details>

## Symbols defined here

- `DeclaredGuarantee  [L24-33] — A guarantee asserted on a specific (model, column). `asset` is the model's unique_id, matching the`
- `TestInventory  [L37-42] — Everything the loader found: the MVP guarantees plus a tally of skipped tests (table-level,`
- `_attached_model(node: dict) -> str | None  [L45-51]`
- `load_test_inventory(manifest_path: str | Path) -> TestInventory  [L54-69]`
- `load_declared_guarantees(manifest_path: str | Path) -> list[DeclaredGuarantee]  [L72-74] — Convenience: just the MVP (not_null / unique) guarantees from explicit tests.`
- `test_uid_index(manifest_path: str | Path) -> dict[tuple[str, str, GuaranteeKind], list[str]]  [L77-92] — `(attached_model, column, kind) -> [test node unique_id]` for not_null/unique tests — lets a`
- `load_run_results(path: str | Path) -> dict[str, str]  [L95-102] — `node_unique_id -> status` (pass / success / fail / error / skipped) from a `run_results.json`.`
- `load_run_metadata(path: str | Path) -> dict  [L105-121] — Provenance of a `run_results.json` so a cost/timing reading is never context-free: which dbt`
- `load_run_timing(path: str | Path) -> dict[str, float]  [L124-132] — `node_unique_id -> execution_time` (wall-clock seconds) from a `run_results.json` — used to price`
- `_key_columns(unique_key: object) -> list[str] | None  [L135-150] — Plain column name(s) from a `unique_key` config (str or list of str). Returns None for an`
- `unique_key_guarantees(manifest_path: str | Path, kinds: tuple[GuaranteeKind, ...]=(GuaranteeKind.NOT_NULL, GuaranteeKind.UNIQUE)) -> list[DeclaredGuarantee]  [L153-177] — OPT-IN guarantees implied by each model's `config.unique_key` — for projects that enforce the key`

## Connects to

- [dbt_test_lineage.verdict](./dbt_test_lineage.verdict.md)
<!-- repo-manual:generated:end -->

<!-- repo-manual:human:start -->
<!-- Human notes for this page are preserved across regeneration. Add yours below. -->
<!-- repo-manual:human:end -->
