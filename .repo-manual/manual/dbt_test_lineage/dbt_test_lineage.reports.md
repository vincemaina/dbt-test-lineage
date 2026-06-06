---
id: dbt_test_lineage.reports
title: "dbt_test_lineage.reports"
section: dbt_test_lineage
importance: medium
source: skeleton
status: todo
generated_at: null
related_pages: [dbt_test_lineage.propagate, dbt_test_lineage.tests_loader, dbt_test_lineage.verdict]
relevant_files:
  - path: src/dbt_test_lineage/reports.py
    hash: ""
---

<!-- repo-manual:generated:start -->
<!-- repo-manual:TODO  Orchestrator: replace this generated region with the page narrative.
     Read the relevant source files below (and plan.json, page id "dbt_test_lineage.reports"), then write
     the chapter per docs/generation-recipe.md: source-grounded, cite every claim
     (Sources: [file:Lstart-end]), vertical mermaid diagrams, progressive disclosure.
     Leave the human region untouched. -->

# dbt_test_lineage.reports

> _Skeleton — awaiting narrative. The facts below are deterministic; the prose is not yet written._

<details>
<summary>Relevant source files</summary>

- [`src/dbt_test_lineage/reports.py`](../../../src/dbt_test_lineage/reports.py)

</details>

## Symbols defined here

- `ReportKind  [L43-48]`
- `Finding  [L52-64]`
- `Finding.__str__(self) -> str  [L63-64]`
- `TestLeverage  [L68-76] — How far an explicit test's guarantee reaches: the number of downstream columns where it still`
- `Report  [L80-88]`
- `Report.of(self, kind: ReportKind) -> list[Finding]  [L87-88]`
- `_parse_col(colstr: str) -> tuple[str, str]  [L91-93]`
- `_held(colstr: str, verdicts: dict[tuple[str, str], ColumnVerdict], tested: set) -> bool  [L96-102] — Did the column carry the guarantee upstream — i.e. is it tested, or its verdict holds?`
- `_anchor(start: tuple, up_adj: dict, asserted: set, held: set) -> tuple | None  [L105-119] — Climb upstream through holding columns to the nearest column that carries a declared guarantee —`
- `_reach(start: tuple, down_adj: dict, held: set) -> int  [L122-132] — Count downstream columns reachable from `start` through columns where the guarantee still holds —`
- `analyze(result: LineageResult, guarantees: list[DeclaredGuarantee], kinds: tuple[GuaranteeKind, ...]=_DEFAULT_KINDS) -> Report  [L135-251]`
- `finding_to_dict(f: Finding) -> dict  [L254-265]`
- `redundant_cost(report: Report, test_index: dict, timing: dict[str, float], dollars_per_hour: float=0.0) -> dict  [L268-290] — Price the removable (REDUNDANT + REDUNDANT_STRUCTURAL) tests using per-test `execution_time` from`
- `report_to_dict(report: Report) -> dict  [L293-308]`

## Connects to

- [dbt_test_lineage.propagate](./dbt_test_lineage.propagate.md)
- [dbt_test_lineage.tests_loader](./dbt_test_lineage.tests_loader.md)
- [dbt_test_lineage.verdict](./dbt_test_lineage.verdict.md)
<!-- repo-manual:generated:end -->

<!-- repo-manual:human:start -->
<!-- Human notes for this page are preserved across regeneration. Add yours below. -->
<!-- repo-manual:human:end -->
