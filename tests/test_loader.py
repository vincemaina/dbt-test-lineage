"""Phase 1: the test loader parses manifest test nodes into typed not_null/unique guarantees and tallies
the rest. Validated on a synthetic manifest and (sanity) the engine's real-repo clone."""

import json
from pathlib import Path

import pytest

from dbt_test_lineage.tests_loader import (
    DeclaredGuarantee,
    load_declared_guarantees,
    load_test_inventory,
)
from dbt_test_lineage.verdict import GuaranteeKind


def _test_node(name, column, attached, **extra):
    md = {"name": name, "kwargs": {"column_name": column}} if name else None
    return {
        "resource_type": "test",
        "test_metadata": md,
        "column_name": column,
        "attached_node": attached,
        "depends_on": {"nodes": [attached] if attached else []},
        **extra,
    }


def _write_manifest(tmp: Path) -> Path:
    manifest = {
        "nodes": {
            "model.p.orders": {"resource_type": "model", "name": "orders"},
            "test.p.nn_id": _test_node("not_null", "ORDER_ID", "model.p.orders"),
            "test.p.uq_id": _test_node("unique", "order_id", "model.p.orders"),
            "test.p.av_status": _test_node("accepted_values", "status", "model.p.orders"),
            "test.p.rel": _test_node("relationships", "customer_id", "model.p.orders"),
            # table-level test (no column_name) -> skipped
            "test.p.tablelevel": _test_node("unique", None, "model.p.orders"),
            # custom/package generic test (test_metadata.name absent) -> skipped as <custom>
            "test.p.custom": _test_node(None, "x", "model.p.orders"),
        }
    }
    path = tmp / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def test_extracts_not_null_and_unique_only(tmp_path):
    inv = load_test_inventory(_write_manifest(tmp_path))
    assert set(inv.guarantees) == {
        DeclaredGuarantee("model.p.orders", "order_id", GuaranteeKind.NOT_NULL),
        DeclaredGuarantee("model.p.orders", "order_id", GuaranteeKind.UNIQUE),
    }


def test_column_name_is_normalized_lowercase(tmp_path):
    # the not_null test used ORDER_ID (upper) — must match the engine's lower-cased ColumnRef columns
    gs = load_declared_guarantees(_write_manifest(tmp_path))
    assert all(g.column == "order_id" for g in gs)


def test_skipped_tests_are_tallied(tmp_path):
    inv = load_test_inventory(_write_manifest(tmp_path))
    # accepted_values, relationships, the table-level unique (no column), and the custom test
    assert inv.skipped_by_name == {
        "accepted_values": 1,
        "relationships": 1,
        "unique": 1,  # the column-less (table-level) unique test
        "<custom>": 1,
    }


def test_attached_node_falls_back_to_single_model_dep(tmp_path):
    node = _test_node("not_null", "k", None)
    node["attached_node"] = None
    node["depends_on"] = {"nodes": ["model.p.orders"]}
    manifest = {"nodes": {"model.p.orders": {"resource_type": "model"}, "test.p.t": node}}
    path = tmp_path / "m.json"
    path.write_text(json.dumps(manifest))
    gs = load_declared_guarantees(path)
    assert gs == [DeclaredGuarantee("model.p.orders", "k", GuaranteeKind.NOT_NULL)]


def _real_manifest() -> Path:
    import dbt_column_lineage

    root = Path(dbt_column_lineage.__file__).parents[2]
    return root / ".repos" / "lyst-dbt" / "black_friday" / "target" / "manifest.json"


def test_loads_real_repo_guarantees():
    manifest = _real_manifest()
    if not manifest.exists():
        pytest.skip("real-repo manifest not present")
    inv = load_test_inventory(manifest)
    nn = [g for g in inv.guarantees if g.kind == GuaranteeKind.NOT_NULL]
    uq = [g for g in inv.guarantees if g.kind == GuaranteeKind.UNIQUE]
    assert len(nn) > 100 and len(uq) > 0  # ~183 not_null + ~12 unique in this repo
    # tests attach to models, seeds, or sources — all valid seed points for propagation
    valid = ("model.", "seed.", "source.")
    assert all(g.asset.startswith(valid) and g.column == g.column.lower() for g in inv.guarantees)
