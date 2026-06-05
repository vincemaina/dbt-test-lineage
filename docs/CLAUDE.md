# docs/

Design documentation for dbt-test-lineage.

## Contents

- [`architecture.md`](./architecture.md) — **source of truth**: locked decisions, the guarantee-
  propagation model (state lattice, topological walk), per-transform rule tables (not_null / unique),
  multi-edge combination semantics, the three reports, integration data flow, non-goals, stack.
- [`use-cases.md`](./use-cases.md) — the directional map of what the tool is *for* (prune redundant
  tests, find coverage holes, block provable contradictions, audit, …); keeps the engine + reports
  pointed at real value.

Per-phase design notes will be added here as each roadmap phase is started (e.g. `phase-2-not-null.md`).
