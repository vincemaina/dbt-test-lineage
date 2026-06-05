# tests/

Test suite for dbt-test-lineage. Fast, no warehouse, no network.

## Contents

- `test_smoke.py` *(Phase 0)* — verifies the editable `dbt-column-lineage` path dependency resolves and
  that `extract_lineage` runs end-to-end on the engine's jaffle fixture (the input contract).

_Planned (per [`../ROADMAP.md`](../ROADMAP.md)):_ hand-verified **rule fixtures** — one per transform
kind — as the propagation correctness oracle (mirrors the engine's eval-harness discipline), plus
loader and report tests, validated against the engine's `.repos/lyst-dbt` real-repo clone.
