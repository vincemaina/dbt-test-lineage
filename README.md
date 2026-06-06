# dbt-test-lineage

**Find redundant, missing, and contradicted dbt tests by tracing whether `not_null` / `unique`
guarantees actually survive your transformations.**

dbt tests assert a guarantee at a point — but data flows. A `not_null` test on a source column says
nothing about the column three models downstream that's now behind a `LEFT JOIN` and a `TRY_CAST`. This
tool propagates each declared guarantee through the **column-level lineage** (via the sibling
[`dbt-column-lineage`](../dbt-column-lineage) engine) and tells you, per column, whether the guarantee is
**structurally backed, merely assumed, or already covered elsewhere** — with an auditable reason for
every call.

It's an **advisory report**, not a black box: every finding shows the propagation path that produced it,
and rests-on-uncertain-lineage findings are flagged low-confidence. Soundness over coverage — it only
says a test is removable when it can *prove* the guarantee holds without it.

## What it tells you

| Report | Meaning | Action |
|---|---|---|
| **REDUNDANT** | the guarantee is already proven by an **upstream test** + preserving transforms (names the anchor) | remove the test (while the upstream one stays) |
| **REDUNDANT_STRUCTURAL** | the guarantee is created by **this model's own SQL** (`GROUP BY` → unique, `COALESCE`/`COUNT` → not_null) | remove the test (structure guarantees it) |
| **MISSING** | a guarantee existed upstream and a transform **dropped it** (e.g. `LEFT JOIN`, `NULLIF`), untested here | add a test — a real coverage hole |
| **UNCOVERED** | a model's **primary key** (single-column grain) has no guarantee anywhere in its lineage | add a test on the key |
| **CONTRADICTION** | the lineage **proves** a tested guarantee can't hold (rare) | fix the model or the test |

Plus: per-kind **coverage** (raw + importance-weighted), **test leverage** (how far each test's guarantee
reaches), **consolidation** (which redundant tests collapse onto one upstream anchor), and — with a real
test run — the **time/$ cost** of the redundant tests.

## Install

Requires Python 3.12 and [`uv`](https://docs.astral.sh/uv/). The sibling `dbt-column-lineage` engine is
an editable path dependency.

```bash
uv sync
```

## Quick start

Point it at your dbt artifacts (`manifest.json` + optional `catalog.json`):

```bash
uv run dbt-test-lineage report target/manifest.json --catalog target/catalog.json
```

Iterating? Cache the (slow) lineage extraction so subsequent runs are instant:

```bash
uv run dbt-test-lineage report target/manifest.json --catalog target/catalog.json --cache .tl.pkl
```

### Useful flags

- `--assume-unique-key` — treat each model's `config.unique_key` as a `not_null`+`unique` guarantee on
  the PK. **Opt-in** (vanilla dbt doesn't enforce `unique_key`); turn it on if your project does (e.g. a
  `unique_key` override that auto-generates the tests).
- `--run-results target/run_results.json` — annotate redundant tests with their last-run status
  (passing = safe to remove; failing = investigate) and **price** them. Use a `dbt build`/`dbt test`
  artifact — a `dbt run`/`docs generate` one has no real test runtimes (the tool will warn).
- `--cost-per-hour <warehouse $/hr>` — estimate the $/run spent on removable redundant tests.
- `--limit N` — show only the top-N (highest priority) findings per category.
- `--json` — machine-readable output.

### CI gate (secondary)

```bash
uv run dbt-test-lineage check target/manifest.json --catalog target/catalog.json   # exits non-zero on contradictions
```
`check` is intentionally quiet — `CONTRADICTION` only fires when a violation is *provable*, so it almost
never false-alarms. Use `--strict` to also fail on `MISSING` coverage holes.

## Getting artifacts from dbt Cloud

There's no local `target/` in dbt Cloud — pull the artifacts from a run via the Administrative API, all
from the **same** `dbt build` run so the ids line up:

```bash
ACCT=...; JOB=...; TOKEN=...
RUN_ID=$(curl -s -H "Authorization: Token $TOKEN" \
  "https://cloud.getdbt.com/api/v2/accounts/$ACCT/runs/?job_definition_id=$JOB&order_by=-finished_at&limit=1" | jq '.data[0].id')
for art in manifest.json catalog.json run_results.json; do
  curl -s -H "Authorization: Token $TOKEN" \
    "https://cloud.getdbt.com/api/v2/accounts/$ACCT/runs/$RUN_ID/artifacts/$art" -o "prod_$art"
done
```

## How it works (and what it won't do)

- **Consumes facts, renders verdicts.** Lineage extraction lives entirely in `dbt-column-lineage`; this
  tool only reasons over the resulting IR. See [`docs/architecture.md`](docs/architecture.md).
- **Static only** — never queries the warehouse. A "proven" verdict means *the transforms guarantee it*,
  not *today's data satisfies it*.
- **Conservative both ways** — asserts a guarantee holds, or is violated, only when the facts prove it;
  otherwise `NOT_GUARANTEED`/`UNKNOWN`. A false "remove this test" costs more than a missed one.
- **MVP scope:** `not_null` + `unique`. `accepted_values` / `relationships` are designed-for but not yet
  implemented (the lattice generalizes). See [`ROADMAP.md`](ROADMAP.md) and
  [`docs/use-cases.md`](docs/use-cases.md).
