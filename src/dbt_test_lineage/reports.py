"""Turn propagated verdicts + declared tests into actionable findings (architecture §5).

Three report kinds, biased toward what we can prove (a false alarm costs more than a miss):
- REDUNDANT     — a test whose guarantee is already PROVEN/ESTABLISHED upstream → safe to remove.
- MISSING       — an untested column that is NOT_GUARANTEED *and whose upstream held the guarantee*
                  (the guarantee was dropped by a transform and never re-tested) → a real coverage hole.
- CONTRADICTION — a test whose verdict is the (rare) provable VIOLATED → the only CI-failing finding.

A tested column that is merely NOT_GUARANTEED is NOT a finding — the test is load-bearing, doing real
work; it is surfaced only in the informational `relies_on_data` count.
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
    REDUNDANT = "REDUNDANT"
    MISSING = "MISSING"
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
    for kind in kinds:
        verdicts = propagate(result, guarantees, kind)
        tested = {(g.asset, g.column) for g in guarantees if g.kind == kind}

        for asset, column in tested:  # REDUNDANT / CONTRADICTION over tested columns
            cv = verdicts.get((asset, column))
            if cv is None:  # no incoming lineage (a source/seed-level test) — nothing to compare
                continue
            if cv.verdict.holds:
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

        for (asset, column), cv in verdicts.items():  # MISSING over untested columns
            if (asset, column) in tested or cv.verdict != Verdict.NOT_GUARANTEED:
                continue
            # only flag when the guarantee actually existed upstream and was dropped here
            dropped = [s for s in cv.path if s.effect == Effect.BREAK and _held(s.column, verdicts, tested)]
            if dropped:
                findings.append(
                    Finding(ReportKind.MISSING, asset, column, kind, cv.verdict,
                            f"upstream guarantee dropped by {dropped[-1].detail} and not re-tested", cv.path)
                )
    return Report(tuple(findings), relies_on_data)


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
        "findings": {k: by_kind.get(k, []) for k in (r.value for r in ReportKind)},
    }
