"""Phase 3: unique propagation — per-model unique key-set tracking (architecture §4.2)."""

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

from dbt_test_lineage.propagate import propagate
from dbt_test_lineage.tests_loader import DeclaredGuarantee
from dbt_test_lineage.verdict import GuaranteeKind, Verdict

UQ = GuaranteeKind.UNIQUE
ROOT = "model.root"
M = "model.m"


def _s(kind, **d):
    return TransformStep(kind, d)


def _edge(down_col, up_col, *steps, up=ROOT, down=M):
    return LineageEdge(
        ColumnRef(down, down_col), ColumnRef(up, up_col), LineageType.DIRECT, tuple(steps)
    )


def _op(asset=M, grain=(), distinct=False, may_multiply=False):
    return ModelOperation(
        asset=asset, grain=tuple(grain), distinct=distinct, may_multiply_rows=may_multiply
    )


def _verdict(edges, guarantees, ops, col, asset=M):
    result = LineageResult(edges=tuple(edges), operations=tuple(ops))
    return propagate(result, guarantees, UQ)[(asset, col)].verdict


def test_group_by_grain_establishes_unique():
    e = _edge("id", "id", _s(TransformKind.IDENTITY))
    assert _verdict([e], [], [_op(grain=("id",))], "id") == Verdict.ESTABLISHED


def test_distinct_single_column_establishes():
    e = _edge("id", "id", _s(TransformKind.IDENTITY))
    assert _verdict([e], [], [_op(distinct=True)], "id") == Verdict.ESTABLISHED


def test_inherits_unique_through_injective_passthrough():
    e = _edge("id", "id", _s(TransformKind.IDENTITY))
    seeds = [DeclaredGuarantee(ROOT, "id", UQ)]
    assert _verdict([e], seeds, [_op()], "id") == Verdict.PROVEN


def test_fanout_breaks_inherited_unique():
    # unique upstream id, but the model joins (may multiply rows) -> admits duplicates
    e = _edge(
        "id", "id",
        _s(TransformKind.IDENTITY),
        _s(TransformKind.JOIN, join_type="LEFT", introduces_nulls=True),
    )
    seeds = [DeclaredGuarantee(ROOT, "id", UQ)]
    assert _verdict([e], seeds, [_op(may_multiply=True)], "id") == Verdict.NOT_GUARANTEED


def test_non_injective_transform_does_not_inherit():
    e = _edge("k", "id", _s(TransformKind.COALESCE, default="'x'", arg_index=0, arg_count=2))
    seeds = [DeclaredGuarantee(ROOT, "id", UQ)]
    assert _verdict([e], seeds, [_op()], "k") == Verdict.UNKNOWN


def test_composite_grain_does_not_prove_single_column():
    # GROUP BY (a, b): the TUPLE is unique, neither column alone
    ea = _edge("a", "a", _s(TransformKind.IDENTITY))
    eb = _edge("b", "b", _s(TransformKind.IDENTITY))
    assert _verdict([ea, eb], [], [_op(grain=("a", "b"))], "a") == Verdict.UNKNOWN


def test_untested_unmultiplied_passthrough_is_unknown():
    # no upstream unique evidence -> can't prove unique, but nothing breaks it either
    e = _edge("id", "id", _s(TransformKind.IDENTITY))
    assert _verdict([e], [], [_op()], "id") == Verdict.UNKNOWN


# --- end-to-end through the engine ---


def _write_manifest(tmp: Path) -> Path:
    def model(uid, name, sql, deps):
        return {
            "resource_type": "model", "unique_id": uid, "name": name, "database": "DB",
            "schema": "S", "alias": name.upper(), "original_file_path": f"{name}.sql",
            "depends_on": {"nodes": deps}, "compiled_code": sql,
        }

    manifest = {
        "nodes": {
            "model.p.agg": model(
                "model.p.agg", "agg",
                "select customer_id, count(*) as n from RAW.S.ORDERS group by 1",
                ["source.p.raw.orders"],
            ),
            "model.p.down": model(
                "model.p.down", "down", "select customer_id from DB.S.AGG", ["model.p.agg"]
            ),
        },
        "sources": {
            "source.p.raw.orders": {
                "resource_type": "source", "name": "orders", "database": "RAW",
                "schema": "S", "identifier": "ORDERS",
            }
        },
    }
    path = tmp / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def test_end_to_end_grain_and_inheritance(tmp_path):
    from dbt_column_lineage.engine import extract_lineage

    result = extract_lineage(_write_manifest(tmp_path), None, schema_mode="inferred")
    verdicts = propagate(result, [], UQ)
    # agg groups by customer_id -> that column is the grain -> ESTABLISHED unique
    assert verdicts[("model.p.agg", "customer_id")].verdict == Verdict.ESTABLISHED
    # down passes it through unchanged, no row multiplication -> inherits PROVEN
    assert verdicts[("model.p.down", "customer_id")].verdict == Verdict.PROVEN
