# src/dbt_test_lineage/

Core package for the dbt test-lineage assurance tool. Consumes the `dbt-column-lineage` engine's IR and
propagates `not_null` / `unique` guarantees to verdicts. See [`../../docs/architecture.md`](../../docs/architecture.md).

## Modules

- `__init__.py` — package marker; exposes `__version__`.
- `verdict.py` — the guarantee model: `GuaranteeKind` (not_null/unique), the `Verdict` lattice
  (`PROVEN`/`ESTABLISHED`/`VIOLATED`/`UNKNOWN`, with `.holds`), `Effect`, and the explainable
  `ColumnVerdict` IR (carries the ordered `PropagationStep` path) + `verdict_to_dict`.
- `tests_loader.py` — parse `manifest.json` test nodes (`resource_type:"test"`) into typed
  `DeclaredGuarantee(asset, column, kind, source)` for not_null/unique; `load_test_inventory` also tallies
  skipped tests. (`asset` = attached_node unique_id — model, seed, or source.) `unique_key_guarantees`
  is the OPT-IN config source: `config.unique_key` → not_null+unique on the PK (`source="unique_key"`;
  single-col ⇒ both, composite ⇒ not_null per component only). `test_uid_index` maps
  `(asset,column,kind)`→test node uids; `load_run_results` reads `run_results.json` (uid→status),
  `load_run_timing` reads it (uid→execution_time seconds), and `load_run_metadata` reads its provenance
  (command/target/generated_at + `executed_tests` = was it `build`/`test`) — used to refuse a misleading
  cost when the artifact is from a non-test command (e.g. `dbt docs generate`).

- `rules.py` — per-transform-step guarantee effects. `not_null_effect(step)` maps the engine's
  `TransformStep` facts to an `Effect` per §4.1 (conservative null-preserving function allowlist);
  `is_injective_chain(transforms)` is the uniqueness-preserving (§4.2) per-column predicate.
- `propagate.py` — `propagate(result, guarantees, kind)` → `{(asset, column): ColumnVerdict}`
  (computed-from-inputs, excluding the column's own test). not_null folds each edge's chain over its
  upstream verdict and combines per §4.3 (COALESCE=OR, UNION=AND); unique tracks per-model unique
  KEY-SETS (establish from `operations.grain`/`distinct`, inherit through injective passthrough when not
  `may_multiply_rows`). `column_confidence(result)` = per-column lineage certainty (LOW if an incoming
  edge has an UNKNOWN transform / unresolved schema / warning, propagated downstream) → `Finding.confidence`.
- `reports.py` — `analyze(result, guarantees, kinds)` → `Report`. `Finding`s: REDUNDANT (tested +
  `PROVEN`, inherited — reason names the upstream anchor), REDUNDANT_STRUCTURAL (tested + `ESTABLISHED`,
  this model's SQL), MISSING (untested + `NOT_GUARANTEED` whose upstream held), UNCOVERED (single-column
  grain/PK with no guarantee anywhere), CONTRADICTION (tested + provable `VIOLATED`). Each `Finding` has a
  `priority` (key-ness + blast radius; sorted worst-first). Report also: per-kind `coverage` (raw +
  importance-`weighted`), `leverage` (per-test downstream reach where the guarantee holds), and
  `consolidations` (anchor → redundant tests it covers = minimal-test-set view). `redundant_cost(report,
  test_index, timing, dollars_per_hour)` prices removable tests from run_results `execution_time`.
  `report_to_dict`.
- `cli.py` — Typer CLI: `report` (text/`--json`; `--assume-unique-key`; `--run-results` annotates
  redundant tests with last-run status AND prices them; `--cost-per-hour` for $/run; `--limit N` top-N;
  `--workers/-j N` parallel lineage extraction) and `check` (CI gate; exits 1 on contradictions,
  `--strict` also on missing). Renders coverage (raw+weighted), leverage, consolidation, redundant-test
  cost, low-confidence count. (Engine `extract_column_lineage` is ~96% of runtime → `--workers` is the
  speed lever.)
