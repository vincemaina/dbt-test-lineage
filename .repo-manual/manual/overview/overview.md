---
id: overview
title: "Overview — start here"
section: overview
importance: high
source: skeleton
status: todo
description: "What this repo is, the mental model, and how the systems connect."
generated_at: null
related_pages: []
relevant_files:
  - path: src/dbt_test_lineage/cli.py
    hash: ""
---

<!-- repo-manual:generated:start -->
<!-- repo-manual:TODO  Orchestrator: replace this generated region with the page narrative.
     Read the relevant source files below (and plan.json, page id "overview"), then write
     the chapter per docs/generation-recipe.md: source-grounded, cite every claim
     (Sources: [file:Lstart-end]), vertical mermaid diagrams, progressive disclosure.
     Leave the human region untouched. -->

# Overview — start here

> _Skeleton — awaiting narrative. The facts below are deterministic; the prose is not yet written._

What this repo is, the mental model, and how the systems connect.

<details>
<summary>Relevant source files</summary>

- [`src/dbt_test_lineage/cli.py`](../../../src/dbt_test_lineage/cli.py)

</details>

## Symbols defined here

- `_run(manifest: Path, catalog: Optional[Path], assume_unique_key: bool, cache: Optional[Path]=None) -> Report  [L40-51]`
- `_status(f: Finding, status_map: dict) -> str  [L62-70]`
- `_render(report: Report, limit: int=0, status_map: dict | None=None, cost: dict | None=None) -> None  [L73-136]`
- `_status_map(manifest: Path, run_results: Optional[Path]) -> dict  [L139-149] — (asset, column, kind) -> [last-run statuses] for the tests on that column.`
- `report(manifest: Path=_MANIFEST, catalog: Optional[Path]=_CATALOG, assume_unique_key: bool=_ASSUME_UK, run_results: Optional[Path]=typer.Option(None, '--run-results', help='dbt run_results.json — annotate redundant tests with last-run status and price what they cost per run (passing = safe to remove; failing = investigate first)'), cost_per_hour: float=typer.Option(0.0, '--cost-per-hour', help='Warehouse $/hour — estimate the per-run $ spent on removable redundant tests'), limit: int=typer.Option(0, '--limit', '-n', help='Show only the top-N (highest priority) findings per category'), cache: Optional[Path]=_CACHE, as_json: bool=typer.Option(False, '--json', help='Emit JSON instead of text')) -> None  [L153-189] — Advisory report: redundant / missing / contradicted tests, each with its propagation path.`
- `check(manifest: Path=_MANIFEST, catalog: Optional[Path]=_CATALOG, assume_unique_key: bool=_ASSUME_UK, cache: Optional[Path]=_CACHE, strict: bool=typer.Option(False, '--strict', help='Also fail on MISSING coverage holes')) -> None  [L193-211] — CI gate: exit non-zero on provable contradictions (and, with --strict, on missing coverage).`
<!-- repo-manual:generated:end -->

<!-- repo-manual:human:start -->
<!-- Human notes for this page are preserved across regeneration. Add yours below. -->
<!-- repo-manual:human:end -->
