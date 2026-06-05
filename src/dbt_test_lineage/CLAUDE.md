# src/dbt_test_lineage/

Core package for the dbt test-lineage assurance tool. Consumes the `dbt-column-lineage` engine's IR and
propagates `not_null` / `unique` guarantees to verdicts. See [`../../docs/architecture.md`](../../docs/architecture.md).

## Modules

- `__init__.py` — package marker; exposes `__version__`.
- `verdict.py` — the guarantee model: `GuaranteeKind` (not_null/unique), the `Verdict` lattice
  (`PROVEN`/`ESTABLISHED`/`VIOLATED`/`UNKNOWN`, with `.holds`), `Effect`, and the explainable
  `ColumnVerdict` IR (carries the ordered `PropagationStep` path) + `verdict_to_dict`.
- `tests_loader.py` — parse `manifest.json` test nodes (`resource_type:"test"`) into typed
  `DeclaredGuarantee(asset, column, kind)` for not_null/unique; `load_test_inventory` also tallies
  skipped tests (`TestInventory.skipped_by_name`) for coverage. (`asset` = attached_node unique_id, which
  may be a model, seed, or source — all valid propagation seed points.)

- `rules.py` — per-transform-step guarantee effects. `not_null_effect(step)` maps the engine's
  `TransformStep` facts to an `Effect` per §4.1 (conservative null-preserving function allowlist);
  `is_injective_chain(transforms)` is the uniqueness-preserving (§4.2) per-column predicate.
- `propagate.py` — `propagate(result, guarantees, kind)` → `{(asset, column): ColumnVerdict}`
  (computed-from-inputs, excluding the column's own test). not_null folds each edge's chain over its
  upstream verdict and combines per §4.3 (COALESCE=OR, UNION=AND); unique tracks per-model unique
  KEY-SETS (establish from `operations.grain`/`distinct`, inherit through injective passthrough when not
  `may_multiply_rows`).
- `reports.py` — `analyze(result, guarantees, kinds)` → `Report` of `Finding`s: REDUNDANT (tested +
  `.holds`), MISSING (untested + `NOT_GUARANTEED` whose upstream held the guarantee), CONTRADICTION
  (tested + provable `VIOLATED`); + `relies_on_data` count. `report_to_dict` / `finding_to_dict`.
- `cli.py` — Typer CLI: `report` (advisory text/JSON) and `check` (CI gate; exits 1 on contradictions,
  `--strict` also on missing).
