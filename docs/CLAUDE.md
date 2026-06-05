# docs/

Design documentation for dbt-test-lineage.

## Contents

- [`architecture.md`](./architecture.md) — **source of truth**: locked decisions, the guarantee-
  propagation model (state lattice, topological walk), per-transform rule tables (not_null / unique),
  multi-edge combination semantics, the three reports, integration data flow, non-goals, stack.

Per-phase design notes will be added here as each roadmap phase is started (e.g. `phase-2-not-null.md`).
