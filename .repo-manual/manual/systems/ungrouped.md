---
id: ungrouped
title: "Ungrouped"
section: systems
importance: low
source: generated
status: fresh
description: "Files not yet assigned to a system — group these in structure.json."
generated_at: 2026-06-06T13:58:20+00:00
related_pages: []
relevant_files:
  - path: src/dbt_test_lineage/__init__.py
    hash: "sha256:62cc6343bbc52c6f2b0311fb2ee6919781dd343e6f175f123e256a4b4661b6a3"
---

<!-- repo-manual:generated:start -->
# Ungrouped — package metadata

<details>
<summary>Relevant source files</summary>

- [`src/dbt_test_lineage/__init__.py`](../../../src/dbt_test_lineage/__init__.py)

</details>

These files weren't assigned to a system in `structure.json`. Here there's just one, and it's
intentionally outside the five systems: the package marker.

`__init__.py` is the package's front door — a module docstring summarising the whole tool ("consume the
engine's fact-only IR and render verdicts") and the `__version__` string. It contains no logic.
`Sources: [src/dbt_test_lineage/__init__.py:1-7]()`

> This page exists because the tool never silently drops a file: anything a system doesn't claim lands
> here, visibly. To fold it into a system, add the path to that system in `.repo-manual/structure.json`
> and regenerate.
<!-- repo-manual:generated:end -->

<!-- repo-manual:human:start -->
<!-- Human notes for this page are preserved across regeneration. Add yours below. -->
<!-- repo-manual:human:end -->
