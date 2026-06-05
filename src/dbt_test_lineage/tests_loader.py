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
    """A guarantee a dbt test asserts on a specific (model, column). `asset` is the model's unique_id,
    matching the `ColumnRef.asset` the lineage engine emits — so guarantees align with edges directly."""

    asset: str  # attached_node: the model unique_id the test guards
    column: str  # normalized (lower-cased) column name
    kind: GuaranteeKind


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
    """Convenience: just the MVP (not_null / unique) guarantees."""
    return list(load_test_inventory(manifest_path).guarantees)
