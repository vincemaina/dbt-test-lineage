# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

**Working MVP+ (Phases 0–4 done, plus prioritization, confidence, accuracy eval, caching).** not_null +
unique propagation; reports REDUNDANT (inherited + structural) / MISSING / UNCOVERED / CONTRADICTION;
coverage (raw + weighted); test leverage; consolidation; redundant-test cost (with provenance guardrail);
opt-in `unique_key` source; per-finding confidence; `report`/`check` CLI with `--cache`. ~89 tests, lint
clean. Read these first:

- [`README.md`](README.md) — what it does + quick start.
- [`docs/architecture.md`](docs/architecture.md) — **source of truth**: locked decisions, the
  guarantee-propagation model, per-transform rule tables, outputs, non-goals, stack.
- [`ROADMAP.md`](ROADMAP.md) — phased plan + status; what's next (diff/regression mode,
  accepted_values/relationships).

Stack: **Python 3.12 · `uv` · `pytest` · `Typer` · `ruff` (line-length 100)**, `src/` layout, editable
path dependency on the sibling `dbt-column-lineage` engine.

## What this project is

`dbt-test-lineage` is the **second of two projects**. The first,
[`dbt-column-lineage`](../dbt-column-lineage) (sibling repo), is a finished, general-purpose column-
lineage engine that emits a fact-only lineage IR. **This tool consumes that IR and renders verdicts**:
it propagates declared dbt test guarantees (`not_null`, `unique`) through the recorded transforms to
find where guarantees are **contradicted**, **missing**, or **redundant**.

The division is load-bearing: **the engine records facts; this tool renders verdicts.** All
guarantee/test semantics live here; no lineage extraction lives here. Do not push verdict logic back
into the engine, and do not re-derive lineage here — call the engine.

## The settled approach, in one paragraph

Consume `dbt-column-lineage` **as a library** (path dependency; call `extract_lineage()` for the typed
`LineageResult`). Load declared tests from `manifest.json` test nodes. Seed `not_null`/`unique`
guarantees on tested columns and **propagate them in topological order** over the column lineage graph,
applying per-transform rules (architecture §4) and multi-edge combination semantics (coalesce = OR,
union/case = AND). Each `(column, guarantee)` gets a verdict — `PROVEN` / `VIOLATED` / `UNKNOWN` /
`ESTABLISHED` — **only when the facts prove it** (conservative both ways; `UNKNOWN` is the default).
Two outputs: a **CI gate** (fails on contradictions) and an **advisory report** (missing/redundant
tests). Every verdict carries the propagation path that explains it. See architecture §2 for the full
decision list.

## Design constraints (load-bearing)

- **Sound and explainable.** Assert `PROVEN` only when provable, `VIOLATED` only when provable; else
  `UNKNOWN`. A false contradiction erodes trust faster than a missed one — bias toward `UNKNOWN`. Every
  verdict must carry its propagation path; never assert without a why.
- **Static only.** No warehouse access, no row data, no network. A `PROVEN` verdict means "the
  transforms guarantee it," not "today's data satisfies it."
- **Facts in, verdicts out.** Inputs are the engine's IR + dbt artifacts; YAML is never read directly
  (the compiled manifest is the contract).
- **Library, CLI, and CI usable.** Importable Python API + a Typer CLI suitable for CI exit codes.
- **Modular boundaries:** test loading → guarantee seeding → propagation → report generation → CLI.

## Working practices (the user's standing conventions)

- **Git is the user's job. Do not run git commands** — no commits, pushes, branches, tags, rebases,
  merges, stashes. Suggest commit messages; let the user execute. If told to perform a git action once,
  treat it as a one-time exception, not a new default.
- **CLAUDE.md in every subfolder**, describing every file/subfolder it contains. Keep small and current.
- **Plan before building.** Non-trivial work gets a plan first (research included). Confirm
  architectural decisions with the user before significant code.
- **Roadmaps as the entry point.** Top-level `ROADMAP.md` linking per-phase detail, not a monolith.
- **Research before substantial work** (tools, dbt/SQL semantics) — it measurably improves results.
- **Tests guard code and practices.** Fast suite; hand-verified rule fixtures are the correctness oracle
  for propagation (mirror the engine's eval-harness discipline). Prefer end-to-end self-verification
  against the engine's `.repos/lyst-dbt` real-repo clone.

## Relationship to the engine

The engine's IR is the input contract. Key facts this tool relies on (all already emitted): transform
chains with `CAST {safe}`, `CASE {else_null}`, `COALESCE {arg_index,arg_count,default}`,
`AGGREGATION {distinct}`, `JOIN {introduces_nulls}`, `WINDOW {frame}`, `STRUCT_ACCESS`, `UNNEST`,
`EXPRESSION {func/op}`; `LineageResult.operations` (`may_multiply_rows`, `grouped`, `distinct`);
`controls` (GROUP_BY grain, join keys); `self_references`. If a needed fact is missing, prefer adding
it to the engine (facts) over inferring it here (verdicts).
