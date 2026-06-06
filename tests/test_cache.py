"""Caching the engine's LineageResult: reuse while inputs are unchanged, rebuild when they change."""

import json
from pathlib import Path

from dbt_test_lineage.cache import extract_lineage_cached


def _manifest(tmp: Path, col: str) -> Path:
    manifest = {
        "nodes": {
            "model.p.a": {
                "resource_type": "model", "unique_id": "model.p.a", "name": "a", "database": "DB",
                "schema": "S", "alias": "A", "original_file_path": "a.sql",
                "depends_on": {"nodes": ["source.p.raw"]},
                "compiled_code": f"select {col} from RAW.S.SRC",
            }
        },
        "sources": {
            "source.p.raw": {"resource_type": "source", "name": "raw", "database": "RAW",
                             "schema": "S", "identifier": "SRC"},
        },
    }
    path = tmp / "manifest.json"
    path.write_text(json.dumps(manifest))
    return path


def test_first_call_extracts_then_hits_cache(tmp_path):
    manifest = _manifest(tmp_path, "id")
    cache = tmp_path / "lineage.pkl"
    r1, hit1 = extract_lineage_cached(manifest, None, schema_mode="inferred", cache=cache)
    assert hit1 is False and cache.exists()
    r2, hit2 = extract_lineage_cached(manifest, None, schema_mode="inferred", cache=cache)
    assert hit2 is True  # reused without re-extracting
    assert len(r1.edges) == len(r2.edges)


def test_changed_manifest_invalidates_cache(tmp_path):
    manifest = _manifest(tmp_path, "id")
    cache = tmp_path / "lineage.pkl"
    extract_lineage_cached(manifest, None, schema_mode="inferred", cache=cache)
    _manifest(tmp_path, "other_col")  # rewrite the same path with different content
    _, hit = extract_lineage_cached(manifest, None, schema_mode="inferred", cache=cache)
    assert hit is False  # key changed -> re-extracted


def test_no_cache_path_always_extracts(tmp_path):
    manifest = _manifest(tmp_path, "id")
    _, hit = extract_lineage_cached(manifest, None, schema_mode="inferred", cache=None)
    assert hit is False
