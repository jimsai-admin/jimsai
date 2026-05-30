from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from .models import MemorySignature


@dataclass
class Edge:
    target: str
    predicate: str
    weight: float
    source_signature: str
    last_used: float


class CausalGraphEngine:
    def __init__(self) -> None:
        self.edges: dict[str, list[Edge]] = defaultdict(list)

    def _add_edge(self, source: str, edge: Edge) -> None:
        source_key = source.lower()
        for existing in self.edges.get(source_key, []):
            if (
                existing.target == edge.target
                and existing.predicate == edge.predicate
                and existing.source_signature == edge.source_signature
            ):
                existing.weight = max(existing.weight, edge.weight)
                existing.last_used = max(existing.last_used, edge.last_used)
                return
        self.edges[source_key].append(edge)

    def add_signature(self, signature: MemorySignature) -> None:
        self.remove_signature(signature.id)
        now = time.time()
        for relation in signature.structured.relations:
            self._add_edge(
                relation.subject,
                Edge(relation.object.lower(), relation.predicate, relation.confidence, signature.id, now),
            )
        for link in signature.structured.causal_chain:
            self._add_edge(
                link.cause,
                Edge(link.effect.lower(), "causes", link.confidence, signature.id, now),
            )

    def remove_signature(self, signature_id: str) -> int:
        removed = 0
        for source, edges in list(self.edges.items()):
            live = [edge for edge in edges if edge.source_signature != signature_id]
            removed += len(edges) - len(live)
            if live:
                self.edges[source] = live
            else:
                self.edges.pop(source, None)
        return removed

    def traverse(self, start: str, depth: int = 3) -> dict[str, list[dict[str, str | float]]]:
        start_key = start.lower()
        visited = {start_key}
        queue: deque[tuple[str, int]] = deque([(start_key, 0)])
        paths: dict[str, list[dict[str, str | float]]] = defaultdict(list)
        while queue:
            node, level = queue.popleft()
            if level >= depth:
                continue
            for edge in self.edges.get(node, []):
                edge.last_used = time.time()
                paths[node].append(
                    {
                        "target": edge.target,
                        "predicate": edge.predicate,
                        "weight": round(edge.weight, 4),
                        "source": edge.source_signature,
                    }
                )
                if edge.target not in visited:
                    visited.add(edge.target)
                    queue.append((edge.target, level + 1))
        return dict(paths)

    def incoming(self, target: str) -> list[dict[str, str | float]]:
        target_key = target.lower()
        matches: list[dict[str, str | float]] = []
        for source, edges in self.edges.items():
            for edge in edges:
                if edge.target == target_key or edge.target.startswith(f"{target_key}."):
                    edge.last_used = time.time()
                    matches.append(
                        {
                            "source": source,
                            "target": edge.target,
                            "predicate": edge.predicate,
                            "weight": round(edge.weight, 4),
                            "source_signature": edge.source_signature,
                        }
                    )
        return matches

    def outgoing_edges(self, start: str, predicates: set[str] | None = None, depth: int = 4) -> list[dict[str, str | float | int]]:
        start_key = start.lower()
        seeds = [source for source in self.edges if source == start_key or source.startswith(f"{start_key}.")]
        if not seeds and start_key in self.edges:
            seeds = [start_key]
        queue: deque[tuple[str, int]] = deque((seed, 0) for seed in sorted(set(seeds)))
        visited = set(seeds)
        matches: list[dict[str, str | float | int]] = []
        while queue:
            source, level = queue.popleft()
            if level >= depth:
                continue
            for edge in self.edges.get(source, []):
                edge.last_used = time.time()
                if predicates is None or edge.predicate in predicates:
                    matches.append(
                        {
                            "source": source,
                            "target": edge.target,
                            "predicate": edge.predicate,
                            "weight": round(edge.weight, 4),
                            "source_signature": edge.source_signature,
                            "depth": level + 1,
                        }
                    )
                if edge.target not in visited:
                    visited.add(edge.target)
                    queue.append((edge.target, level + 1))
        return matches

    def incoming_edges(self, target: str, predicates: set[str] | None = None, depth: int = 4) -> list[dict[str, str | float | int]]:
        target_key = target.lower()
        seeds = {target_key}
        matches: list[dict[str, str | float | int]] = []
        for level in range(depth):
            next_seeds: set[str] = set()
            for source, edges in self.edges.items():
                for edge in edges:
                    if not any(edge.target == seed or edge.target.startswith(f"{seed}.") for seed in seeds):
                        continue
                    edge.last_used = time.time()
                    if predicates is None or edge.predicate in predicates:
                        matches.append(
                            {
                                "source": source,
                                "target": edge.target,
                                "predicate": edge.predicate,
                                "weight": round(edge.weight, 4),
                                "source_signature": edge.source_signature,
                                "depth": level + 1,
                            }
                        )
                    next_seeds.add(source)
            if not next_seeds or next_seeds <= seeds:
                break
            seeds = next_seeds
        return matches

    def reinforce(self, source: str, target: str, delta: float = 0.03) -> bool:
        for edge in self.edges.get(source.lower(), []):
            if edge.target == target.lower():
                edge.weight = min(1.0, edge.weight + delta)
                edge.last_used = time.time()
                return True
        return False

    def decay(self, decay_rate: float = 0.05, prune_threshold: float = 0.15) -> int:
        now = time.time()
        pruned = 0
        for node, edges in list(self.edges.items()):
            live: list[Edge] = []
            for edge in edges:
                days_stale = (now - edge.last_used) / 86400
                edge.weight = round(edge.weight - (decay_rate * days_stale), 4)
                if edge.weight >= prune_threshold:
                    live.append(edge)
                else:
                    pruned += 1
            if live:
                self.edges[node] = live
            else:
                self.edges.pop(node, None)
        return pruned
