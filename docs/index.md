# dbt-test-lineage

Find **redundant, missing, and contradicted dbt tests** by propagating `not_null` / `unique` guarantees
through column-level lineage. It consumes the [`dbt-column-lineage`](../dbt-column-lineage) engine's IR
and renders verdicts — recording *facts → verdicts*, conservatively, with an auditable reason for every
finding. See the [README](https://github.com/) for a usage quick-start.

## How to read these docs

- **[Architecture](architecture.md)** — the source of truth: the guarantee-propagation model, the
  verdict lattice, per-transform rule tables, the reports, non-goals.
- **[Use cases](use-cases.md)** — prune redundant tests, find coverage holes, block provable
  contradictions, audit, trust-scoring.
- **[API reference](reference/)** — auto-generated per-module. Start high and click in:
    - `reports` — `analyze()` → the `Report` of findings (REDUNDANT / MISSING / UNCOVERED / …),
      coverage, leverage, consolidation, cost
    - `propagate` — the topological guarantee propagation + `column_confidence`
    - `rules` — the per-transform not_null/unique effect tables
    - `verdict` — the verdict lattice + `ColumnVerdict`
    - `tests_loader` — declared tests + the opt-in `unique_key` source + run_results
    - `cache` — the lineage result cache; `cli` — the Typer commands

## Pipeline at a glance

```
manifest.json (+ catalog.json)
        │  dbt-column-lineage.extract_lineage()   (cache.py wraps + caches this)
        ▼
   LineageResult ──┐
                   │  tests_loader.py  (declared guarantees: tests + opt-in unique_key)
                   ▼
   propagate.py    (seed guarantees → topological walk → ColumnVerdict per column, + confidence)
                   │
                   ▼
   reports.analyze()  →  Report (findings + coverage + leverage + consolidation + cost)
                   │
                   ▼
   cli.py  (report / check)
```
