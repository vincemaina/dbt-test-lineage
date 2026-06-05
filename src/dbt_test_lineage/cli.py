"""CLI: `check` (CI gate) and `report` (advisory). Both drive the engine on a dbt manifest, load its
declared tests, propagate, and render findings (architecture §5)."""

import json
from pathlib import Path
from typing import Optional

import typer

from dbt_column_lineage.engine import extract_lineage

from dbt_test_lineage.reports import Finding, Report, ReportKind, analyze, report_to_dict
from dbt_test_lineage.tests_loader import (
    load_declared_guarantees,
    load_run_results,
    test_uid_index,
    unique_key_guarantees,
)

app = typer.Typer(help="Propagate dbt test guarantees through column lineage to find redundant, "
                       "missing, and contradicted tests.", no_args_is_help=True)

_MANIFEST = typer.Argument(..., help="Path to the dbt manifest.json")
_CATALOG = typer.Option(None, "--catalog", "-c", help="Path to catalog.json (optional; improves schema)")
_ASSUME_UK = typer.Option(
    False, "--assume-unique-key",
    help="Treat each model's config.unique_key as not_null+unique guarantees on the PK. Opt-in: enable "
         "only if your project enforces unique_key (e.g. auto-generates tests for it); vanilla dbt does not.",
)


def _run(manifest: Path, catalog: Optional[Path], assume_unique_key: bool) -> Report:
    result = extract_lineage(manifest, catalog)
    guarantees = load_declared_guarantees(manifest)
    if assume_unique_key:
        guarantees += unique_key_guarantees(manifest)
    return analyze(result, guarantees)


def _status(f: Finding, status_map: dict) -> str:
    statuses = status_map.get((f.asset, f.column, f.guarantee))
    if not statuses:
        return ""
    if any(s in ("fail", "error") for s in statuses):
        return " (last run: FAIL — investigate before removing)"
    if all(s == "pass" for s in statuses):
        return " (last run: pass — safe to remove)"
    return f" (last run: {','.join(sorted(set(statuses)))})"


def _render(report: Report, limit: int = 0, status_map: dict | None = None) -> None:
    status_map = status_map or {}
    for kind in ReportKind:
        rows = report.of(kind)  # already sorted worst-first by priority
        if not rows:
            continue
        shown = rows[:limit] if limit else rows
        suffix = f" (showing top {len(shown)})" if limit and len(rows) > limit else ""
        typer.secho(f"\n{kind.value} ({len(rows)}){suffix}", bold=True)
        for f in shown:
            run = _status(f, status_map) if kind.value.startswith("REDUNDANT") else ""
            typer.echo(f"  [p{f.priority}] {f.asset}.{f.column} [{f.guarantee.value}] — {f.reason}{run}")
            for step in f.path:
                typer.echo(f"        {step.effect.value}: {step.column} {step.detail}".rstrip())
    if report.coverage:
        typer.secho("\ncoverage", bold=True)
        for kind, c in report.coverage.items():
            total, wtotal = c["total"] or 1, c.get("weighted_total") or 1
            typer.echo(
                f"  {kind}: {c['covered']}/{c['total']} columns ({100 * c['covered'] // total}%), "
                f"importance-weighted {100 * c.get('weighted_covered', 0) // wtotal}% "
                f"— {c['uncovered']} uncovered"
            )
    low = [lv for lv in report.leverage if lv.reach == 0]
    if report.leverage:
        typer.secho("\ntest leverage", bold=True)
        typer.echo(f"  {len(low)} of {len(report.leverage)} tests have reach 0 "
                   "(guard only their own column — low leverage)")
    if report.consolidations:
        covered_total = sum(len(v) for v in report.consolidations.values())
        typer.secho("\nconsolidation", bold=True)
        typer.echo(f"  {covered_total} redundant tests collapse onto {len(report.consolidations)} "
                   "upstream anchors (test once at the anchor, remove the rest)")
    typer.echo(
        f"\nsummary: {len(report.of(ReportKind.REDUNDANT))} redundant (inherited), "
        f"{len(report.of(ReportKind.REDUNDANT_STRUCTURAL))} redundant (structural), "
        f"{len(report.of(ReportKind.MISSING))} missing, "
        f"{len(report.of(ReportKind.UNCOVERED))} uncovered keys, "
        f"{len(report.of(ReportKind.CONTRADICTION))} contradiction, "
        f"{report.relies_on_data} tests rely on data (load-bearing, ok)"
    )


def _status_map(manifest: Path, run_results: Optional[Path]) -> dict:
    """(asset, column, kind) -> [last-run statuses] for the tests on that column."""
    if not run_results:
        return {}
    runs = load_run_results(run_results)
    out: dict = {}
    for (asset, column, kind), uids in test_uid_index(manifest).items():
        statuses = [runs[u] for u in uids if u in runs]
        if statuses:
            out[(asset, column, kind)] = statuses
    return out


@app.command()
def report(manifest: Path = _MANIFEST, catalog: Optional[Path] = _CATALOG,
           assume_unique_key: bool = _ASSUME_UK,
           run_results: Optional[Path] = typer.Option(
               None, "--run-results",
               help="dbt run_results.json — annotate redundant tests with last-run status "
                    "(passing = safe to remove; failing = investigate first)"),
           limit: int = typer.Option(0, "--limit", "-n",
                                     help="Show only the top-N (highest priority) findings per category"),
           as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of text")) -> None:
    """Advisory report: redundant / missing / contradicted tests, each with its propagation path."""
    rep = _run(manifest, catalog, assume_unique_key)
    if as_json:
        typer.echo(json.dumps(report_to_dict(rep), indent=2))
    else:
        _render(rep, limit, _status_map(manifest, run_results))


@app.command()
def check(manifest: Path = _MANIFEST, catalog: Optional[Path] = _CATALOG,
          assume_unique_key: bool = _ASSUME_UK,
          strict: bool = typer.Option(False, "--strict",
                                      help="Also fail on MISSING coverage holes")) -> None:
    """CI gate: exit non-zero on provable contradictions (and, with --strict, on missing coverage)."""
    rep = _run(manifest, catalog, assume_unique_key)
    _render(rep)
    contradictions = len(rep.of(ReportKind.CONTRADICTION))
    missing = len(rep.of(ReportKind.MISSING))
    failed = contradictions > 0 or (strict and missing > 0)
    if failed:
        typer.secho(
            f"\nFAILED: {contradictions} contradiction(s)"
            + (f", {missing} missing (strict)" if strict else ""),
            fg=typer.colors.RED, bold=True,
        )
        raise typer.Exit(code=1)
    typer.secho("\nPASSED", fg=typer.colors.GREEN, bold=True)


if __name__ == "__main__":  # pragma: no cover
    app()
