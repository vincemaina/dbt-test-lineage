"""Cache the engine's LineageResult so repeated analyses don't re-pay the (slow) extraction.

The lineage depends only on the manifest + catalog contents and the extraction params, so the cache key
is a hash of exactly those (plus the engine version). When they're unchanged the cached result is
returned instantly; when anything changes the key misses and we re-extract. Storage is a local pickle
the caller owns — only ever loaded from a path the user passed.
"""

import hashlib
import pickle
from pathlib import Path

import dbt_column_lineage
from dbt_column_lineage.engine import extract_lineage
from dbt_column_lineage.ir import LineageResult


def _cache_key(manifest: Path, catalog: Path | None, schema_mode: str, dialect: str) -> str:
    h = hashlib.sha256()
    h.update(getattr(dbt_column_lineage, "__version__", "?").encode())  # engine version
    h.update(f"{schema_mode}|{dialect}".encode())
    h.update(Path(manifest).read_bytes())
    if catalog is not None:
        h.update(Path(catalog).read_bytes())
    return h.hexdigest()


def extract_lineage_cached(
    manifest_path,
    catalog_path=None,
    *,
    schema_mode: str = "auto",
    dialect: str = "snowflake",
    cache: str | Path | None = None,
) -> tuple[LineageResult, bool]:
    """Return (result, from_cache). With `cache` set, reuse a valid cached result keyed on the manifest/
    catalog contents + params; otherwise extract and write the cache. A corrupt or stale cache is
    silently ignored and rebuilt."""
    if cache is None:
        return extract_lineage(manifest_path, catalog_path, schema_mode=schema_mode, dialect=dialect), False
    cache = Path(cache)
    key = _cache_key(manifest_path, catalog_path, schema_mode, dialect)
    if cache.exists():
        try:
            blob = pickle.loads(cache.read_bytes())
            if blob.get("key") == key and isinstance(blob.get("result"), LineageResult):
                return blob["result"], True
        except Exception:  # noqa: BLE001 - unreadable/incompatible cache -> rebuild
            pass
    result = extract_lineage(manifest_path, catalog_path, schema_mode=schema_mode, dialect=dialect)
    cache.write_bytes(pickle.dumps({"key": key, "result": result}))
    return result, False
