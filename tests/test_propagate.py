"""Phase 2: not_null propagation — the fold + multi-edge combination (§4.3), on synthetic edges for
precise control and end-to-end through the real engine for integration."""

import json
from pathlib import Path

from dbt_column_lineage.ir import (
    ColumnRef,
    LineageEdge,
    LineageResult,
    LineageType,
    TransformKind,
    TransformStep,
)

from dbt_test_lineage.propagate import propagate
from dbt_test_lineage.tests_loader import DeclaredGuarantee
from dbt_test_lineage.verdict import GuaranteeKind, Verdict

NN = GuaranteeKind.NOT_NULL
ROOT = "model.root"
M = "model.m"


def _step(kind, **d):
    return TransformStep(kind, d)


def _edge(down_col, up_col, *steps, up=ROOT, down=M):
    return LineageEdge(
        ColumnRef(down, down_col), ColumnRef(up, up_col), LineageType.DIRECT, tuple(steps)
    )


def _verdict(edges, guarantees, col="c"):
    result = LineageResult(edges=tuple(edges))
    return propagate(result, guarantees, NN)[(M, col)].verdict


def _seed(col="x", asset=ROOT):
    return [DeclaredGuarantee(asset, col, NN)]


def test_passthrough_preserves_proven():
    assert _verdict([_edge("c", "x", _step(TransformKind.IDENTITY))], _seed()) == Verdict.PROVEN


def test_try_cast_admits_null_not_guaranteed():
    # TRY_CAST admits a null on failure — not PROVEN, but not proof of failure either
    chain = _step(TransformKind.CAST, to_type="INT", safe=True)
    assert _verdict([_edge("c", "x", chain)], _seed()) == Verdict.NOT_GUARANTEED


def test_left_join_admits_null():
    chain = _step(TransformKind.JOIN, join_type="LEFT", introduces_nulls=True)
    assert _verdict([_edge("c", "x", chain)], _seed()) == Verdict.NOT_GUARANTEED


def test_untested_root_is_unknown():
    assert _verdict([_edge("c", "x", _step(TransformKind.IDENTITY))], []) == Verdict.UNKNOWN


def test_coalesce_literal_establishes_even_from_unknown():
    # nullable/untested input, but COALESCE(x, 'n/a') is always non-null
    chain = _step(TransformKind.COALESCE, default="'n/a'", arg_index=0, arg_count=2)
    assert _verdict([_edge("c", "x", chain)], []) == Verdict.ESTABLISHED


def test_count_establishes():
    assert _verdict([_edge("c", "x", _step(TransformKind.AGGREGATION, func="COUNT"))], []) == (
        Verdict.ESTABLISHED
    )


def test_unknown_function_downgrades_to_unknown():
    chain = _step(TransformKind.EXPRESSION, func="SOME_UDF")
    assert _verdict([_edge("c", "x", chain)], _seed()) == Verdict.UNKNOWN


def test_coalesce_or_combine_any_arg_holds():
    # COALESCE(x, y): x tested not_null, y untested -> OR -> holds
    def co():
        return _step(TransformKind.COALESCE, default="other", arg_index=0, arg_count=2)

    edges = [_edge("c", "x", co()), _edge("c", "y", co())]
    assert _verdict(edges, _seed("x")) == Verdict.PROVEN


def test_union_one_unknown_branch_is_unknown():
    # branch 0 tested not_null, branch 1 untested -> AND(PROVEN, UNKNOWN) -> UNKNOWN
    b0 = _edge("c", "x", _step(TransformKind.UNION, branch=0))
    b1 = _edge("c", "y", _step(TransformKind.UNION, branch=1))
    assert _verdict([b0, b1], _seed("x")) == Verdict.UNKNOWN


def test_union_one_admits_null_branch_not_guaranteed():
    # branch 1 goes through TRY_CAST (admits null) -> AND -> NOT_GUARANTEED dominates
    b0 = _edge("c", "x", _step(TransformKind.UNION, branch=0))
    b1 = _edge(
        "c", "y", _step(TransformKind.UNION, branch=1),
        _step(TransformKind.CAST, to_type="INT", safe=True),
    )
    seeds = [DeclaredGuarantee(ROOT, "x", NN), DeclaredGuarantee(ROOT, "y", NN)]
    assert _verdict([b0, b1], seeds) == Verdict.NOT_GUARANTEED


def test_union_all_branches_tested_proven():
    b0 = _edge("c", "x", _step(TransformKind.UNION, branch=0))
    b1 = _edge("c", "y", _step(TransformKind.UNION, branch=1))
    assert _verdict([b0, b1], [DeclaredGuarantee(ROOT, "x", NN), DeclaredGuarantee(ROOT, "y", NN)]) == (
        Verdict.PROVEN
    )


def test_multi_hop_chain_breaks_then_irrelevant_preserve():
    # not_null -> TRY_CAST (admits null) -> UPPER (preserve): last non-preserve wins -> NOT_GUARANTEED
    edges = [
        _edge(
            "c", "x",
            _step(TransformKind.CAST, to_type="VARCHAR", safe=True),
            _step(TransformKind.EXPRESSION, func="UPPER"),
        )
    ]
    assert _verdict(edges, _seed()) == Verdict.NOT_GUARANTEED


# --- end-to-end through the real engine ---


def _write_manifest(tmp: Path) -> Path:
    def model(uid, name, sql, deps):
        return {
            "resource_type": "model", "unique_id": uid, "name": name, "database": "DB",
            "schema": "S", "alias": name.upper(), "original_file_path": f"{name}.sql",
            "depends_on": {"nodes": deps}, "compiled_code": sql,
        }

    manifest = {
        "nodes": {
            "model.p.a": model("model.p.a", "a", "select id from RAW.S.SRC", ["source.p.raw.src"]),
            "model.p.keep": model("model.p.keep", "keep", "select id from DB.S.A", ["model.p.a"]),
            "model.p.risky": model(
                "model.p.risky", "risky", "select try_cast(id as int) as id from DB.S.A", ["model.p.a"]
            ),
            # not_null test on a.id -> seeds the guarantee
            "test.p.nn": {
                "resource_type": "test", "name": "nn_a_id",
                "database": "DB", "schema": "S", "test_metadata": {"name": "not_null"},
                "column_name": "id", "attached_node": "model.p.a",
                "depends_on": {"nodes": ["model.p.a"]},
            },
        },
        "sources": {
            "source.p.raw.src": {
                "resource_type": "source", "name": "src", "database": "RAW",
                "schema": "S", "identifier": "SRC",
            }
        },
    }
    path = tmp / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def test_end_to_end_through_engine(tmp_path):
    from dbt_column_lineage.engine import extract_lineage

    from dbt_test_lineage.tests_loader import load_declared_guarantees

    manifest = _write_manifest(tmp_path)
    result = extract_lineage(manifest, None, schema_mode="inferred")
    verdicts = propagate(result, load_declared_guarantees(manifest), NN)
    # keep.id is a pure passthrough of the tested a.id -> PROVEN
    assert verdicts[("model.p.keep", "id")].verdict == Verdict.PROVEN
    # risky.id is TRY_CAST(a.id) -> admits a null -> NOT_GUARANTEED (not proof of failure)
    assert verdicts[("model.p.risky", "id")].verdict == Verdict.NOT_GUARANTEED
