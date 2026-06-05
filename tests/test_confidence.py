"""Confidence: findings resting on uncertain lineage (UNKNOWN transforms, warnings, unknown schema)
are flagged LOW so they can be verified before acting."""

from dbt_column_lineage.ir import (
    ColumnRef,
    Confidence,
    LineageEdge,
    LineageResult,
    LineageType,
    SchemaProvenance,
    TransformKind,
    TransformStep,
)

from dbt_test_lineage.propagate import column_confidence

ROOT, MID, DOWN = "model.root", "model.mid", "model.down"


def _edge(down, down_col, up, up_col, *steps, provenance=SchemaProvenance.CATALOG, warnings=()):
    return LineageEdge(
        ColumnRef(down, down_col), ColumnRef(up, up_col), LineageType.DIRECT, tuple(steps),
        schema_provenance=provenance, warnings=tuple(warnings),
    )


def test_unknown_transform_is_low_confidence():
    edges = (_edge(MID, "x", ROOT, "a", TransformStep(TransformKind.UNKNOWN, {})),)
    conf = column_confidence(LineageResult(edges=edges))
    assert conf[(MID, "x")] == Confidence.LOW


def test_clean_passthrough_is_high_confidence():
    edges = (_edge(MID, "x", ROOT, "a", TransformStep(TransformKind.IDENTITY, {})),)
    assert column_confidence(LineageResult(edges=edges))[(MID, "x")] == Confidence.HIGH


def test_low_confidence_propagates_downstream():
    edges = (
        _edge(MID, "x", ROOT, "a", TransformStep(TransformKind.UNKNOWN, {})),  # uncertain here
        _edge(DOWN, "y", MID, "x", TransformStep(TransformKind.IDENTITY, {})),  # clean, but inherits
    )
    conf = column_confidence(LineageResult(edges=edges))
    assert conf[(MID, "x")] == Confidence.LOW
    assert conf[(DOWN, "y")] == Confidence.LOW  # uncertainty is inherited downstream


def test_warnings_and_unknown_schema_lower_confidence():
    warned = (_edge(MID, "x", ROOT, "a", TransformStep(TransformKind.IDENTITY, {}),
                    warnings=("unresolved_column",)),)
    assert column_confidence(LineageResult(edges=warned))[(MID, "x")] == Confidence.LOW
    noschema = (_edge(MID, "x", ROOT, "a", TransformStep(TransformKind.IDENTITY, {}),
                      provenance=SchemaProvenance.UNKNOWN),)
    assert column_confidence(LineageResult(edges=noschema))[(MID, "x")] == Confidence.LOW
