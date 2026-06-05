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

## Phase 1 — Test loader & guarantee model  ◻

Parse `manifest.json` test nodes (`resource_type:"test"`) into typed `DeclaredGuarantee(model, column,
kind)` for `not_null` / `unique` (skip + count others). Define the verdict lattice (`PROVEN` /
`VIOLATED` / `UNKNOWN` / `ESTABLISHED`) and the `ColumnVerdict` IR with a propagation-path field.
Loader tested against the jaffle fixture (extend it with a few tests) and the real repo.

## Phase 2 — not_null propagation  ◻

The per-transform nullability rule table (architecture §4.1) + multi-edge combination (§4.3: coalesce
OR, union/case AND). Topological walk over the column graph seeding from declared not_null tests.
Output `ColumnVerdict` per column with the explaining path. Hand-verified rule fixtures (one per
transform kind) are the correctness oracle — mirror the engine's eval-harness discipline.

## Phase 3 — unique propagation  ◻

Cardinality rules (architecture §4.2): row-multiplication breaks (`operations.may_multiply_rows`),
`GROUP BY` grain / `DISTINCT` establish, per-column injectivity. Single-column `unique` + the grain
tuple. Combined with Phase 2 into a single propagation pass.

## Phase 4 — The three reports + CI gate + advisory CLI  ◻

`CONTRADICTION` / `MISSING` / `REDUNDANT` detection (architecture §5) over the verdicts. Typer CLI:
`check` (CI gate — non-zero exit on contradictions, configurable on gaps) and `report` (advisory,
human-readable + JSON). Each row shows the propagation path. End-to-end on the real repo.

## Phase 5 — Breadth & ergonomics  ◻

`accepted_values` + `relationships` propagation (the lattice generalizes), multi-column `unique`,
richer reporting (coverage %, by-package), OpenLineage/test-result export, optional wrapper that runs
the engine for the user.

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
