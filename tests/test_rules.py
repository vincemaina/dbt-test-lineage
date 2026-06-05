"""The per-transform not_null effect table (architecture §4.1) — the rule oracle."""

import pytest

from dbt_column_lineage.ir import TransformKind, TransformStep

from dbt_test_lineage.rules import not_null_effect
from dbt_test_lineage.verdict import Effect


def step(kind, **detail):
    return TransformStep(kind, detail)


@pytest.mark.parametrize(
    "s,expected",
    [
        (step(TransformKind.IDENTITY), Effect.PRESERVE),
        (step(TransformKind.RENAME, **{"from": "a", "to": "b"}), Effect.PRESERVE),
        (step(TransformKind.CAST, to_type="INT"), Effect.PRESERVE),
        (step(TransformKind.CAST, to_type="INT", safe=True), Effect.BREAK),  # TRY_CAST
        (step(TransformKind.CASE, else_null=True), Effect.BREAK),
        (step(TransformKind.CASE, else_null=False), Effect.PRESERVE),
        (step(TransformKind.COALESCE, default="'n/a'"), Effect.ESTABLISH),
        (step(TransformKind.COALESCE, default="0"), Effect.ESTABLISH),
        (step(TransformKind.COALESCE, default="other_col"), Effect.PRESERVE),
        (step(TransformKind.COALESCE, default="to_char(x, 'f')"), Effect.PRESERVE),  # nested, not a literal
        (step(TransformKind.AGGREGATION, func="COUNT"), Effect.ESTABLISH),
        (step(TransformKind.AGGREGATION, func="SUM"), Effect.UNKNOWN),
        (step(TransformKind.WINDOW, func="ROW_NUMBER", role="value"), Effect.ESTABLISH),
        (step(TransformKind.WINDOW, func="LAG", role="value"), Effect.UNKNOWN),
        (step(TransformKind.STRUCT_ACCESS, path="user.id"), Effect.BREAK),
        (step(TransformKind.UNNEST, output="VALUE"), Effect.UNKNOWN),
        (step(TransformKind.EXPRESSION, op="add"), Effect.PRESERVE),
        (step(TransformKind.EXPRESSION, func="UPPER"), Effect.PRESERVE),
        (step(TransformKind.EXPRESSION, func="SOME_UDF"), Effect.UNKNOWN),
        (step(TransformKind.EXPRESSION, func="NULLIF", introduces_nulls=True), Effect.BREAK),
        (step(TransformKind.JOIN, join_type="LEFT", introduces_nulls=True), Effect.BREAK),
        (step(TransformKind.JOIN, join_type="INNER", introduces_nulls=False), Effect.PRESERVE),
        (step(TransformKind.UNION, branch=0), Effect.PRESERVE),
        (step(TransformKind.UNKNOWN), Effect.UNKNOWN),
    ],
)
def test_not_null_effect(s, expected):
    assert not_null_effect(s) == expected
