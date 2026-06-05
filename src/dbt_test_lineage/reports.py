"""Turn propagated verdicts + declared tests into actionable findings (architecture §5).

Report kinds, biased toward what we can prove (a false alarm costs more than a miss):
- REDUNDANT            — INHERITED: the guarantee is already PROVEN by an upstream test + preserving
                         transforms (a passthrough re-test) → safe to remove while the upstream test stays.
- REDUNDANT_STRUCTURAL — the test is guaranteed by THIS model's own SQL (`GROUP BY` grain makes a column
                         unique; `COALESCE`/`COUNT`/`ROW_NUMBER` make it not_null) → the test re-checks
                         what the structure already guarantees, independent of any upstream test.
- MISSING       — an untested column that is NOT_GUARANTEED *and whose upstream held the guarantee*
                  (the guarantee was dropped by a transform and never re-tested) → a real coverage hole.
- UNCOVERED     — a **grain/key** column with NO guarantee anywhere in its lineage (untested, not
                  structurally guaranteed, nothing upstream held it) → a key with zero coverage. Scoped
                  to grain columns so the list stays actionable; the full picture is the `coverage` stat.
- CONTRADICTION — a test whose verdict is the (rare) provable VIOLATED → the only CI-failing finding.

A tested column that is merely NOT_GUARANTEED is NOT a finding — the test is load-bearing, doing real
work; it is surfaced only in the informational `relies_on_data` count.

`coverage` (per kind) is the whole-population view: of the columns the lineage reaches, how many are
covered (tested or structurally guaranteed) vs not — the "how much is untested" number, independent of
the grain-scoped UNCOVERED findings.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

from dbt_column_lineage.ir import LineageResult

from dbt_test_lineage.propagate import propagate
from dbt_test_lineage.tests_loader import DeclaredGuarantee
from dbt_test_lineage.verdict import (
    ColumnVerdict,
    Effect,
    GuaranteeKind,
    PropagationStep,
    Verdict,
)

_DEFAULT_KINDS = (GuaranteeKind.NOT_NULL, GuaranteeKind.UNIQUE)


class ReportKind(str, Enum):
    REDUNDANT = "REDUNDANT"  # inherited: guarantee already proven by an UPSTREAM test + passthrough
    REDUNDANT_STRUCTURAL = "REDUNDANT_STRUCTURAL"  # this model's own logic guarantees it (GROUP BY, COALESCE, …)
    MISSING = "MISSING"
    UNCOVERED = "UNCOVERED"
    CONTRADICTION = "CONTRADICTION"


@dataclass(frozen=True)
class Finding:
    kind: ReportKind
    asset: str
    column: str
    guarantee: GuaranteeKind
    verdict: Verdict
    reason: str
    path: tuple[PropagationStep, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return f"{self.kind.value}: {self.asset}.{self.column} [{self.guarantee.value}] — {self.reason}"


@dataclass(frozen=True)
class Report:
    findings: tuple[Finding, ...]
    relies_on_data: int = 0  # tested columns that are NOT_GUARANTEED (load-bearing, not a problem)
    coverage: dict = field(default_factory=dict)  # kind -> {total, covered, uncovered}

    def of(self, kind: ReportKind) -> list[Finding]:
        return [f for f in self.findings if f.kind == kind]


def _parse_col(colstr: str) -> tuple[str, str]:
    asset, _, column = colstr.rpartition(".")
    return asset, column


def _held(colstr: str, verdicts: dict[tuple[str, str], ColumnVerdict], tested: set) -> bool:
    """Did the column carry the guarantee upstream — i.e. is it tested, or its verdict holds?"""
    key = _parse_col(colstr)
    if key in tested:
        return True
    cv = verdicts.get(key)
    return cv is not None and cv.verdict.holds


def analyze(
    result: LineageResult,
    guarantees: list[DeclaredGuarantee],
    kinds: tuple[GuaranteeKind, ...] = _DEFAULT_KINDS,
) -> Report:
    findings: list[Finding] = []
    relies_on_data = 0
    coverage: dict = {}
    # UNCOVERED findings are scoped to SINGLE-column grains — a model's natural primary key — so the list
    # stays actionable. (Every grain column would be ~noise: many GROUP BY keys are nullable dimensions;
    # the whole-population picture is the `coverage` stat instead.)
    grain_cols = {(o.asset, o.grain[0]) for o in result.operations if len(o.grain) == 1}
    for kind in kinds:
        verdicts = propagate(result, guarantees, kind)  # seeds from explicit tests AND implied (config)
        explicit = {(g.asset, g.column) for g in guarantees if g.kind == kind and g.source == "test"}
        implied = {(g.asset, g.column) for g in guarantees if g.kind == kind and g.source != "test"}
        asserted = explicit | implied  # any column whose guarantee is declared (test or config)
        held = {k for k, cv in verdicts.items() if cv.verdict.holds}
        universe = set(verdicts) | asserted  # every column the lineage can speak about
        covered = asserted | held  # config-implied guarantees count as coverage too
        uncovered = universe - covered
        coverage[kind.value] = {
            "total": len(universe), "covered": len(covered), "uncovered": len(uncovered)
        }

        for asset, column in explicit:  # findings report only on EXPLICIT tests (removable test nodes)
            cv = verdicts.get((asset, column))
            if cv is None:  # no incoming lineage (a source/seed-level test) — nothing to compare
                continue
            if cv.verdict == Verdict.ESTABLISHED:  # guaranteed by this model's own logic
                est = next((s for s in cv.path if s.effect == Effect.ESTABLISH), None)
                why = "structurally guaranteed by this model"
                if est:
                    why += f" ({est.detail})"
                findings.append(
                    Finding(ReportKind.REDUNDANT_STRUCTURAL, asset, column, kind, cv.verdict, why, cv.path)
                )
            elif cv.verdict == Verdict.PROVEN:  # inherited from an upstream test via passthrough
                findings.append(
                    Finding(ReportKind.REDUNDANT, asset, column, kind, cv.verdict,
                            "guarantee already proven by upstream test + preserving transforms", cv.path)
                )
            elif cv.verdict == Verdict.VIOLATED:
                findings.append(
                    Finding(ReportKind.CONTRADICTION, asset, column, kind, cv.verdict,
                            "lineage proves the guarantee cannot hold", cv.path)
                )
            elif cv.verdict == Verdict.NOT_GUARANTEED:
                relies_on_data += 1

        missing_keys: set = set()
        for (asset, column), cv in verdicts.items():  # MISSING over uncovered columns
            if (asset, column) in asserted or cv.verdict != Verdict.NOT_GUARANTEED:
                continue
            # only flag when the guarantee actually existed upstream and was dropped here
            dropped = [s for s in cv.path if s.effect == Effect.BREAK and _held(s.column, verdicts, asserted)]
            if dropped:
                missing_keys.add((asset, column))
                findings.append(
                    Finding(ReportKind.MISSING, asset, column, kind, cv.verdict,
                            f"upstream guarantee dropped by {dropped[-1].detail} and not re-tested", cv.path)
                )

        for asset, column in sorted(uncovered):  # UNCOVERED — grain/key columns with zero coverage
            if (asset, column) in missing_keys or (asset, column) not in grain_cols:
                continue
            cv = verdicts.get((asset, column))
            findings.append(
                Finding(ReportKind.UNCOVERED, asset, column, kind,
                        cv.verdict if cv else Verdict.UNKNOWN,
                        f"primary-key column (single-column grain) with no {kind.value} guarantee "
                        "anywhere in its lineage",
                        cv.path if cv else ())
            )
    return Report(tuple(findings), relies_on_data, coverage)


def finding_to_dict(f: Finding) -> dict:
    return {
        "kind": f.kind.value,
        "asset": f.asset,
        "column": f.column,
        "guarantee": f.guarantee.value,
        "verdict": f.verdict.value,
        "reason": f.reason,
        "path": [{"column": s.column, "effect": s.effect.value, "detail": s.detail} for s in f.path],
    }


def report_to_dict(report: Report) -> dict:
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for f in report.findings:
        by_kind[f.kind.value].append(finding_to_dict(f))
    return {
        "summary": {k.value: len(report.of(k)) for k in ReportKind} | {
            "relies_on_data": report.relies_on_data
        },
        "coverage": report.coverage,
        "findings": {k: by_kind.get(k, []) for k in (r.value for r in ReportKind)},
    }
