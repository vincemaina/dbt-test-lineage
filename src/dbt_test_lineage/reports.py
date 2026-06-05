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
from dataclasses import dataclass, field, replace
from enum import Enum

from dbt_column_lineage.ir import Confidence, LineageResult, LineageType

from dbt_test_lineage.propagate import column_confidence, propagate
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
    priority: int = 0  # higher = act first: key-ness (is a PK/grain) + downstream blast radius
    confidence: Confidence = Confidence.HIGH  # LOW if the lineage it rests on is uncertain

    def __str__(self) -> str:
        return f"{self.kind.value}: {self.asset}.{self.column} [{self.guarantee.value}] — {self.reason}"


@dataclass(frozen=True)
class TestLeverage:
    """How far an explicit test's guarantee reaches: the number of downstream columns where it still
    holds, reachable from the tested column. Low reach = the test guards little (the structure kills the
    guarantee right away); high reach = it protects a wide downstream footprint."""

    asset: str
    column: str
    guarantee: GuaranteeKind
    reach: int


@dataclass(frozen=True)
class Report:
    findings: tuple[Finding, ...]
    relies_on_data: int = 0  # tested columns that are NOT_GUARANTEED (load-bearing, not a problem)
    coverage: dict = field(default_factory=dict)  # kind -> {total, covered, uncovered, weighted_*}
    leverage: tuple[TestLeverage, ...] = ()  # per explicit test, low-reach first
    consolidations: dict = field(default_factory=dict)  # anchor "asset.col" -> redundant tests it covers

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


def _anchor(start: tuple, up_adj: dict, asserted: set, held: set) -> tuple | None:
    """Climb upstream through holding columns to the nearest column that carries a declared guarantee —
    the test that makes `start` redundant (so a chain of re-tests can collapse to this one anchor)."""
    seen: set = set()
    stack = [start]
    while stack:
        for up in up_adj.get(stack.pop(), ()):
            if up in seen:
                continue
            seen.add(up)
            if up in asserted:
                return up
            if up in held:  # keep climbing only while the guarantee is preserved
                stack.append(up)
    return None


def _reach(start: tuple, down_adj: dict, held: set) -> int:
    """Count downstream columns reachable from `start` through columns where the guarantee still holds —
    the test's downstream footprint. Stops where the guarantee dies. Cycle-safe."""
    seen: set = set()
    stack = [start]
    while stack:
        for nxt in down_adj.get(stack.pop(), ()):
            if nxt not in seen and nxt in held:
                seen.add(nxt)
                stack.append(nxt)
    return len(seen)


def analyze(
    result: LineageResult,
    guarantees: list[DeclaredGuarantee],
    kinds: tuple[GuaranteeKind, ...] = _DEFAULT_KINDS,
) -> Report:
    findings: list[Finding] = []
    leverage: list[TestLeverage] = []
    relies_on_data = 0
    coverage: dict = {}
    # UNCOVERED findings are scoped to SINGLE-column grains — a model's natural primary key — so the list
    # stays actionable. (Every grain column would be ~noise: many GROUP BY keys are nullable dimensions;
    # the whole-population picture is the `coverage` stat instead.)
    grain_cols = {(o.asset, o.grain[0]) for o in result.operations if len(o.grain) == 1}
    # downstream + upstream adjacency and blast radius, computed once over the DIRECT graph
    out_degree: dict = defaultdict(int)
    down_adj: dict = defaultdict(list)
    up_adj: dict = defaultdict(list)
    for e in result.edges:
        if e.lineage_type == LineageType.DIRECT:
            up, down = (e.upstream.asset, e.upstream.column), (e.downstream.asset, e.downstream.column)
            out_degree[up] += 1
            down_adj[up].append(down)
            up_adj[down].append(up)
    consolidations: dict = defaultdict(list)  # anchor "asset.col" -> redundant tests it covers

    def weight(key: tuple) -> int:  # column importance: base + blast radius + key-ness
        return 1 + min(out_degree.get(key, 0), 10) + (10 if key in grain_cols else 0)

    confidence = column_confidence(result)  # per-column lineage certainty (kind-independent)

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
            "total": len(universe), "covered": len(covered), "uncovered": len(uncovered),
            # importance-weighted: a covered high-blast-radius/PK column counts for more than a leaf
            "weighted_total": sum(weight(k) for k in universe),
            "weighted_covered": sum(weight(k) for k in covered),
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
                anchor = _anchor((asset, column), up_adj, asserted - {(asset, column)}, held)
                why = "guarantee already proven upstream + preserving transforms"
                if anchor:
                    why += f" — covered by the guarantee at {anchor[0]}.{anchor[1]}"
                    consolidations[f"{anchor[0]}.{anchor[1]}"].append(f"{asset}.{column}")
                findings.append(
                    Finding(ReportKind.REDUNDANT, asset, column, kind, cv.verdict, why, cv.path)
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

        for key in explicit:  # test leverage: downstream footprint where the guarantee still holds
            leverage.append(TestLeverage(key[0], key[1], kind, _reach(key, down_adj, held)))

    # priority = blast radius + key-ness (= weight without the base 1). Sorts findings worst-first.
    ranked = sorted(
        (
            replace(
                f,
                priority=weight((f.asset, f.column)) - 1,
                confidence=confidence.get((f.asset, f.column), Confidence.HIGH),
            )
            for f in findings
        ),
        key=lambda f: -f.priority,
    )
    leverage.sort(key=lambda lv: lv.reach)  # least-leverage tests first
    return Report(tuple(ranked), relies_on_data, coverage, tuple(leverage), dict(consolidations))


def finding_to_dict(f: Finding) -> dict:
    return {
        "kind": f.kind.value,
        "asset": f.asset,
        "column": f.column,
        "guarantee": f.guarantee.value,
        "verdict": f.verdict.value,
        "priority": f.priority,
        "confidence": f.confidence.value,
        "reason": f.reason,
        "path": [{"column": s.column, "effect": s.effect.value, "detail": s.detail} for s in f.path],
    }


def redundant_cost(
    report: Report,
    test_index: dict,
    timing: dict[str, float],
    dollars_per_hour: float = 0.0,
) -> dict:
    """Price the removable (REDUNDANT + REDUNDANT_STRUCTURAL) tests using per-test `execution_time` from
    run_results: seconds spent on tests we could drop, as a share of total test time, optionally in $."""
    removable_uids: set = set()
    for f in report.findings:
        if f.kind in (ReportKind.REDUNDANT, ReportKind.REDUNDANT_STRUCTURAL):
            removable_uids.update(test_index.get((f.asset, f.column, f.guarantee), ()))
    redundant_secs = sum(timing.get(u, 0.0) for u in removable_uids)
    total_test_secs = sum(t for u, t in timing.items() if u.startswith("test."))
    out = {
        "removable_tests": len(removable_uids),
        "redundant_seconds": round(redundant_secs, 3),
        "total_test_seconds": round(total_test_secs, 3),
        "pct_of_test_time": round(100 * redundant_secs / total_test_secs, 1) if total_test_secs else 0.0,
    }
    if dollars_per_hour:
        out["dollars_per_run"] = round(redundant_secs / 3600 * dollars_per_hour, 4)
    return out


def report_to_dict(report: Report) -> dict:
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for f in report.findings:
        by_kind[f.kind.value].append(finding_to_dict(f))
    return {
        "summary": {k.value: len(report.of(k)) for k in ReportKind} | {
            "relies_on_data": report.relies_on_data
        },
        "coverage": report.coverage,
        "leverage": [
            {"asset": lv.asset, "column": lv.column, "guarantee": lv.guarantee.value, "reach": lv.reach}
            for lv in report.leverage
        ],
        "consolidations": report.consolidations,
        "findings": {k: by_kind.get(k, []) for k in (r.value for r in ReportKind)},
    }
