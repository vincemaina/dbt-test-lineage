"""run_results.json correlation: map tests to their last-run status."""

import json

from dbt_test_lineage.tests_loader import load_run_metadata, load_run_results
from dbt_test_lineage.tests_loader import test_uid_index as build_test_uid_index
from dbt_test_lineage.verdict import GuaranteeKind


def _write_rr(tmp, which):
    path = tmp / "run_results.json"
    path.write_text(json.dumps({
        "metadata": {"generated_at": "2026-06-05T00:00:00Z", "dbt_version": "1.11.4"},
        "args": {"which": which, "invocation_command": f"dbt {which}", "target": "prod"},
        "elapsed_time": 12.0, "results": [],
    }))
    return path


def test_metadata_flags_non_test_command(tmp_path):
    # `dbt docs generate` / `compile` do not execute tests -> executed_tests False
    assert load_run_metadata(_write_rr(tmp_path, "generate"))["executed_tests"] is False
    assert load_run_metadata(_write_rr(tmp_path, "compile"))["executed_tests"] is False


def test_metadata_recognizes_test_executing_commands(tmp_path):
    for which in ("build", "test"):
        meta = load_run_metadata(_write_rr(tmp_path, which))
        assert meta["executed_tests"] is True
        assert meta["target"] == "prod" and meta["command"] == f"dbt {which}"


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
