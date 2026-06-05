"""Load declared dbt test guarantees from a compiled `manifest.json`.

dbt generic tests appear as nodes with `resource_type: "test"`, carrying `test_metadata.name`
(`not_null` / `unique` / ...), `column_name`, and `attached_node` (the tested model's unique_id). We
read the manifest directly for these — the engine doesn't surface tests — and keep only the MVP kinds
(`not_null`, `unique`), counting the rest for a coverage denominator. See docs/architecture.md §2/§5.
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from dbt_test_lineage.verdict import GuaranteeKind

# test_metadata.name -> the guarantee we propagate. Only single-column not_null/unique in the MVP.
_KIND_BY_TEST_NAME = {
    "not_null": GuaranteeKind.NOT_NULL,
    "unique": GuaranteeKind.UNIQUE,
}


@dataclass(frozen=True)
class DeclaredGuarantee:
    """A guarantee asserted on a specific (model, column). `asset` is the model's unique_id, matching the
    `ColumnRef.asset` the lineage engine emits — so guarantees align with edges directly. `source`
    distinguishes an explicit dbt test (`"test"`, the only kind that's a removable test node) from a
    config-implied guarantee (e.g. `"unique_key"`)."""

    asset: str  # attached_node: the model unique_id the test guards
    column: str  # normalized (lower-cased) column name
    kind: GuaranteeKind
    source: str = "test"


@dataclass(frozen=True)
class TestInventory:
    """Everything the loader found: the MVP guarantees plus a tally of skipped tests (table-level,
    custom/package generic tests, accepted_values/relationships) for coverage reporting later."""

    guarantees: tuple[DeclaredGuarantee, ...]
    skipped_by_name: dict[str, int]  # test_metadata.name (or "<custom>") -> count of skipped tests


def _attached_model(node: dict) -> str | None:
    attached = node.get("attached_node")
    if attached:
        return attached
    # older manifests omit attached_node — fall back to the single model dependency
    models = [d for d in node.get("depends_on", {}).get("nodes", []) if d.startswith("model.")]
    return models[0] if len(models) == 1 else None


def load_test_inventory(manifest_path: str | Path) -> TestInventory:
    manifest = json.loads(Path(manifest_path).read_text())
    guarantees: list[DeclaredGuarantee] = []
    skipped: Counter[str] = Counter()
    for node in manifest.get("nodes", {}).values():
        if node.get("resource_type") != "test":
            continue
        name = (node.get("test_metadata") or {}).get("name")
        kind = _KIND_BY_TEST_NAME.get(name) if name else None
        column = node.get("column_name")
        asset = _attached_model(node)
        if kind is None or not column or asset is None:
            skipped[name or "<custom>"] += 1
            continue
        guarantees.append(DeclaredGuarantee(asset, column.lower(), kind))
    return TestInventory(tuple(guarantees), dict(skipped))


def load_declared_guarantees(manifest_path: str | Path) -> list[DeclaredGuarantee]:
    """Convenience: just the MVP (not_null / unique) guarantees from explicit tests."""
    return list(load_test_inventory(manifest_path).guarantees)


def test_uid_index(manifest_path: str | Path) -> dict[tuple[str, str, GuaranteeKind], list[str]]:
    """`(attached_model, column, kind) -> [test node unique_id]` for not_null/unique tests — lets a
    finding be tied back to the actual dbt test node(s) (e.g. to look up run history)."""
    manifest = json.loads(Path(manifest_path).read_text())
    out: dict[tuple[str, str, GuaranteeKind], list[str]] = {}
    for uid, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") != "test":
            continue
        name = (node.get("test_metadata") or {}).get("name")
        kind = _KIND_BY_TEST_NAME.get(name) if name else None
        column = node.get("column_name")
        asset = _attached_model(node)
        if kind is None or not column or asset is None:
            continue
        out.setdefault((asset, column.lower(), kind), []).append(node.get("unique_id", uid))
    return out


def load_run_results(path: str | Path) -> dict[str, str]:
    """`node_unique_id -> status` (pass / success / fail / error / skipped) from a `run_results.json`."""
    data = json.loads(Path(path).read_text())
    return {
        r["unique_id"]: str(r.get("status", "")).lower()
        for r in data.get("results", [])
        if "unique_id" in r
    }


def load_run_metadata(path: str | Path) -> dict:
    """Provenance of a `run_results.json` so a cost/timing reading is never context-free: which dbt
    command produced it, target, when, and total elapsed. `executed_tests` is True only for commands that
    actually RUN tests (`build` / `test`) — otherwise any per-test `execution_time` is compile/catalog
    time, not real test runtime, and must not be priced as such."""
    d = json.loads(Path(path).read_text())
    meta, args = d.get("metadata", {}), d.get("args", {})
    command = args.get("invocation_command") or args.get("which") or ""
    which = str(args.get("which") or "").lower()
    return {
        "command": command,
        "target": args.get("target"),
        "generated_at": meta.get("generated_at"),
        "dbt_version": meta.get("dbt_version"),
        "elapsed_time": d.get("elapsed_time"),
        "executed_tests": which in ("build", "test"),
    }


def load_run_timing(path: str | Path) -> dict[str, float]:
    """`node_unique_id -> execution_time` (wall-clock seconds) from a `run_results.json` — used to price
    what removable (redundant) tests cost per run."""
    data = json.loads(Path(path).read_text())
    return {
        r["unique_id"]: float(r.get("execution_time") or 0.0)
        for r in data.get("results", [])
        if "unique_id" in r
    }


def _key_columns(unique_key: object) -> list[str] | None:
    """Plain column name(s) from a `unique_key` config (str or list of str). Returns None for an
    expression / SQL key (e.g. `coalesce(a,b)`, `a || b`) we can't map to columns."""
    if isinstance(unique_key, str):
        raw = [unique_key]
    elif isinstance(unique_key, list):
        raw = [c for c in unique_key if isinstance(c, str)]
    else:
        return None
    cols: list[str] = []
    for c in raw:
        c = c.strip()
        if not c or any(ch in c for ch in " ()|,'\"."):  # not a bare identifier -> an expression
            return None
        cols.append(c.lower())
    return cols or None


def unique_key_guarantees(
    manifest_path: str | Path,
    kinds: tuple[GuaranteeKind, ...] = (GuaranteeKind.NOT_NULL, GuaranteeKind.UNIQUE),
) -> list[DeclaredGuarantee]:
    """OPT-IN guarantees implied by each model's `config.unique_key` — for projects that enforce the key
    (e.g. a `unique_key` override that auto-generates not_null/unique tests on the PK). Vanilla dbt does
    NOT enforce `unique_key`, so this is off by default. A single-column key implies `unique` + `not_null`
    on it; a COMPOSITE key implies `not_null` on each component only (the tuple is unique, not the parts —
    a single-column `unique` would be unsound). `source="unique_key"`."""
    manifest = json.loads(Path(manifest_path).read_text())
    out: list[DeclaredGuarantee] = []
    for uid, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") != "model":
            continue
        cols = _key_columns((node.get("config") or {}).get("unique_key"))
        if not cols:
            continue
        asset = node.get("unique_id", uid)
        composite = len(cols) > 1
        for col in cols:
            if GuaranteeKind.NOT_NULL in kinds:
                out.append(DeclaredGuarantee(asset, col, GuaranteeKind.NOT_NULL, source="unique_key"))
            if GuaranteeKind.UNIQUE in kinds and not composite:
                out.append(DeclaredGuarantee(asset, col, GuaranteeKind.UNIQUE, source="unique_key"))
    return out
