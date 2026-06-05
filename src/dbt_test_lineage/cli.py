"""CLI: `check` (CI gate) and `report` (advisory). Both drive the engine on a dbt manifest, load its
declared tests, propagate, and render findings (architecture §5)."""

import json
from pathlib import Path
from typing import Optional

import typer

from dbt_column_lineage.engine import extract_lineage

from dbt_test_lineage.reports import Report, ReportKind, analyze, report_to_dict
from dbt_test_lineage.tests_loader import load_declared_guarantees, unique_key_guarantees

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


def _render(report: Report, limit: int = 0) -> None:
    for kind in ReportKind:
        rows = report.of(kind)  # already sorted worst-first by priority
        if not rows:
            continue
        shown = rows[:limit] if limit else rows
        suffix = f" (showing top {len(shown)})" if limit and len(rows) > limit else ""
        typer.secho(f"\n{kind.value} ({len(rows)}){suffix}", bold=True)
        for f in shown:
            typer.echo(f"  [p{f.priority}] {f.asset}.{f.column} [{f.guarantee.value}] — {f.reason}")
            for step in f.path:
                typer.echo(f"        {step.effect.value}: {step.column} {step.detail}".rstrip())
    if report.coverage:
        typer.secho("\ncoverage", bold=True)
        for kind, c in report.coverage.items():
            total = c["total"] or 1
            typer.echo(f"  {kind}: {c['covered']}/{c['total']} columns guaranteed "
                       f"({100 * c['covered'] // total}%), {c['uncovered']} uncovered")
    typer.echo(
        f"\nsummary: {len(report.of(ReportKind.REDUNDANT))} redundant (inherited), "
        f"{len(report.of(ReportKind.REDUNDANT_STRUCTURAL))} redundant (structural), "
        f"{len(report.of(ReportKind.MISSING))} missing, "
        f"{len(report.of(ReportKind.UNCOVERED))} uncovered keys, "
        f"{len(report.of(ReportKind.CONTRADICTION))} contradiction, "
        f"{report.relies_on_data} tests rely on data (load-bearing, ok)"
    )


@app.command()
def report(manifest: Path = _MANIFEST, catalog: Optional[Path] = _CATALOG,
           assume_unique_key: bool = _ASSUME_UK,
           limit: int = typer.Option(0, "--limit", "-n",
                                     help="Show only the top-N (highest priority) findings per category"),
           as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of text")) -> None:
    """Advisory report: redundant / missing / contradicted tests, each with its propagation path."""
    rep = _run(manifest, catalog, assume_unique_key)
    if as_json:
        typer.echo(json.dumps(report_to_dict(rep), indent=2))
    else:
        _render(rep, limit)


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
