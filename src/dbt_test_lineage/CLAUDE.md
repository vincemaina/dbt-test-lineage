# src/dbt_test_lineage/

Core package for the dbt test-lineage assurance tool. Consumes the `dbt-column-lineage` engine's IR and
propagates `not_null` / `unique` guarantees to verdicts. See [`../../docs/architecture.md`](../../docs/architecture.md).

## Modules

- `__init__.py` — package marker; exposes `__version__`.

_The modules below are planned per [`../../ROADMAP.md`](../../ROADMAP.md) and do not exist yet:_

- `tests_loader.py` *(Phase 1)* — parse `manifest.json` test nodes (`resource_type:"test"`) into typed
  `DeclaredGuarantee(model, column, kind)` for not_null/unique.
- `verdict.py` *(Phase 1)* — the verdict lattice (`PROVEN`/`VIOLATED`/`UNKNOWN`/`ESTABLISHED`) and the
  `ColumnVerdict` IR (with the explaining propagation path).
- `rules.py` *(Phase 2–3)* — per-transform effect tables (not_null §4.1, unique §4.2) + multi-edge
  combination (§4.3).
- `propagate.py` *(Phase 2–3)* — topological walk over the engine's column graph, seeding from declared
  guarantees and folding the rules to a verdict per `(column, guarantee)`.
- `reports.py` *(Phase 4)* — CONTRADICTION / MISSING / REDUNDANT detection over the verdicts.
- `cli.py` *(Phase 4)* — Typer CLI: `check` (CI gate) and `report` (advisory).
