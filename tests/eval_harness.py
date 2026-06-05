"""Accuracy eval harness: hand-verified cases run end-to-end through the REAL engine
(extract_lineage) + analyze, so the whole pipeline — lineage extraction, propagation, finding generation
— is scored against known-correct expectations. The reproducible accuracy gate for the tool's verdicts.

Each case is a tiny dbt project (compiled SQL + tests). `expect` = findings that MUST appear (kind,
model, column); `forbid` = (kind, model, column) that must NOT. A case passes only if every expectation
holds. Mirrors dbt-column-lineage's eval_harness discipline.
"""

import json
from pathlib import Path

from dbt_column_lineage.engine import extract_lineage

from dbt_test_lineage.reports import ReportKind, analyze
from dbt_test_lineage.tests_loader import load_declared_guarantees


def _manifest(models, tests, sources):
    nodes = {}
    for name, sql, deps in models:
        uid = f"model.p.{name}"
        nodes[uid] = {
            "resource_type": "model", "unique_id": uid, "name": name, "database": "DB", "schema": "S",
            "alias": name.upper(), "original_file_path": f"{name}.sql",
            "depends_on": {"nodes": [d if "." in d else f"model.p.{d}" for d in deps]},
            "compiled_code": sql,
        }
    for i, (kind, mname, col) in enumerate(tests):
        uid = f"test.p.t{i}"
        nodes[uid] = {
            "resource_type": "test", "unique_id": uid, "name": f"t{i}", "database": "DB", "schema": "S",
            "test_metadata": {"name": kind}, "column_name": col, "attached_node": f"model.p.{mname}",
            "depends_on": {"nodes": [f"model.p.{mname}"]},
        }
    srcs = {
        f"source.p.{name}": {"resource_type": "source", "name": name, "database": db, "schema": sch,
                             "identifier": ident}
        for name, db, sch, ident in sources
    }
    return {"nodes": nodes, "sources": srcs}


def run_case(tmp: Path, case: dict):
    path = tmp / f"{case['name']}.json"
    path.write_text(json.dumps(_manifest(case["models"], case["tests"], case.get("sources", []))))
    result = extract_lineage(path, None, schema_mode="inferred")
    report = analyze(result, load_declared_guarantees(path))
    found = {(f.kind.value, f.asset.split(".")[-1], f.column) for f in report.findings}
    missing = [e for e in case.get("expect", []) if e not in found]
    leaked = [e for e in case.get("forbid", []) if e in found]
    return missing, leaked


# kind constants
R, RS = ReportKind.REDUNDANT.value, ReportKind.REDUNDANT_STRUCTURAL.value
M, U = ReportKind.MISSING.value, ReportKind.UNCOVERED.value

CASES: list[dict] = [
    {
        "name": "inherited_redundant",
        "sources": [("raw", "RAW", "S", "SRC")],
        "models": [
            ("a", "select id from RAW.S.SRC", ["source.p.raw"]),
            ("b", "select id from DB.S.A", ["a"]),  # pure passthrough of the tested a.id
        ],
        "tests": [("not_null", "a", "id"), ("not_null", "b", "id")],
        "expect": [(R, "b", "id")],  # b.id is redundant (inherited from a.id)
    },
    {
        "name": "structural_redundant_coalesce",
        "sources": [("raw", "RAW", "S", "SRC")],
        "models": [("a", "select coalesce(x, 'n/a') as v from RAW.S.SRC", ["source.p.raw"])],
        "tests": [("not_null", "a", "v")],
        "expect": [(RS, "a", "v")],  # COALESCE with a literal makes it structurally not_null
    },
    {
        "name": "structural_redundant_group_by_unique",
        "sources": [("raw", "RAW", "S", "SRC")],
        "models": [("a", "select cust_id, count(*) as n from RAW.S.SRC group by 1", ["source.p.raw"])],
        "tests": [("unique", "a", "cust_id")],
        "expect": [(RS, "a", "cust_id")],  # GROUP BY grain makes cust_id structurally unique
    },
    {
        "name": "missing_try_cast",
        "sources": [("raw", "RAW", "S", "SRC")],
        "models": [
            ("a", "select id from RAW.S.SRC", ["source.p.raw"]),
            ("b", "select try_cast(id as int) as id from DB.S.A", ["a"]),  # untested, drops not_null
        ],
        "tests": [("not_null", "a", "id")],
        "expect": [(M, "b", "id")],
        "forbid": [(R, "b", "id"), (RS, "b", "id")],
    },
    {
        "name": "missing_left_join",
        "sources": [("raw", "RAW", "S", "SRC"), ("main", "RAW", "S", "MAIN")],
        "models": [
            ("a", "select id, k from RAW.S.SRC", ["source.p.raw"]),
            # a is on the NULLABLE side of the left join, so a.id can be null for unmatched main rows
            ("b", "select a.id from RAW.S.MAIN m left join DB.S.A a on m.k = a.k",
             ["a", "source.p.main"]),
        ],
        "tests": [("not_null", "a", "id")],
        "expect": [(M, "b", "id")],  # tested a.id dropped by the outer join, untested downstream
    },
    {
        "name": "uncovered_pk",
        "sources": [("raw", "RAW", "S", "SRC")],
        "models": [("a", "select id, count(*) as n from RAW.S.SRC group by 1", ["source.p.raw"])],
        "tests": [],  # the PK `id` (single-column grain) is untested for not_null
        "expect": [(U, "a", "id")],
    },
    {
        "name": "load_bearing_not_flagged",
        "sources": [("raw", "RAW", "S", "SRC")],
        "models": [
            ("a", "select id from RAW.S.SRC", ["source.p.raw"]),
            ("b", "select try_cast(id as int) as id from DB.S.A", ["a"]),  # tested here -> load-bearing
        ],
        "tests": [("not_null", "a", "id"), ("not_null", "b", "id")],
        # b.id is NOT_GUARANTEED but tested -> relies_on_data, not a finding
        "forbid": [(R, "b", "id"), (RS, "b", "id"), (M, "b", "id")],
    },
]


def score(tmp: Path):
    rows = []
    for case in CASES:
        missing, leaked = run_case(tmp, case)
        rows.append((case["name"], not missing and not leaked, missing, leaked))
    passed = sum(1 for _, ok, _, _ in rows if ok)
    return passed, len(rows), rows
