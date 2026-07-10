"""Traversal reasoning — compose graph paths into voiced inferences (no LLM).

The graph already stores learned relations as edges and can traverse them
(`CausalGraphEngine`). What was missing is turning a discovered PATH into an
answer: given "does A relate to C?" or "what does A lead to?", find the chain
A →…→ C and VOICE it as a transitive inference ("A causes B, B causes C, so A
causes C"), or honestly report NO connection when none exists.

Two honest properties:
  * grounded — every step of the voiced chain is a real edge that was learned
    from a source signature; nothing is invented between the endpoints;
  * fail-safe — when no path exists the reasoner says so (returns None); it
    never fabricates a link to satisfy the question. This is the reasoning
    analog of the gap-honesty guarantee.

Language stance: the chain is rendered as NOTATION — entity names and the
learned predicate labels joined by "→"/"⟹" (universal symbols). The predicates
are DATA (learned relations, in whatever language the knowledge was stored), not
hardcoded English chrome, so the inference carries no English of its own.
"""

from __future__ import annotations


def compose_path_inference(path: list[tuple[str, str, str]]) -> dict | None:
    """Turn a path [(from, predicate, to), …] into a voiced inference.

    Returns {"chain": str, "transitive": str | None, "hops": int} or None for
    an empty/absent path. When every edge shares one predicate the relation is
    transitive and a direct conclusion is emitted (A p B, B p C ⟹ A p C);
    otherwise the mixed chain is shown with each predicate on its arrow."""
    if not path:
        return None
    nodes = [path[0][0]] + [edge[2] for edge in path]
    predicates = [edge[1] for edge in path]
    uniform = len(set(predicates)) == 1
    if uniform:
        pred = predicates[0]
        chain = f" —{pred}→ ".join(nodes)
        transitive = f"{nodes[0]} —{pred}→ {nodes[-1]}" if len(nodes) > 2 else None
    else:
        parts = [nodes[0]]
        for _src, pred, dst in path:
            parts.append(f"—{pred}→ {dst}")
        chain = " ".join(parts)
        transitive = None
    return {"chain": chain, "transitive": transitive, "hops": len(path)}


def relate(graph, source: str, target: str, max_depth: int = 6) -> dict | None:
    """Reason about how `source` connects to `target`: find the shortest learned
    path and compose it, or None (honest no-connection). Symmetric fallback —
    if A→B is not found, try B→A so "how are A and C related?" works either
    way; the returned chain records the actual direction traversed."""
    path = graph.find_path(source, target, max_depth=max_depth)
    if path is None:
        path = graph.find_path(target, source, max_depth=max_depth)
    if path is None:
        return None
    inference = compose_path_inference(path)
    if inference is not None:
        inference["path"] = path
    return inference


def consequences(graph, source: str, max_depth: int = 4, limit: int = 6) -> list[dict]:
    """"What does `source` lead to?" — every node reachable from source, each as
    a composed chain from source. Grounded (real edges); bounded by depth."""
    out: list[dict] = []
    seen: set[str] = set()
    for endpoint_edges in (graph.outgoing_edges(source, depth=max_depth) or []):
        target = str(endpoint_edges.get("target") or "")
        if not target or target in seen or target.lower() == source.lower():
            continue
        seen.add(target)
        inference = relate(graph, source, target, max_depth=max_depth)
        if inference:
            out.append(inference)
        if len(out) >= limit:
            break
    return out
