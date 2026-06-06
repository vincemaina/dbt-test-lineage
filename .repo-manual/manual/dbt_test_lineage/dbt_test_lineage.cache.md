---
id: dbt_test_lineage.cache
title: "dbt_test_lineage.cache"
section: dbt_test_lineage
importance: medium
source: skeleton
status: todo
generated_at: null
related_pages: []
relevant_files:
  - path: src/dbt_test_lineage/cache.py
    hash: ""
---

<!-- repo-manual:generated:start -->
<!-- repo-manual:TODO  Orchestrator: replace this generated region with the page narrative.
     Read the relevant source files below (and plan.json, page id "dbt_test_lineage.cache"), then write
     the chapter per docs/generation-recipe.md: source-grounded, cite every claim
     (Sources: [file:Lstart-end]), vertical mermaid diagrams, progressive disclosure.
     Leave the human region untouched. -->

# dbt_test_lineage.cache

> _Skeleton — awaiting narrative. The facts below are deterministic; the prose is not yet written._

<details>
<summary>Relevant source files</summary>

- [`src/dbt_test_lineage/cache.py`](../../../src/dbt_test_lineage/cache.py)

</details>

## Symbols defined here

- `_cache_key(manifest: Path, catalog: Path | None, schema_mode: str, dialect: str) -> str  [L18-25]`
- `extract_lineage_cached(manifest_path, catalog_path=None, *, schema_mode: str='auto', dialect: str='snowflake', cache: str | Path | None=None) -> tuple[LineageResult, bool]  [L28-52] — Return (result, from_cache). With `cache` set, reuse a valid cached result keyed on the manifest/`
<!-- repo-manual:generated:end -->

<!-- repo-manual:human:start -->
<!-- Human notes for this page are preserved across regeneration. Add yours below. -->
<!-- repo-manual:human:end -->
