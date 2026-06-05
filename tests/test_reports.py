"""Phase 4: REDUNDANT / MISSING / CONTRADICTION findings over the verdicts (architecture §5)."""

from dbt_column_lineage.ir import (
    ColumnRef,
    LineageEdge,
    LineageResult,
    LineageType,
    ModelOperation,
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
    assert d["summary"] == {
        "REDUNDANT": 0, "REDUNDANT_STRUCTURAL": 0, "MISSING": 0, "UNCOVERED": 0,
        "CONTRADICTION": 1, "relies_on_data": 3,
    }
    assert d["findings"]["CONTRADICTION"][0]["column"] == "c"


def test_redundant_structural_from_coalesce_not_null():
    # not_null test on COALESCE(x, 'n/a') -> guaranteed by this model, not inherited
    edges = (
        _edge("model.m", "v", ROOT, "x",
              TransformStep(TransformKind.COALESCE, {"default": "'n/a'", "arg_index": 0, "arg_count": 2})),
    )
    result = LineageResult(edges=edges)
    guarantees = [DeclaredGuarantee("model.m", "v", NN)]  # untested upstream; established here
    report = analyze(result, guarantees, kinds=(NN,))
    struct = report.of(ReportKind.REDUNDANT_STRUCTURAL)
    assert [(f.asset, f.column) for f in struct] == [("model.m", "v")]
    assert report.of(ReportKind.REDUNDANT) == []  # not the inherited kind
    assert "COALESCE" in struct[0].reason


def test_redundant_structural_from_group_by_unique():
    from dbt_test_lineage.verdict import GuaranteeKind

    edges = (_edge("model.g", "k", ROOT, "k", TransformStep(TransformKind.IDENTITY, {})),)
    ops = (ModelOperation(asset="model.g", grain=("k",)),)
    result = LineageResult(edges=edges, operations=ops)
    guarantees = [DeclaredGuarantee("model.g", "k", GuaranteeKind.UNIQUE)]
    report = analyze(result, guarantees, kinds=(GuaranteeKind.UNIQUE,))
    struct = report.of(ReportKind.REDUNDANT_STRUCTURAL)
    assert [(f.asset, f.column) for f in struct] == [("model.g", "k")]


def test_inherited_redundant_stays_redundant():
    # the passthrough case must remain REDUNDANT (inherited), not structural
    result, guarantees = _scenario()
    report = analyze(result, guarantees, kinds=(NN,))
    assert [(f.asset, f.column) for f in report.of(ReportKind.REDUNDANT)] == [(MID, "id")]
    assert report.of(ReportKind.REDUNDANT_STRUCTURAL) == []


def test_findings_ranked_by_priority():
    # two missing columns: one is a PK (grain) feeding a downstream col, one is a leaf
    edges = (
        _edge(MID, "pk", ROOT, "id", TransformStep(TransformKind.CAST, {"to_type": "INT", "safe": True})),
        _edge(MID, "leaf", ROOT, "id", TransformStep(TransformKind.CAST, {"to_type": "INT", "safe": True})),
        _edge("model.down", "x", MID, "pk", TransformStep(TransformKind.IDENTITY, {})),
    )
    ops = (ModelOperation(asset=MID, grain=("pk",)),)
    result = LineageResult(edges=edges, operations=ops)
    report = analyze(result, [DeclaredGuarantee(ROOT, "id", NN)], kinds=(NN,))
    missing = report.of(ReportKind.MISSING)
    # the PK (grain + has a downstream dependent) must rank above the leaf
    assert missing[0].column == "pk"
    assert missing[0].priority > missing[-1].priority


def test_uncovered_flags_grain_column_with_no_coverage():
    # GRAIN model.g groups by k, but k has no not_null guarantee anywhere in its lineage
    edges = (_edge("model.g", "k", ROOT, "k", TransformStep(TransformKind.IDENTITY, {})),)
    ops = (ModelOperation(asset="model.g", grain=("k",)),)
    result = LineageResult(edges=edges, operations=ops)
    report = analyze(result, [], kinds=(NN,))  # no tests at all
    unc = report.of(ReportKind.UNCOVERED)
    assert [(f.asset, f.column) for f in unc] == [("model.g", "k")]
    assert report.coverage["not_null"]["uncovered"] >= 1


def test_uncovered_excludes_covered_grain():
    # same grain column, but now tested upstream -> it holds -> not uncovered
    edges = (_edge("model.g", "k", ROOT, "k", TransformStep(TransformKind.IDENTITY, {})),)
    ops = (ModelOperation(asset="model.g", grain=("k",)),)
    result = LineageResult(edges=edges, operations=ops)
    report = analyze(result, [DeclaredGuarantee(ROOT, "k", NN)], kinds=(NN,))
    assert report.of(ReportKind.UNCOVERED) == []  # model.g.k inherits PROVEN -> covered
