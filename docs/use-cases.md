# Use cases — dbt-test-lineage

What the assurance tool is *for* — the directional map that keeps the propagation engine and reports
pointed at real value. Kept current as priorities shift. Everything here is some reading of the verdict
lattice (`PROVEN`/`ESTABLISHED`/`NOT_GUARANTEED`/`VIOLATED`/`UNKNOWN`) over the lineage IR; see
[`architecture.md`](./architecture.md).

The throughline: dbt tests assert guarantees at a point, but data flows. This tool tells you, **per
column, whether a guarantee is structurally backed, merely assumed, or already covered elsewhere** —
and explains why with a propagation path.

## Primary (the MVP earns these)

1. **Prune redundant tests** (cut CI time). A `not_null`/`unique` test whose guarantee is already
   `PROVEN`/`ESTABLISHED` upstream + preserving transforms is re-checking something structure
   guarantees → safe to remove. The most defensible signal (only fires on proof). *Report:* REDUNDANT.

2. **Find coverage holes** (catch real risk). An **untested** column that is `NOT_GUARANTEED` — a
   transform on its path admits a null/duplicate and nothing guards it → a place a test belongs.
   *Report:* MISSING.

3. **Block provable contradictions in CI.** A column tested `not_null`/`unique` whose lineage *proves*
   it cannot hold (`VIOLATED` — literal NULL, provable fan-out). Rare by design so the gate never
   false-alarms; `NOT_GUARANTEED → fail` is an opt-in strict mode. *Report:* CONTRADICTION + `check`.

## Secondary

4. **Refactor / change safety.** "Did my model change break a guarantee a downstream test relies on?"
   Re-run after a change and diff the verdicts — a column that flipped `PROVEN → NOT_GUARANTEED` is a
   regression a downstream test now silently depends on data for.

5. **Guarantee audit / onboarding.** A map of where each `not_null`/`unique` is *structurally enforced*
   vs *merely assumed* (relies on data). Helps a new team see which invariants are load-bearing and
   which are wishful.

6. **PR-review signal.** On a new/changed model, flag key columns (grain, ids) that are `NOT_GUARANTEED`
   and untested — "you added a model whose primary key can duplicate and isn't tested."

7. **Test trust / confidence scoring.** Rank tests by how structurally backed they are — a `not_null`
   on a pure passthrough from a tested source is low-information; one guarding a `TRY_CAST` or outer
   join is doing real work.

## Future

8. **Declared-assumption verification** (architecture §7). Generalize from "does a *test* survive?" to
   "does a *declared assumption* hold?" — e.g. compare an expected column data type from YAML/manifest
   metadata against the engine's inferred upstream type, or probe a single column's assumption upstream
   on demand. The verdict/path IR is kept general enough to carry a type/value assumption, not only
   not_null/unique.

## Design implication

The tool's worth is **trust**: a false contradiction costs more than a missed one. So the reports lead
with what we can *prove* (REDUNDANT, and CONTRADICTION only when provable), treat "admits a violation"
as advisory (`NOT_GUARANTEED`), and always attach the propagation path so a human can audit any verdict.
