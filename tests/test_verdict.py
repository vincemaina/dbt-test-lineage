"""Phase 1: the verdict lattice + explainable ColumnVerdict IR."""

from dbt_test_lineage.verdict import (
    ColumnVerdict,
    Effect,
    GuaranteeKind,
    PropagationStep,
    Verdict,
    verdict_to_dict,
)


def test_holds_only_for_proven_and_established():
    assert Verdict.PROVEN.holds and Verdict.ESTABLISHED.holds
    assert not Verdict.VIOLATED.holds and not Verdict.UNKNOWN.holds
    assert not Verdict.NOT_GUARANTEED.holds


def test_column_verdict_str_and_serialize():
    v = ColumnVerdict(
        asset="model.p.orders",
        column="order_id",
        kind=GuaranteeKind.NOT_NULL,
        verdict=Verdict.ESTABLISHED,
        path=(
            PropagationStep("source.p.raw.orders.id", Effect.SEED, "declared not_null test"),
            PropagationStep("model.p.orders.order_id", Effect.ESTABLISH, "COALESCE default 'n/a'"),
        ),
    )
    assert str(v) == "model.p.orders.order_id [not_null] = ESTABLISHED"
    d = verdict_to_dict(v)
    assert d["verdict"] == "ESTABLISHED" and d["kind"] == "not_null"
    assert d["path"][1] == {
        "column": "model.p.orders.order_id",
        "effect": "establish",
        "detail": "COALESCE default 'n/a'",
    }
