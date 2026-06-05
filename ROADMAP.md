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

## Phase 5 — Breadth & ergonomics  ◻

`accepted_values` + `relationships` propagation (the lattice generalizes), multi-column `unique`,
richer reporting (coverage %, by-package), OpenLineage/test-result export, optional wrapper that runs
the engine for the user.

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
