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
4. **Two output modes from one engine.** A **CI gate** (non-zero exit on `CONTRADICTION`, configurable
   on coverage gaps) and an **advisory report** (missing / redundant tests, with the propagation that
   explains each). Same analysis, two renderers.
5. **dbt artifacts are the test source.** Declared tests come from `manifest.json` test nodes
   (`resource_type: "test"`, `test_metadata.name`, `column_name`, `attached_node`). YAML is never read
   directly; the compiled manifest is the contract — mirrors the engine's stance.
6. **Facts in, verdicts out — but always explainable.** Every verdict carries the propagation path (the
   chain of columns + transforms) that produced it, so a human can audit it. Never assert without a why.

## 3. The guarantee-propagation model

### 3.1 State lattice

For each `(column, guarantee_type)` we compute a `Verdict`:

- **`PROVEN`** — the recorded transforms prove the guarantee holds for every row.
- **`VIOLATED`** — the recorded transforms prove the guarantee cannot hold (e.g. a not_null column fed
  through a LEFT join's nullable side).
- **`UNKNOWN`** — not provable either way from the facts (the safe default; e.g. an unknown scalar
  function, a missing upstream schema, an `EXPRESSION` we can't reason about).

A guarantee can also be **`ESTABLISHED`** — newly true at a column even though its inputs were not
(e.g. `COALESCE(x, 'n/a')` is not_null regardless of `x`; `GROUP BY k` makes `k` unique). `ESTABLISHED`
is `PROVEN` with provenance "created here, not inherited" — useful for the redundancy report.

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
(output inherits input), `B` = break (→ nullable / non-unique), `E` = establish (→ guaranteed
regardless of input), `?` = unknown (→ conservative break of `PROVEN`, but not a `VIOLATION`).

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

Defined precisely over the lattice (a test exists / a guarantee verdict):

- **CONTRADICTION** (highest value, CI-failing): a column has a declared `not_null`/`unique` test, but
  its propagated verdict is `VIOLATED`. The test asserts something the transforms prove false → the test
  is wrong, the upstream changed, or there's a real data bug waiting to fire.
- **MISSING** (advisory): a column's verdict is `PROVEN`/`ESTABLISHED` for a guarantee its **declared
  grain** suggests it should carry, but **no test exists** here — or, more useful, a column that is
  `UNKNOWN`/fragile (a `B` transform) on the path between two tested models, i.e. a coverage hole where
  the guarantee is *not* carried through and should be re-tested.
- **REDUNDANT** (advisory): a column carries a `not_null`/`unique` test, but the same guarantee is
  already `PROVEN` by an upstream test + a chain of preserving transforms (no `B`/`?` in between) → the
  test re-checks something already guaranteed; candidate for removal to cut test runtime.

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
- **Multi-column `unique`** beyond the group-by/distinct grain tuple — follow-up.
- **Correlated-subquery and other engine `UNKNOWN`s** propagate as `?` (we inherit the engine's
  documented limitations rather than re-deriving lineage).
- **Custom/package generic tests** (the manifest's `test_metadata.name: null`, `expression_is_true`,
  etc.) — out of MVP; recognized and skipped, counted in a coverage denominator only.

## 8. Stack

Mirrors the engine: **Python 3.12 · `uv` · `pytest` · `ruff` (line-length 100) · `Typer` CLI**,
`src/` layout. Dependency: **`dbt-column-lineage`** (path dependency to the sibling repo). No warehouse
drivers, no network. Per-folder `CLAUDE.md`. **Git is the user's job.**
