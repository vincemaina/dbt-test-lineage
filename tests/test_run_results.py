"""run_results.json correlation: map tests to their last-run status."""

import json

from dbt_test_lineage.tests_loader import load_run_results
from dbt_test_lineage.tests_loader import test_uid_index as build_test_uid_index
from dbt_test_lineage.verdict import GuaranteeKind


def test_load_run_results(tmp_path):
    rr = {"results": [
        {"unique_id": "test.p.a", "status": "pass"},
        {"unique_id": "test.p.b", "status": "fail"},
        {"no_uid": True},
    ]}
    path = tmp_path / "run_results.json"
    path.write_text(json.dumps(rr))
    assert load_run_results(path) == {"test.p.a": "pass", "test.p.b": "fail"}


def test_test_uid_index_maps_column_to_test_nodes(tmp_path):
    manifest = {"nodes": {
        "model.p.m": {"resource_type": "model", "name": "m"},
        "test.p.nn": {
            "resource_type": "test", "name": "nn", "unique_id": "test.p.nn",
            "test_metadata": {"name": "not_null"}, "column_name": "ID",
            "attached_node": "model.p.m", "depends_on": {"nodes": ["model.p.m"]},
        },
    }}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    idx = build_test_uid_index(path)
    assert idx[("model.p.m", "id", GuaranteeKind.NOT_NULL)] == ["test.p.nn"]
