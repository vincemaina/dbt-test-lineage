"""Per-transform-step guarantee effects — the engine's `TransformStep` facts mapped to how they act on
a propagating guarantee (architecture §4.1 not_null). Each effect is one of `verdict.Effect`.

Lattice model: a step is a function on {HOLDS, NULLABLE, UNKNOWN}. `PRESERVE` is the identity; `BREAK`,
`ESTABLISH`, and `UNKNOWN` are constants. So folding a chain = "the last non-PRESERVE step wins"
(see propagate.py). Soundness: only `PRESERVE`/`ESTABLISH` can yield a proven not_null; anything we
cannot prove maps to `UNKNOWN`, never to a false `BREAK`.
"""

import re

from dbt_column_lineage.ir import TransformKind, TransformStep

from dbt_test_lineage.verdict import Effect

# Scalar functions that provably preserve not_null (return non-null iff their input is non-null).
# Conservative allowlist — anything not here is UNKNOWN, so we never over-claim. Extend as validated.
_NULL_PRESERVING_FUNCS = frozenset(
    {
        "UPPER", "LOWER", "INITCAP", "TRIM", "LTRIM", "RTRIM", "LENGTH", "LEN", "REVERSE",
        "REPLACE", "SUBSTR", "SUBSTRING", "LEFT", "RIGHT", "LPAD", "RPAD", "CONCAT", "CONCAT_WS",
        "ABS", "ROUND", "FLOOR", "CEIL", "CEILING", "SIGN", "TRUNC", "SQRT", "EXP", "LN",
        "TO_CHAR", "TO_VARCHAR", "DATE_TRUNC", "DATEADD", "DATEDIFF", "CONVERT_TIMEZONE",
        "HASH", "MD5", "SHA1", "SHA2",
    }
)

# Window functions whose result is provably non-null (ranking / counting over a non-empty partition).
_NONNULL_WINDOW_FUNCS = frozenset(
    {"ROW_NUMBER", "RANK", "DENSE_RANK", "NTILE", "COUNT", "PERCENT_RANK", "CUME_DIST"}
)

# Aggregates whose result is provably non-null over a (non-empty) group.
_NONNULL_AGG_FUNCS = frozenset({"COUNT", "COUNT_IF"})


def _is_nonnull_literal(token: str) -> bool:
    """True only when a COALESCE default argument is unambiguously a non-null constant. Conservative:
    parenthesised parts (nested functions) never match, so we never falsely 'establish'."""
    s = token.strip()
    if "(" in s or ")" in s:
        return False
    if re.fullmatch(r"'(?:[^']|'')*'", s):  # string literal
        return True
    if re.fullmatch(r"-?\d+(?:\.\d+)?", s):  # numeric literal
        return True
    return s.upper() in {"TRUE", "FALSE", "CURRENT_DATE", "CURRENT_TIMESTAMP", "SYSDATE"}


def _coalesce_has_nonnull_default(default_sql: str) -> bool:
    # `default` is the engine's render of the OTHER coalesce args, comma-joined. A non-null literal
    # among them makes the whole COALESCE non-null regardless of the threaded column.
    return any(_is_nonnull_literal(part) for part in default_sql.split(","))


def not_null_effect(step: TransformStep) -> Effect:
    """How one transform step affects a propagating not_null guarantee (architecture §4.1)."""
    k, d = step.kind, step.detail
    if k in (TransformKind.IDENTITY, TransformKind.RENAME):
        return Effect.PRESERVE
    if k == TransformKind.CAST:
        return Effect.BREAK if d.get("safe") else Effect.PRESERVE  # TRY_CAST -> NULL on failure
    if k == TransformKind.COALESCE:
        return (
            Effect.ESTABLISH
            if _coalesce_has_nonnull_default(str(d.get("default", "")))
            else Effect.PRESERVE  # OR-combined with sibling args at the multi-edge level (§4.3)
        )
    if k == TransformKind.CASE:
        return Effect.BREAK if d.get("else_null") else Effect.PRESERVE  # AND-combined across THENs
    if k == TransformKind.AGGREGATION:
        return Effect.ESTABLISH if d.get("func") in _NONNULL_AGG_FUNCS else Effect.UNKNOWN
    if k == TransformKind.WINDOW:
        return Effect.ESTABLISH if d.get("func") in _NONNULL_WINDOW_FUNCS else Effect.UNKNOWN
    if k == TransformKind.STRUCT_ACCESS:
        return Effect.BREAK  # missing variant key -> NULL
    if k == TransformKind.UNNEST:
        return Effect.UNKNOWN  # exploded element may be null
    if k == TransformKind.EXPRESSION:
        if d.get("introduces_nulls"):  # NULLIF
            return Effect.BREAK
        if "op" in d:  # arithmetic on non-null is non-null (Snowflake errors on /0, never nulls)
            return Effect.PRESERVE
        return Effect.PRESERVE if d.get("func") in _NULL_PRESERVING_FUNCS else Effect.UNKNOWN
    if k == TransformKind.JOIN:
        return Effect.BREAK if d.get("introduces_nulls") else Effect.PRESERVE
    if k == TransformKind.UNION:
        return Effect.PRESERVE  # branch combine handled at the multi-edge level (§4.3)
    return Effect.UNKNOWN  # TransformKind.UNKNOWN and any unmodelled kind


# --- unique (architecture §4.2) ---

# Steps that preserve per-column distinctness (distinct inputs -> distinct outputs). Conservative: only
# pure passthrough + structural steps (JOIN/UNION change rows, not the value). CAST is EXCLUDED — a
# narrowing/truncating cast (float->int, timestamp->date) can collapse distinct values, and we cannot
# tell which from the type alone, so we never claim uniqueness survives a cast (soundness for REDUNDANT).
_INJECTIVE_KINDS = frozenset(
    {TransformKind.IDENTITY, TransformKind.RENAME, TransformKind.JOIN, TransformKind.UNION}
)


def is_injective_chain(transforms: tuple[TransformStep, ...]) -> bool:
    """True if a column's value passes through unchanged-up-to-relabelling (uniqueness-preserving).
    A single such edge from a unique upstream column keeps that column unique — provided the model does
    not multiply rows (checked separately via `operations.may_multiply_rows`)."""
    return all(s.kind in _INJECTIVE_KINDS for s in transforms)
