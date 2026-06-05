# tests/

Test suite for dbt-test-lineage. Fast, no warehouse, no network.

## Contents

- `test_smoke.py` *(Phase 0)* — verifies the editable `dbt-column-lineage` path dependency resolves and
  that `extract_lineage` runs end-to-end on the engine's jaffle fixture (the input contract).

- `eval_harness.py` + `test_eval.py` — **accuracy gate**: hand-verified cases run end-to-end through the
  real engine (`extract_lineage`) + `analyze`, scored against expected/forbidden findings (REDUNDANT,
  REDUNDANT_STRUCTURAL, MISSING, UNCOVERED, load-bearing-not-flagged). Mirrors the engine's eval harness.
- `test_rules.py` / `test_propagate.py` / `test_unique.py` — the propagation oracle (rule table + not_null
  combination + unique key-sets). `test_reports.py` — finding generation + priority + weighted coverage +
  leverage + consolidation + cost. `test_confidence.py` — lineage-certainty flags. `test_unique_key.py`,
  `test_run_results.py`, `test_cli.py`, `test_loader.py`, `test_verdict.py`. Real-repo validation uses the
  engine's `.repos/lyst-dbt` clone.
