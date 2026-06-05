"""Phase 4: the Typer CLI (`report` / `check`) end-to-end through the engine."""

import json
from pathlib import Path

from typer.testing import CliRunner

from dbt_test_lineage.cli import app

runner = CliRunner()


def _manifest(tmp: Path) -> Path:
    def model(uid, name, sql, deps):
        return {
            "resource_type": "model", "unique_id": uid, "name": name, "database": "DB",
            "schema": "S", "alias": name.upper(), "original_file_path": f"{name}.sql",
            "depends_on": {"nodes": deps}, "compiled_code": sql,
        }

    def nn(uid, col, attached):
        return {
            "resource_type": "test", "name": uid.split(".")[-1], "database": "DB", "schema": "S",
            "test_metadata": {"name": "not_null"}, "column_name": col, "attached_node": attached,
            "depends_on": {"nodes": [attached]},
        }

    manifest = {
        "nodes": {
            "model.p.a": model("model.p.a", "a", "select id from RAW.S.SRC", ["source.p.raw.src"]),
            "model.p.keep": model("model.p.keep", "keep", "select id from DB.S.A", ["model.p.a"]),
            "test.p.nn_a": nn("test.p.nn_a", "id", "model.p.a"),
            "test.p.nn_keep": nn("test.p.nn_keep", "id", "model.p.keep"),  # redundant
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


def test_report_text(tmp_path):
    result = runner.invoke(app, ["report", str(_manifest(tmp_path))])
    assert result.exit_code == 0
    assert "REDUNDANT" in result.stdout
    assert "model.p.keep.id" in result.stdout
    assert "summary:" in result.stdout


def test_report_json(tmp_path):
    result = runner.invoke(app, ["report", str(_manifest(tmp_path)), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["summary"]["REDUNDANT"] == 1
    assert payload["findings"]["REDUNDANT"][0]["asset"] == "model.p.keep"


def test_check_passes_without_contradictions(tmp_path):
    result = runner.invoke(app, ["check", str(_manifest(tmp_path))])
    assert result.exit_code == 0
    assert "PASSED" in result.stdout
