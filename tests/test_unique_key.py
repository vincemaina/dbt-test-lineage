"""Opt-in unique_key guarantees: treat config.unique_key as not_null+unique on the PK."""

import json
from pathlib import Path

from dbt_column_lineage.ir import (
    ColumnRef,
    LineageEdge,
    LineageResult,
    LineageType,
    ModelOperation,
    TransformKind,
    TransformStep,
)

from dbt_test_lineage.reports import ReportKind, analyze
from dbt_test_lineage.tests_loader import DeclaredGuarantee, unique_key_guarantees
from dbt_test_lineage.verdict import GuaranteeKind

NN, UQ = GuaranteeKind.NOT_NULL, GuaranteeKind.UNIQUE


def _manifest(tmp: Path, unique_key) -> Path:
    node = {
        "resource_type": "model", "unique_id": "model.p.m", "name": "m",
        "config": {"materialized": "incremental", "unique_key": unique_key},
    }
    path = tmp / "manifest.json"
    path.write_text(json.dumps({"nodes": {"model.p.m": node}}))
    return path


def test_single_column_unique_key_implies_not_null_and_unique(tmp_path):
    gs = unique_key_guarantees(_manifest(tmp_path, "id"))
    assert set(gs) == {
        DeclaredGuarantee("model.p.m", "id", NN, source="unique_key"),
        DeclaredGuarantee("model.p.m", "id", UQ, source="unique_key"),
    }


def test_composite_unique_key_implies_not_null_per_column_only(tmp_path):
    gs = unique_key_guarantees(_manifest(tmp_path, ["a", "b"]))
    # not_null on each; NO single-column unique (only the tuple is unique)
    assert set(gs) == {
        DeclaredGuarantee("model.p.m", "a", NN, source="unique_key"),
        DeclaredGuarantee("model.p.m", "b", NN, source="unique_key"),
    }


def test_expression_unique_key_is_ignored(tmp_path):
    assert unique_key_guarantees(_manifest(tmp_path, "coalesce(a, b)")) == []
    assert unique_key_guarantees(_manifest(tmp_path, None)) == []


def test_implied_guarantee_covers_pk_and_propagates_downstream():
    # model.pk has a single-column grain `id` with no test; model.down passes it through.
    edges = (
        LineageEdge(ColumnRef("model.pk", "id"), ColumnRef("model.src", "id"),
                    LineageType.DIRECT, (TransformStep(TransformKind.IDENTITY, {}),)),
        LineageEdge(ColumnRef("model.down", "id"), ColumnRef("model.pk", "id"),
                    LineageType.DIRECT, (TransformStep(TransformKind.IDENTITY, {}),)),
    )
    ops = (ModelOperation(asset="model.pk", grain=("id",)),)
    result = LineageResult(edges=edges, operations=ops)

    # without the implied guarantee: model.pk.id is an uncovered PK
    bare = analyze(result, [], kinds=(NN,))
    assert ("model.pk", "id") in {(f.asset, f.column) for f in bare.of(ReportKind.UNCOVERED)}

    # WITH unique_key implying not_null on model.pk.id: PK is covered, and an explicit test on the
    # downstream passthrough becomes REDUNDANT (inherited)
    implied = [DeclaredGuarantee("model.pk", "id", NN, source="unique_key")]
    explicit = [DeclaredGuarantee("model.down", "id", NN)]  # a real test node downstream
    rep = analyze(result, implied + explicit, kinds=(NN,))
    assert rep.of(ReportKind.UNCOVERED) == []  # PK now covered by the config implication
    assert [(f.asset, f.column) for f in rep.of(ReportKind.REDUNDANT)] == [("model.down", "id")]
