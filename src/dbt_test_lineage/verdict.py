"""The guarantee model: what we reason about (`GuaranteeKind`), the verdict lattice, and the explainable
`ColumnVerdict` IR. Facts come from the engine; verdicts are rendered here. See docs/architecture.md §3.

Soundness stance (load-bearing): a verdict is `PROVEN`/`ESTABLISHED` only when the recorded facts prove
the guarantee holds, `VIOLATED` only when they prove it cannot, else `UNKNOWN`. A false `VIOLATED` erodes
trust faster than a missed one — when unsure, emit `UNKNOWN`.
"""

from dataclasses import dataclass, field
from enum import Enum


class GuaranteeKind(str, Enum):
    """A dbt test guarantee we propagate. MVP = not_null + unique (architecture §2)."""

    NOT_NULL = "not_null"
    UNIQUE = "unique"


class Verdict(str, Enum):
    PROVEN = "PROVEN"  # the transforms prove the guarantee holds for every row (inherited)
    ESTABLISHED = "ESTABLISHED"  # proven, but created HERE regardless of inputs (COALESCE default, GROUP BY grain)
    NOT_GUARANTEED = "NOT_GUARANTEED"  # the structure ADMITS a violation (null-admitting / non-injective transform on the path) — advisory, NOT proof of failure
    VIOLATED = "VIOLATED"  # the transforms PROVE the guarantee cannot hold (rare: literal NULL, fan-out duplication) — CI-failing
    UNKNOWN = "UNKNOWN"  # not determinable from the facts (unknown function, no upstream info)

    @property
    def holds(self) -> bool:
        """True when the guarantee is provably satisfied (PROVEN or ESTABLISHED)."""
        return self in (Verdict.PROVEN, Verdict.ESTABLISHED)


class Effect(str, Enum):
    """How one transform step (or a seed/combine) acts on a guarantee as it propagates."""

    SEED = "seed"  # a declared test asserts the guarantee at this column
    PRESERVE = "preserve"  # output inherits the input's verdict
    BREAK = "break"  # destroys the guarantee (-> nullable / non-unique)
    ESTABLISH = "establish"  # creates the guarantee regardless of input
    UNKNOWN = "unknown"  # cannot prove the effect -> downgrades PROVEN to UNKNOWN (never to VIOLATED)
    COMBINE = "combine"  # multiple upstream edges merged (COALESCE=OR, UNION/CASE=AND)


@dataclass(frozen=True)
class PropagationStep:
    """One hop in a verdict's explanation: the upstream column, how the guarantee was affected, and a
    human-readable reason. The ordered tuple of these on a `ColumnVerdict` IS the audit trail."""

    column: str  # "asset.column" of the upstream contributor (or the column itself, for a seed)
    effect: Effect
    detail: str = ""  # e.g. "TRY_CAST -> nullable", "declared not_null test", "COALESCE default 'n/a'"


@dataclass(frozen=True)
class ColumnVerdict:
    """The propagated verdict for one (column, guarantee) pair, with the path that explains it."""

    asset: str  # dbt unique_id of the model
    column: str  # normalized (lower-cased) column name
    kind: GuaranteeKind
    verdict: Verdict
    path: tuple[PropagationStep, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return f"{self.asset}.{self.column} [{self.kind.value}] = {self.verdict.value}"


def verdict_to_dict(v: ColumnVerdict) -> dict:
    return {
        "asset": v.asset,
        "column": v.column,
        "kind": v.kind.value,
        "verdict": v.verdict.value,
        "path": [{"column": s.column, "effect": s.effect.value, "detail": s.detail} for s in v.path],
    }
