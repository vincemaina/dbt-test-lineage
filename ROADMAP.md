# Roadmap — dbt-test-lineage

The assurance tool that consumes [`dbt-column-lineage`](../dbt-column-lineage)'s lineage IR and reasons
about whether `not_null` / `unique` guarantees survive transformations. Architecture and rationale:
[`docs/architecture.md`](./docs/architecture.md).

Sequencing principle: get a **sound, explainable** verdict for one guarantee end-to-end first, then add
the second guarantee, then the two output modes, then breadth. Every phase ends with tests + lint green
and a real-repo sanity run (the engine's `.repos/lyst-dbt` clone has 195 not_null/unique tests).

## Phase 0 — Scaffolding & contract  ◻ not started

`uv` project, `src/` layout, `ruff`/`pytest` wired into `pyproject.toml`, **`dbt-column-lineage` path
dependency** resolving and importable. A smoke test that calls `extract_lineage` on the engine's jaffle
fixture and asserts a `LineageResult` comes back. Per-folder `CLAUDE.md`.

## Phase 1 — Test loader & guarantee model  ✅ done

`tests_loader.py`: `load_test_inventory` parses `manifest.json` test nodes into typed
`DeclaredGuarantee(asset, column, kind)` for `not_null`/`unique`, normalizes columns to lower-case, and
tallies skipped tests (`TestInventory.skipped_by_name`). `verdict.py`: the `Verdict` lattice
(`PROVEN`/`ESTABLISHED`/`VIOLATED`/`UNKNOWN`, `.holds`), `Effect`, and the explainable `ColumnVerdict`
IR (ordered `PropagationStep` path) + serializer. Validated on a synthetic manifest and the real repo
(194 guarantees: 179 model, 15 seed — tests attach to models/seeds/sources, all valid seed points). 10
tests, lint clean.

## Phase 2 — not_null propagation  ✅ done

`rules.not_null_effect` implements the §4.1 table (lattice-function model: PRESERVE=identity,
BREAK/ESTABLISH/UNKNOWN=constants, so the last non-PRESERVE step wins). `propagate.propagate` does the
model-topological walk, folds each edge's chain over its upstream verdict, and combines per §4.3
(COALESCE=OR, UNION=AND across branches, else AND). A tested column propagates downstream as PROVEN
(dbt enforces it); the returned verdict is COMPUTED-from-inputs only, so Phase 4 can compare it against
the column's own test. **Real-repo validation forced a soundness reframe** (architecture §3.1): a
null-admitting transform (TRY_CAST / outer join / variant access) → `NOT_GUARANTEED` (advisory, "admits
a null"), **not** `VIOLATED` — equating the two gave 47 false CI fails. `VIOLATED` is reserved for
provable cases (the only CI-failing verdict). Rule-table oracle (`test_rules.py`, 23 cases) + synthetic
combination tests + end-to-end through the engine. 47 tests, lint clean. (Follow-up: push
`coalesce has_nonnull_default` into the engine as a fact instead of the current sound string heuristic.)

## Phase 3 — unique propagation  ✅ done

**Full grain-tuple tracking** (user-chosen): track unique column SETS, not just single columns. Compute
per-model unique keys from `operations.grain` (the GROUP BY grain as output columns — **added to the
engine** this pass, since `controls` GROUP_BY is base-resolved and doesn't map cleanly to outputs) and
`operations.distinct` (all outputs), inherit keys through injective passthrough when the model doesn't
multiply rows (`operations.may_multiply_rows`), and break on fan-out / non-injective transforms
(architecture §4.2). A single-column `unique` test on `C` ⇒ `.holds` iff `{C}` is a unique key.
Engine `ModelOperation.grain` fact (maps `group by 1,2` / `group by a` → output column names; `()` if a
grain key isn't selected) + `rules.is_injective_chain` + `propagate._propagate_unique` (per-model unique
key-set propagation): establish from grain/distinct, inherit through injective passthrough when not
`may_multiply_rows`, break on fan-out → `NOT_GUARANTEED`. Single-column `unique` test holds iff `{C}` is
a key; composite grain doesn't prove single columns. 8 unique tests (synthetic + e2e grain+inheritance).
Like not_null, fan-out is "may multiply" → `NOT_GUARANTEED`, not provable `VIOLATED`.

## Phase 4 — Reports + CI gate + advisory CLI  ✅ done

`reports.analyze` → `Report` of `Finding`s: **REDUNDANT** (tested + `PROVEN`, inherited from an upstream
test), **REDUNDANT_STRUCTURAL** (tested + `ESTABLISHED`, guaranteed by this model's own SQL — GROUP BY
grain / COALESCE / COUNT), **MISSING** (untested +
`NOT_GUARANTEED` *whose upstream held the guarantee* — a dropped guarantee, kept targeted to avoid
noise), **UNCOVERED** (grain/key column with no guarantee anywhere in its lineage — zero-coverage keys),
**CONTRADICTION** (tested + provable `VIOLATED`), plus a per-kind **`coverage`** stat (covered/total)
and a `relies_on_data` count. Typer CLI `cli.py`: `report` (text + `--json`, shows path + coverage) and
`check` (exits 1 on contradictions, `--strict` also on missing). Validated end-to-end via the CLI on the
real repo. Primarily a report tool (CI gate secondary — user steer).

**Opt-in guarantee sources.** `DeclaredGuarantee.source` + `tests_loader.unique_key_guarantees` +
CLI `--assume-unique-key`: a model's `config.unique_key` implies not_null+unique on the PK (single-col ⇒
both; composite ⇒ not_null per component). Off by default (vanilla dbt doesn't enforce unique_key); for
projects that do, it seeds propagation, counts as coverage, and suppresses UNCOVERED on those PKs, while
findings still report only on explicit tests. Real repo: 411 models declare a usable unique_key → 824
implied guarantees. 72 tests, lint clean.

## Phase 4.5 — Finding prioritization  ✅ done

`Finding.priority` = key-ness (single-column grain / PK) + downstream blast radius (direct dependents,
capped). Findings sorted worst-first; CLI `report --limit N` shows the top-N per category and prints the
`[pN]` score. Makes a long MISSING list (248 with `--assume-unique-key`) actionable top-down. 73 tests.

## Phase 4.6 — Accuracy validation & confidence  ✅ done

The tool's value is trust, so before more breadth: **confidence** + an **accuracy gate**.
- `propagate.column_confidence` — per-column lineage certainty (LOW if an incoming edge has an UNKNOWN
  transform / unresolved schema / engine warning, propagated downstream). Every `Finding` carries
  `confidence`; the CLI flags low-confidence findings (⚠) and counts them ("rest on uncertain lineage —
  verify before acting"). Lets users act on the high-confidence findings and scrutinise the rest.
- `tests/eval_harness.py` + `test_eval.py` — hand-verified cases run end-to-end through the **real
  engine** + `analyze`, scored against expected/forbidden findings. Caught a real bug in the author's own
  expectation (anchor-side of a LEFT JOIN is not null-introduced). The reproducible accuracy gate.

**Next (user-noted, deferred):** **diff / regression mode** (PR-time: a change broke a guarantee N
downstream tests rely on — the CI adoption path) and **`accepted_values` / `relationships` propagation**
(extend the lattice to the other two generic tests). Then exposure-aware prioritization, chokepoint
consolidation.

## Phase 4.7 — Performance  ✅ done

Profiled: the engine's `extract_column_lineage` (sqlglot `lineage()`) is ~96% of runtime (~417ms/model
× 729 ≈ 5 min, dominated by a few very wide models); propagation/reports are seconds. The fix:
- **Lineage cache** (`cache.extract_lineage_cached` + CLI `--cache PATH`): pickle the `LineageResult`
  keyed on manifest/catalog contents + params + engine version; reused while inputs are unchanged →
  iterating on the report (different `--assume-unique-key`/`--run-results`/etc.) skips re-extraction
  entirely. The right fix since audits re-*analyze*, not re-*extract*.

(Cross-model parallelism was prototyped — correct but only ~1.3–1.7× on this repo because a handful of
wide models dominate the wall-clock, and unstable at higher worker counts in constrained envs — so it
was removed to keep the engine lean. The good part, a pure per-model `_process_uid`, was kept.)

## Phase 5 — Breadth & ergonomics  ◻

`accepted_values` + `relationships` propagation (the lattice generalizes), multi-column `unique`,
richer reporting (coverage %, by-package), OpenLineage/test-result export, optional wrapper that runs
the engine for the user.

## Future capabilities — assessing test effectiveness & efficiency

Ideas to push the tool from "find redundant/missing tests" toward "tell me how good and how economical
our testing is." Roughly ordered by value/effort; all build on the existing verdict + propagation IR.

**Efficiency (test economically):**
- **✅ Optimal / minimal test placement — DONE (first cut).** `Report.consolidations`: each REDUNDANT
  (inherited) test is traced to the upstream **anchor** that covers it (`_anchor` climbs through holding
  columns to the nearest declared guarantee); grouped anchor → covered tests = "test once at the anchor,
  remove the rest." Reason string names the anchor.
- **Test consolidation at chokepoints** — find columns where many lineages converge; testing there
  covers many downstream paths with fewer tests. *(Extends consolidation; still future.)*

**Effectiveness (test the right things):**
- **✅ Guarantee reach / test leverage — DONE.** `Report.leverage`: per explicit test, the downstream
  footprint where its guarantee still holds (`_reach` through holding columns). Low reach (0) = guards
  only its own column.
- **✅ Importance-weighted coverage — DONE.** `coverage[kind]` carries `weighted_total`/`weighted_covered`
  (column weight = 1 + blast radius + PK-ness), so "coverage of high-impact columns" is surfaced.
- **✅ `run_results.json` correlation — DONE.** `--run-results`: redundant tests annotated with last-run
  status (passing = safe to remove; failing = investigate). `tests_loader.test_uid_index` +
  `load_run_results`.
- **✅ Redundant-test cost — DONE.** `reports.redundant_cost` prices removable tests from run_results
  `execution_time` (`load_run_timing`): seconds spent on droppable tests, % of total test time, and `$`
  per run via `--cost-per-hour` (warehouse rate). **Provenance guardrail** (`load_run_metadata`): every
  cost is labelled with the dbt command/target/timestamp, and a loud warning replaces the number when the
  artifact is from a non-test command (`dbt docs generate`/`compile`/`run`) — those per-test times are
  compile/catalog time, not real test runtime. Refuses to mislead rather than print a meaningless figure.
- **Exposure-aware prioritization** — dbt `exposures` mark columns the business consumes (dashboards,
  ML). Prioritize gaps on lineage paths that reach an exposure. *(Still future.)*
- **`accepted_values` / `relationships` propagation** — extend the lattice to the other two generic
  tests (does a value-domain survive a CASE/coalesce; does a FK relationship survive a join). *(Future.)*
- **Diff / regression mode** — compare two manifests (PR before/after): "your change made `order_id`
  NOT_GUARANTEED and 3 downstream tests now rely on data" — change-safety for CI.

## Future direction — declared-assumption verification

Generalize the propagation from "does a test's guarantee survive?" to "does a declared *assumption*
hold upstream?" (architecture §7): (a) **declared-vs-derived type checking** — compare an expected data
type from column YAML docs / manifest column metadata against the engine's inferred/derived upstream
type, flagging mismatches (mostly reuses the engine's inference + hybrid reconciliation facts);
(b) **ad-hoc assumption probing** — given a test on a column, walk upstream on demand to check the
assumption is supportable. Noted now so the verdict/path IR stays general enough to carry a type/value
assumption, not only not_null/unique. (Requested 2026-06-05; deferred.)

## Known design risks (to validate as we build)

- **Multi-edge combination correctness** — the OR/AND semantics (§4.3) are the subtlest part; the
  rule-fixture oracle must cover coalesce / union / case-without-else explicitly.
- **`?` (UNKNOWN) rate** — too many unknown scalar functions could make the advisory report noisy; a
  curated null-preserving function allowlist mitigates. Measure the unknown rate on the real repo.
- **Soundness of `VIOLATED`** — a false contradiction erodes trust faster than a missed one. Bias the
  rules so `VIOLATED` requires proof; when unsure, emit `UNKNOWN`, not a contradiction.
- **Engine `UNKNOWN`/limitation inheritance** — correlated-subquery columns, pivot, etc. propagate as
  `?`; document so users know coverage boundaries.

## Deferred / out of scope

Data-level validation (no warehouse access — purely static), non-Snowflake dialects (inherited from the
engine's posture), hosted service.
