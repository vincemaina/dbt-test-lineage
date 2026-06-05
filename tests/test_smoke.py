"""Phase 0 smoke test: the editable dbt-column-lineage dependency resolves, and we can drive the engine
end-to-end on its own jaffle fixture (the input contract this tool is built on)."""

from pathlib import Path

import pytest

from dbt_test_lineage import __version__


def test_package_imports():
    assert __version__ == "0.1.0"


def test_engine_dependency_importable():
    # the whole tool rests on consuming this IR — fail loudly if the path dependency is broken
    from dbt_column_lineage.engine import extract_lineage  # noqa: F401
    from dbt_column_lineage.ir import LineageResult  # noqa: F401


def _engine_fixture() -> Path:
    import dbt_column_lineage

    root = Path(dbt_column_lineage.__file__).parents[2]  # repo root of the editable install
    return root / "tests" / "fixtures" / "jaffle"


def test_extract_lineage_on_engine_fixture():
    fixture = _engine_fixture()
    if not (fixture / "manifest.json").exists():
        pytest.skip("engine jaffle fixture not present in this install")
    from dbt_column_lineage.engine import extract_lineage
    from dbt_column_lineage.ir import LineageResult

    result = extract_lineage(fixture / "manifest.json", fixture / "catalog.json")
    assert isinstance(result, LineageResult)
    assert result.edges  # the engine produced lineage we can later propagate guarantees over
