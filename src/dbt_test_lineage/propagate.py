"""Propagate a guarantee over the engine's column lineage to a verdict per column (architecture §3).

Walk the column graph in model-topological order; for each downstream column fold every incoming DIRECT
edge's transform chain over its upstream column's verdict (rules.py), then combine the per-edge results
under the multi-edge semantics (§4.3: COALESCE = OR, UNION = AND across branches, otherwise AND).

The returned verdict for a column is COMPUTED from its inputs and transforms only — it deliberately does
NOT count the column's own declared test, so the reports (Phase 4) can compare "what dbt asserts here"
against "what the lineage proves." A column that IS tested still propagates downstream as PROVEN (dbt
enforces the test). `not_null` folds per-column (§4.1); `unique` tracks per-model unique key-sets (§4.2).
"""

from collections import defaultdict
from collections.abc import Callable, Iterable

from dbt_column_lineage.ir import LineageEdge, LineageResult, LineageType, TransformKind

from dbt_test_lineage.rules import is_injective_chain, not_null_effect
from dbt_test_lineage.tests_loader import DeclaredGuarantee
from dbt_test_lineage.verdict import (
    ColumnVerdict,
    Effect,
    GuaranteeKind,
    PropagationStep,
    Verdict,
)

_Key = tuple[str, str]  # (asset, column)


def _model_topo_order(edges: Iterable[LineageEdge]) -> list[str]:
    """Kahn topological sort of the model-level DAG implied by the edges (self-edges ignored). Any node
    left in a cycle is appended at the end so propagation still terminates."""
    deps: dict[str, set[str]] = defaultdict(set)
    models: set[str] = set()
    for e in edges:
        models.add(e.downstream.asset)
        models.add(e.upstream.asset)
        if e.upstream.asset != e.downstream.asset:
            deps[e.downstream.asset].add(e.upstream.asset)
    order: list[str] = []
    resolved: set[str] = set()
    ready = sorted(m for m in models if not deps[m])
    while ready:
        m = ready.pop()
        order.append(m)
        resolved.add(m)
        for n in sorted(models):
            if n not in resolved and n not in ready and deps[n] <= resolved:
                ready.append(n)
    order.extend(sorted(models - resolved))  # cycle fallback
    return order


def _to3(v: Verdict) -> str:
    if v.holds:
        return "holds"
    return "admits" if v in (Verdict.NOT_GUARANTEED, Verdict.VIOLATED) else "unknown"


def _from3(state: str, established: bool) -> Verdict:
    if state == "holds":
        return Verdict.ESTABLISHED if established else Verdict.PROVEN
    return Verdict.NOT_GUARANTEED if state == "admits" else Verdict.UNKNOWN


def _step_detail(step) -> str:
    extra = {k: step.detail[k] for k in step.detail if k in ("func", "op", "join_type", "to_type")}
    return f"{step.kind.value}{extra or ''}"


def _fold_not_null(
    input_verdict: Verdict, edge: LineageEdge
) -> tuple[Verdict, list[PropagationStep]]:
    """Fold one edge's chain. Effects are lattice functions; BREAK/ESTABLISH/UNKNOWN are constants, so
    the last non-PRESERVE step wins (we still record each one for the explanation)."""
    state = _to3(input_verdict)
    established = input_verdict == Verdict.ESTABLISHED
    steps: list[PropagationStep] = []
    col = f"{edge.upstream.asset}.{edge.upstream.column}"
    for st in edge.transforms:
        effect = not_null_effect(st)
        if effect == Effect.PRESERVE:
            continue
        if effect == Effect.ESTABLISH:
            state, established = "holds", True
        elif effect == Effect.BREAK:  # admits a null — not proven false, just not guaranteed
            state, established = "admits", False
        else:  # UNKNOWN
            state, established = "unknown", False
        steps.append(PropagationStep(col, effect, _step_detail(st)))
    return _from3(state, established), steps


_ADMITS = (Verdict.NOT_GUARANTEED, Verdict.VIOLATED)


def _and(verdicts: list[Verdict]) -> Verdict:
    """not_null holds only if ALL inputs hold (UNION branches, independent contributors, CASE THENs).
    If any input admits a null, so does the combination — that dominates UNKNOWN."""
    if not verdicts:
        return Verdict.UNKNOWN
    if any(v in _ADMITS for v in verdicts):
        return Verdict.NOT_GUARANTEED
    if any(v == Verdict.UNKNOWN for v in verdicts):
        return Verdict.UNKNOWN
    return Verdict.ESTABLISHED if all(v == Verdict.ESTABLISHED for v in verdicts) else Verdict.PROVEN


def _or(verdicts: list[Verdict]) -> Verdict:
    """not_null holds if ANY input holds (COALESCE arguments); else unknown if any unknown, else the
    combination admits a null only when every argument does."""
    if not verdicts:
        return Verdict.UNKNOWN
    if any(v == Verdict.ESTABLISHED for v in verdicts):
        return Verdict.ESTABLISHED
    if any(v == Verdict.PROVEN for v in verdicts):
        return Verdict.PROVEN
    if any(v == Verdict.UNKNOWN for v in verdicts):
        return Verdict.UNKNOWN
    return Verdict.NOT_GUARANTEED


def _has_kind(edge: LineageEdge, kind: TransformKind) -> bool:
    return any(s.kind == kind for s in edge.transforms)


def _union_branch(edge: LineageEdge) -> int | None:
    for s in edge.transforms:
        if s.kind == TransformKind.UNION:
            return int(s.detail.get("branch", 0))
    return None


def _combine_group(folded: list[tuple[LineageEdge, Verdict]]) -> Verdict:
    # within a non-union group: COALESCE args combine by OR, everything else by AND
    if any(_has_kind(e, TransformKind.COALESCE) for e, _ in folded):
        return _or([v for _, v in folded])
    return _and([v for _, v in folded])


def _combine_not_null(
    edges: list[LineageEdge], upstream: Callable[[str, str], Verdict]
) -> tuple[Verdict, list[PropagationStep]]:
    folded = [(e, *_fold_not_null(upstream(e.upstream.asset, e.upstream.column), e)) for e in edges]
    simple = [(e, v) for e, v, _ in folded]
    if any(_union_branch(e) is not None for e in edges):  # UNION: AND across branches
        by_branch: dict[int | None, list[tuple[LineageEdge, Verdict]]] = defaultdict(list)
        for e, v in simple:
            by_branch[_union_branch(e)].append((e, v))
        verdict = _and([_combine_group(items) for items in by_branch.values()])
    else:
        verdict = _combine_group(simple)
    # explanation: the steps of the edge that decided the verdict (a matching one, else the first)
    decisive = next((steps for _, v, steps in folded if v == verdict), folded[0][2])
    return verdict, decisive


def propagate(
    result: LineageResult,
    guarantees: Iterable[DeclaredGuarantee],
    kind: GuaranteeKind = GuaranteeKind.NOT_NULL,
) -> dict[_Key, ColumnVerdict]:
    """Compute the verdict for every column the lineage reaches, for one guarantee `kind`."""
    if kind == GuaranteeKind.NOT_NULL:
        return _propagate_not_null(result, guarantees)
    if kind == GuaranteeKind.UNIQUE:
        return _propagate_unique(result, guarantees)
    raise NotImplementedError(f"no propagation for {kind}")  # pragma: no cover


def _propagate_not_null(
    result: LineageResult, guarantees: Iterable[DeclaredGuarantee]
) -> dict[_Key, ColumnVerdict]:
    kind = GuaranteeKind.NOT_NULL
    direct = [e for e in result.edges if e.lineage_type == LineageType.DIRECT]
    asserted: set[_Key] = {(g.asset, g.column) for g in guarantees if g.kind == kind}

    by_down: dict[_Key, list[LineageEdge]] = defaultdict(list)
    for e in direct:
        by_down[(e.downstream.asset, e.downstream.column)].append(e)

    effective: dict[_Key, Verdict] = {}

    def upstream(asset: str, column: str) -> Verdict:
        key = (asset, column)
        if key in effective:
            return effective[key]
        return Verdict.PROVEN if key in asserted else Verdict.UNKNOWN  # roots: tested or unknown

    verdicts: dict[_Key, ColumnVerdict] = {}
    cols_by_model: dict[str, list[_Key]] = defaultdict(list)
    for key in by_down:
        cols_by_model[key[0]].append(key)

    for model in _model_topo_order(direct):
        for key in cols_by_model.get(model, []):
            verdict, path = _combine_not_null(by_down[key], upstream)
            seed = PropagationStep(f"{key[0]}.{key[1]}", Effect.SEED, kind.value)
            verdicts[key] = ColumnVerdict(key[0], key[1], kind, verdict, (seed, *path))
            # downstream usable value: a declared test enforces not_null here regardless of computed
            effective[key] = Verdict.PROVEN if key in asserted else verdict
    return verdicts


# --- unique (architecture §4.2): full grain-tuple / unique-KEY-set propagation ---


def _propagate_unique(
    result: LineageResult, guarantees: Iterable[DeclaredGuarantee]
) -> dict[_Key, ColumnVerdict]:
    """Track each model's unique KEYS (sets of output columns provably unique). Establish from the
    GROUP BY grain (`operations.grain`, output columns) and SELECT DISTINCT (all outputs); inherit a key
    through injective passthrough when the model does not multiply rows; break on row multiplication. A
    single-column `unique` test on C holds iff {C} is a unique key."""
    kind = GuaranteeKind.UNIQUE
    direct = [e for e in result.edges if e.lineage_type == LineageType.DIRECT]
    asserted: set[_Key] = {(g.asset, g.column) for g in guarantees if g.kind == kind}
    ops = {o.asset: o for o in result.operations}

    by_down: dict[_Key, list[LineageEdge]] = defaultdict(list)
    for e in direct:
        by_down[(e.downstream.asset, e.downstream.column)].append(e)
    out_cols: dict[str, set[str]] = defaultdict(set)
    for a, c in by_down:
        out_cols[a].add(c)
    # a column is an injective image of ONE upstream column iff it has a single, injective edge
    inj: dict[str, dict[str, _Key]] = defaultdict(dict)  # model -> {out_col: (up_asset, up_col)}
    for (a, c), edges in by_down.items():
        if len(edges) == 1 and is_injective_chain(edges[0].transforms):
            inj[a][c] = (edges[0].upstream.asset, edges[0].upstream.column)

    keys: dict[str, set[frozenset[str]]] = defaultdict(set)  # all unique keys (established + inherited)
    established: dict[str, set[frozenset[str]]] = defaultdict(set)  # keys CREATED here (grain/distinct)
    effective: dict[str, set[frozenset[str]]] = defaultdict(set)  # keys + asserted single-col tests

    def src_unique(src: _Key) -> bool:
        return frozenset({src[1]}) in effective.get(src[0], set())

    for model in _model_topo_order(direct):
        op = ops.get(model)
        mkeys: set[frozenset[str]] = set()
        if op and op.grain:
            k = frozenset(op.grain)
            mkeys.add(k)
            established[model].add(k)
        if op and op.distinct and out_cols[model]:
            k = frozenset(out_cols[model])
            mkeys.add(k)
            established[model].add(k)
        if not (op and op.may_multiply_rows):  # inherit keys through injective passthrough
            images: dict[str, dict[str, str]] = defaultdict(dict)  # up_model -> {up_col: out_col}
            for out_col, (ua, uc) in inj[model].items():
                images[ua].setdefault(uc, out_col)
            for ua, colmap in images.items():
                for up_key in effective.get(ua, set()):
                    if all(kc in colmap for kc in up_key):
                        mkeys.add(frozenset(colmap[kc] for kc in up_key))
        keys[model] = mkeys
        effective[model] = set(mkeys) | {frozenset({c}) for (a, c) in asserted if a == model}

    for a, c in asserted:  # ensure root (source/seed) tested-unique columns seed downstream
        effective[a].add(frozenset({c}))

    verdicts: dict[_Key, ColumnVerdict] = {}
    for (a, c), _edges in by_down.items():
        seed = PropagationStep(f"{a}.{c}", Effect.SEED, kind.value)
        op = ops.get(a)
        single = frozenset({c})
        if single in keys[a]:
            here = single in established[a]
            verdict = Verdict.ESTABLISHED if here else Verdict.PROVEN
            why = "GROUP BY / DISTINCT grain" if here else "unique upstream via injective passthrough"
            path = (seed, PropagationStep(f"{a}.{c}", Effect.ESTABLISH if here else Effect.PRESERVE, why))
        elif c in inj[a] and src_unique(inj[a][c]) and op and op.may_multiply_rows:
            src = inj[a][c]
            verdict = Verdict.NOT_GUARANTEED  # unique upstream, but the model may duplicate rows
            path = (seed, PropagationStep(f"{src[0]}.{src[1]}", Effect.BREAK, "row multiplication admits duplicates"))
        else:
            verdict = Verdict.UNKNOWN
            path = (seed,)
        verdicts[(a, c)] = ColumnVerdict(a, c, kind, verdict, path)
    return verdicts
