"""Phase 4: REDUNDANT / MISSING / CONTRADICTION findings over the verdicts (architecture §5)."""

from dbt_column_lineage.ir import (
    ColumnRef,
    LineageEdge,
    LineageResult,
    LineageType,
    TransformKind,
    TransformStep,
)

from dbt_test_lineage.reports import (
    Finding,
    Report,
    ReportKind,
    analyze,
    report_to_dict,
)
from dbt_test_lineage.tests_loader import DeclaredGuarantee
from dbt_test_lineage.verdict import GuaranteeKind, Verdict

NN = GuaranteeKind.NOT_NULL
ROOT, MID, RISKY = "model.root", "model.mid", "model.risky"


def _edge(down, down_col, up, up_col, *steps):
    return LineageEdge(
        ColumnRef(down, down_col), ColumnRef(up, up_col), LineageType.DIRECT, tuple(steps)
    )


def _scenario():
    edges = [
        _edge(MID, "id", ROOT, "id", TransformStep(TransformKind.IDENTITY, {})),
        _edge(RISKY, "id", ROOT, "id", TransformStep(TransformKind.CAST, {"to_type": "INT", "safe": True})),
    ]
    guarantees = [
        DeclaredGuarantee(ROOT, "id", NN),  # the source guarantee (seed)
        DeclaredGuarantee(MID, "id", NN),  # redundant: mid.id is a pure passthrough of root.id
    ]
    return LineageResult(edges=tuple(edges)), guarantees


def test_redundant_detected():
    result, guarantees = _scenario()
    report = analyze(result, guarantees, kinds=(NN,))
    red = report.of(ReportKind.REDUNDANT)
    assert [(f.asset, f.column) for f in red] == [(MID, "id")]
    assert red[0].verdict == Verdict.PROVEN


def test_missing_detected_when_guarantee_dropped():
    result, guarantees = _scenario()
    report = analyze(result, guarantees, kinds=(NN,))
    miss = report.of(ReportKind.MISSING)
    # risky.id: TRY_CAST of the tested root.id, untested -> coverage hole
    assert [(f.asset, f.column) for f in miss] == [(RISKY, "id")]
    assert "dropped" in miss[0].reason


def test_no_false_contradiction():
    result, guarantees = _scenario()
    report = analyze(result, guarantees, kinds=(NN,))
    assert report.of(ReportKind.CONTRADICTION) == []  # NOT_GUARANTEED is never a contradiction


def test_relies_on_data_counts_tested_not_guaranteed():
    result, _ = _scenario()
    # test risky.id directly -> it's NOT_GUARANTEED -> load-bearing, not a finding
    guarantees = [DeclaredGuarantee(ROOT, "id", NN), DeclaredGuarantee(RISKY, "id", NN)]
    report = analyze(result, guarantees, kinds=(NN,))
    assert report.relies_on_data == 1
    assert all(f.asset != RISKY for f in report.findings)  # not flagged as missing/redundant


def test_report_to_dict_shape():
    f = Finding(ReportKind.CONTRADICTION, "model.x", "c", NN, Verdict.VIOLATED, "proven null")
    d = report_to_dict(Report((f,), relies_on_data=3))
    assert d["summary"] == {"REDUNDANT": 0, "MISSING": 0, "CONTRADICTION": 1, "relies_on_data": 3}
    assert d["findings"]["CONTRADICTION"][0]["column"] == "c"
