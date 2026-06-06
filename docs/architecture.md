# Architecture — dbt-test-lineage

**Source of truth** for the assurance tool. Locked decisions, the guarantee-propagation model, the
per-transform rule tables, outputs, non-goals, stack. Read this before writing code.

## 1. What this tool is

`dbt-test-lineage` answers one question across a dbt project:

> **Does a declared test's guarantee still hold for the columns derived from it — and where is it
> missing, redundant, or contradicted?**

It is the **second** of two projects. The **first** — [`dbt-column-lineage`](../../dbt-column-lineage)
— already produces a rich, fact-only column-lineage IR (value edges with ordered transform chains,
control edges, model-level operation facts, self-references). This tool **consumes** that IR and adds
the *reasoning* the engine deliberately refused to do: propagating `not_null` / `unique` guarantees
through the recorded transforms to a verdict.

The split is load-bearing: the engine records **facts**, this tool renders **verdicts**. All
guarantee semantics live here; no lineage extraction lives here.

## 2. Locked decisions

1. **Consume the engine as a library.** Depend on `dbt-column-lineage` (path/editable dependency) and
   call `extract_lineage(...)` for the typed `LineageResult`. No JSON round-trip. The two repos evolve
   in lockstep; this tool pins a known-good engine version.
2. **MVP guarantees: `not_null` and `unique`.** The two with the richest transform semantics the engine
   already captures. `accepted_values` and `relationships` are designed-for but deferred (§7).
3. **Soundness over coverage — conservative both ways.** A column's guarantee is `PROVEN` only when the
   recorded facts *prove* it, `VIOLATED` only when they *prove* it cannot hold, else `UNKNOWN`. We never
   guess a guarantee holds, and never cry wolf on a violation. `UNKNOWN` is a first-class, common state.
4. **Primarily an advisory report; CI gate secondary.** The headline surface is the **report**
   (redundant / missing tests, with the propagation that explains each) — human-read, not a build
   blocker. A **CI gate** renderer also exists (non-zero exit on `CONTRADICTION`, `--strict` on coverage
   gaps) from the same analysis, but until we can *prove* `VIOLATED` it rarely fires, so it stays a
   secondary surface. Lead with `report`. (User steer, 2026-06-05.)
5. **dbt artifacts are the guarantee source, with pluggable opt-in sources.** Explicit tests come from
   `manifest.json` test nodes (`resource_type: "test"`, `test_metadata.name`, `column_name`,
   `attached_node`). Each `DeclaredGuarantee` carries a `source` so additional, **opt-in** sources can be
   layered in without being hardcoded to one project. The first is **`unique_key`** (`--assume-unique-key`):
   a model's `config.unique_key` implies `not_null`+`unique` on the PK — *off by default* because vanilla
   dbt's `unique_key` only drives incremental merge and does NOT enforce uniqueness; *on* for projects
   that enforce it (e.g. a `unique_key` override that auto-generates the tests). Single-column key ⇒
   not_null+unique; composite key ⇒ not_null per component only (the *tuple* is unique, not the parts).
   Implied guarantees seed propagation and count as coverage, but only **explicit** tests are reported as
   removable (REDUNDANT). YAML is never read directly; the compiled manifest is the contract.
6. **Facts in, verdicts out — but always explainable.** Every verdict carries the propagation path (the
   chain of columns + transforms) that produced it, so a human can audit it. Never assert without a why.

## 3. The guarantee-propagation model

### 3.1 State lattice

For each `(column, guarantee_type)` we compute a `Verdict`:

- **`PROVEN`** — the recorded transforms prove the guarantee holds for every row.
- **`ESTABLISHED`** — newly true at a column even though its inputs were not (e.g. `COALESCE(x, 'n/a')`
  is not_null regardless of `x`; `GROUP BY k` makes `k` unique). `PROVEN` with provenance "created here,
  not inherited" — the key signal for the redundancy report. (`PROVEN`/`ESTABLISHED` ⇒ `.holds`.)
- **`NOT_GUARANTEED`** — the structure **admits** a violation: a null-admitting / non-injective
  transform is on the path (TRY_CAST, outer-join nullable side, `STRUCT_ACCESS`, `CASE` with no ELSE,
  fan-out for unique). This is **not** proof of failure — the test may be perfectly valid and the data
  may always satisfy it. It means the guarantee is *not structurally guaranteed* and depends on data.
- **`UNKNOWN`** — not determinable from the facts (unknown scalar function, missing upstream info).
- **`VIOLATED`** — the transforms **prove** the guarantee cannot hold (rare: a literal `NULL` column,
  provable fan-out duplication). Reserved for the genuinely-provable case; this is the only CI-failing
  verdict. Most "admits a null" cases are `NOT_GUARANTEED`, not `VIOLATED`.

**Why the `NOT_GUARANTEED` / `VIOLATED` split (learned from real-repo validation):** almost nothing is
statically "provably null" — TRY_CAST/LEFT JOIN/variant-access *admit* nulls without *guaranteeing*
them. Equating "admits" with "contradiction" produced ~47 false CI failures on a 729-model repo. A false
alarm erodes trust faster than a missed one (locked decision §2.3), so "admits" is advisory, not fatal.

### 3.2 How propagation runs

1. **Seed** from declared tests: each `not_null` / `unique` test marks its `(model, column)` as a
   `PROVEN` *source guarantee* (a test is an assertion dbt enforces on that column).
2. **Walk** the column graph in topological (DAG) order. For each downstream column, combine its
   upstream DIRECT edges' verdicts under the transform rules (§4) to compute its own verdict.
3. A column may have **multiple upstream edges** for the same output (set-op branches, coalesce args,
   multiple CASE THEN values). The combination operator is read from the edge facts (`UNION` branch,
   `COALESCE` `arg_index`/`arg_count`, `CASE`) — see §4.3. This is the crux; single-edge folding is not
   enough.
4. Control edges (INDIRECT) never carry value guarantees — they are ignored for not_null/unique value
   propagation (but `unique` consults model-level `operations` + `controls`, §4.2).

## 4. Transform rule tables (facts → guarantee effect)

The engine's `TransformStep.kind` + `detail` map to nullability and cardinality effects. `P` = preserve
(output inherits input), `B` = break (admits a violation → `NOT_GUARANTEED`, **not** `VIOLATED`),
`E` = establish (→ guaranteed regardless of input), `?` = unknown (→ conservative downgrade of `PROVEN`
to `UNKNOWN`). No transform currently yields `VIOLATED` for not_null — nothing in the facts proves a
column is always/sometimes null (a literal-`NULL` column simply has no lineage edge). `VIOLATED` is
reserved for cases we can actually prove (and for unique fan-out, evaluated in Phase 3).

### 4.1 not_null effect (per transform step)

| Transform (kind + detail) | not_null effect | Rationale |
|---|---|---|
| `IDENTITY`, `RENAME` | **P** | passthrough |
| `CAST` (no `safe`) | **P** | Snowflake CAST errors on bad data, never nulls |
| `CAST {safe:true}` (TRY_CAST) | **B** | yields NULL on conversion failure |
| `COALESCE` with a non-null literal in `default` | **E** | always non-null |
| `COALESCE` (all args otherwise) | combine: not_null if **any** arg not_null (§4.3) | first-non-null wins |
| `CASE {else_null:true}` | **B** | unmatched rows → NULL |
| `CASE {else_null:false}` | combine: not_null if **all** THEN + ELSE not_null (§4.3) | every branch non-null |
| `AGGREGATION {func:COUNT}` | **E** | COUNT is never null |
| `AGGREGATION` (SUM/MIN/MAX/AVG/…) | **?** (conservative) | null on all-null/empty group |
| `WINDOW {func:ROW_NUMBER\|RANK\|…}` | **E** | ranking funcs non-null |
| `WINDOW` (LAG/LEAD/SUM-over/…) | **?** | null at frame boundaries / empty frames |
| `STRUCT_ACCESS` | **B** | missing variant key → NULL |
| `UNNEST` | **?** | exploded element may be null |
| `EXPRESSION {op:…}` (arithmetic) | **P** | arithmetic on non-null is non-null (÷0 errors, not nulls) |
| `EXPRESSION {func:NULLIF, introduces_nulls:true}` | **B** | NULL when args equal |
| `EXPRESSION {func:…}` (known null-preserving allowlist: UPPER, TRIM, …) | **P** | |
| `EXPRESSION {func:…}` (unknown function) | **?** | can't prove |
| `JOIN {introduces_nulls:true}` | **B** | outer-join nullable side |
| `JOIN {introduces_nulls:false}` (inner) | **P** | inner join preserves |
| `UNION {branch:n}` | combine: not_null if **all** branches not_null (§4.3) | every row from some branch |
| `UNKNOWN` | **?** | unclassified |

A chain is folded step-by-step; `E` short-circuits to not_null; the first `B` makes it nullable;
`?` downgrades `PROVEN`→`UNKNOWN` but is not a `VIOLATION`.

### 4.2 unique effect

Uniqueness is governed more by **model-level operation facts** than per-column transforms:

- Row multiplication breaks uniqueness: `operations.may_multiply_rows` (fan-out join / `UNION ALL` /
  lateral flatten) ⇒ any inherited `unique` becomes **B** unless re-established.
- `GROUP BY k` (read from `controls` GROUP_BY grain) ⇒ the grain tuple is **E** unique.
- `SELECT DISTINCT` (`operations.distinct`) ⇒ the selected tuple is **E** unique (row-level).
- Per-column injectivity along the chain: `IDENTITY`/`RENAME` preserve; `CAST` usually preserves;
  `CASE`/`COALESCE`/`STRUCT_ACCESS`/most funcs are non-injective ⇒ **B** (collisions possible).
- `unique` is a property of a **column or column tuple**; the MVP tracks single-column `unique` and the
  group-by/distinct grain tuple, and flags multi-column uniqueness as a follow-up (§7).

### 4.3 Multi-edge combination (the crux)

When a downstream column has N upstream DIRECT edges, the verdict combines by the construct:

- **COALESCE** (edges share an output, each tagged `arg_index`/`arg_count`): not_null if **any** branch
  is not_null, or the `default` holds a non-null literal. (Logical OR over not-null.)
- **UNION** (edges tagged `branch`): not_null if **all** branches are not_null. (Logical AND.)
- **CASE** (multiple THEN value edges + `else_null`): not_null if **all** THEN edges not_null and
  `else_null` is false. (Logical AND, plus the else.)
- Otherwise (independent contributions): conservative AND.

These combination semantics are *why* the engine records `arg_index`, `branch`, and `else_null`.

## 5. Outputs — the three reports

Defined precisely over the lattice (does a test exist on the column × its computed verdict, which
excludes the column's own test). The two headline reports are sound and actionable:

- **REDUNDANT** (advisory, high-confidence): a tested column whose verdict is **`PROVEN`** — the
  guarantee is **inherited** from an upstream test through preserving transforms (a passthrough re-test).
  Safe to remove *while the upstream test stays* (there is a coupling). The most defensible signal — only
  fires when we can prove the redundancy.
- **REDUNDANT_STRUCTURAL** (advisory): a tested column whose verdict is **`ESTABLISHED`** — the guarantee
  is created by **this model's own SQL**, independent of any upstream test: a `GROUP BY` grain makes a
  column unique; `COALESCE(x, <literal>)` / `COUNT` / `ROW_NUMBER` make it not_null. The test re-checks
  what the structure itself guarantees → removable regardless of upstream tests (only the model's SQL
  must hold). Distinct from REDUNDANT because the *reason* (and the coupling) differ: structural
  redundancy is local and more safely removable; inherited redundancy depends on the upstream test.
- **MISSING** (advisory): a column is **untested** and `NOT_GUARANTEED` **and the transform that broke
  it acted on an upstream column that held the guarantee** — i.e. a guarantee existed upstream and a
  transform dropped it without a re-test. A real, targeted coverage hole (kept narrow to stay
  high-signal; the broad "never covered" set is UNCOVERED, below). *Note:* for `unique`, a MISSING from
  `operations.may_multiply_rows` is **conservative** — "a join/union/flatten is present, so this key
  *may* duplicate", not a claim it does (cardinality is data-dependent). Read those as "verify the join
  cardinality", not "definitely broken".
- **UNCOVERED** (advisory): a **single-column-grain** column — a model's natural primary key — with **no
  guarantee anywhere in its lineage** (untested, not structurally guaranteed, nothing upstream held it).
  Scoped to *single-column* grains (`len(operations.grain) == 1`) deliberately: every grain column would
  be noise (many GROUP BY keys are nullable dimensions; real-repo had ~1157 such), whereas a
  single-column grain is the model's key and "this PK has zero coverage" is a clean, actionable signal.
  The whole-population picture is the separate **`coverage`** statistic (per kind: of the columns the
  lineage reaches, how many are covered = tested or structurally guaranteed). Together, MISSING +
  UNCOVERED + coverage answer "where are the testing gaps?": dropped guarantees, uncovered keys, and the
  overall %. *(Widening UNCOVERED to non-grain key-like columns needs a naming/downstream-key-usage
  heuristic — deferred.)*
- **CONTRADICTION** (CI-failing, rare/strict): a column has a declared test but its verdict is
  `VIOLATED` — the transforms *prove* the guarantee cannot hold. Reserved for genuinely-provable cases
  so the CI gate never false-alarms. `NOT_GUARANTEED` is **not** a contradiction (the test may be valid;
  the data may always satisfy it) — it surfaces in an informational "relies on data, not structure"
  listing, optionally promotable to a failure via a strict/opt-in mode.

Every report row includes the **propagation path**: the column-to-column chain and the transform at
each hop that produced the verdict, so the user can audit and act.

## 6. Integration & data flow

```
manifest.json ──► dbt-column-lineage.extract_lineage() ──► LineageResult (edges, controls,
                                                            operations, self_references)
                                                                   │
manifest.json ──► test loader (resource_type:"test") ──► DeclaredGuarantee[]
                                                                   │
                                          ▼─────────── propagation engine (§3–§4) ───────────▼
                                                            ColumnVerdict[ (col, guarantee) ]
                                                                   │
                                              ┌────────────────────┴───────────────────┐
                                          CI gate (exit code)                    advisory report
```

## 7. Non-goals / deferred

- **Data-level checking.** We never query the warehouse or read rows. Purely static over the lineage
  facts. (A `PROVEN` verdict means "the transforms guarantee it," not "the current data satisfies it.")
- **`accepted_values` / `relationships`** propagation — designed-for (the lattice + path machinery is
  general), deferred past the not_null/unique MVP.
- **Declared-assumption verification (future direction).** The same propagation machinery generalizes
  from "does a *test's* guarantee survive?" to "does a *declared assumption* hold upstream?". Two shapes,
  both later: (a) **declared-vs-derived type checking** — read an expected data type from column YAML
  docs (or the manifest's column metadata) and check it against what the engine infers/derives upstream,
  flagging mismatches; (b) **ad-hoc assumption probing** — when a `not_null` (or other) test sits on a
  column, walk upstream to verify the assumption is actually supportable by the lineage (essentially the
  MISSING/REDUNDANT analysis run on demand for a single column). The engine already exposes inferred
  schemas + provenance and the hybrid reconciliation diff, so the type-check variant mostly reuses
  existing facts. Deferred — noted so the verdict/path IR stays general enough to carry a type/value
  assumption, not only not_null/unique.
- **Multi-column `unique`** beyond the group-by/distinct grain tuple — follow-up.
- **Correlated-subquery and other engine `UNKNOWN`s** propagate as `?` (we inherit the engine's
  documented limitations rather than re-deriving lineage).
- **Custom/package generic tests** (the manifest's `test_metadata.name: null`, `expression_is_true`,
  etc.) — out of MVP; recognized and skipped, counted in a coverage denominator only.

## 8. Stack

Mirrors the engine: **Python 3.12 · `uv` · `pytest` · `ruff` (line-length 100) · `Typer` CLI**,
`src/` layout. Dependency: **`dbt-column-lineage`** (path dependency to the sibling repo). No warehouse
drivers, no network. Per-folder `CLAUDE.md`. **Git is the user's job.**
