from __future__ import annotations

from collections import defaultdict

from .models import MemorySignature


class FourLayerMemoryStore:
    def __init__(self) -> None:
        self.sensory: dict[str, MemorySignature] = {}
        self.working: dict[str, MemorySignature] = {}
        self.episodic: dict[str, MemorySignature] = {}
        self.semantic: dict[str, MemorySignature] = {}
        self.entity_index: dict[str, set[str]] = defaultdict(set)
        self.temporal_index: dict[str, set[str]] = defaultdict(set)
        self.causal_index: dict[str, set[str]] = defaultdict(set)
        self.importance_index: dict[str, float] = {}

    def insert(self, signature: MemorySignature) -> MemorySignature:
        self.delete(signature.id)
        self.sensory[signature.id] = signature
        if signature.confidence.score >= 0.75:
            self.working[signature.id] = signature
            self.episodic[signature.id] = signature
        if signature.confidence.score >= 0.85:
            self.semantic[signature.id] = signature
        for entity in signature.structured.entities:
            self.entity_index[entity.name.lower()].add(signature.id)
        month_key = signature.structured.temporal.timestamp.strftime("%Y-%m")
        self.temporal_index[month_key].add(signature.id)
        for link in signature.structured.causal_chain:
            self.causal_index[link.cause.lower()].add(signature.id)
            self.causal_index[link.effect.lower()].add(signature.id)
        self.importance_index[signature.id] = signature.importance.current_score
        return signature

    def all_signatures(self) -> list[MemorySignature]:
        merged = {**self.sensory, **self.working, **self.episodic, **self.semantic}
        return list(merged.values())

    def visible_signatures(self, workspace_id: str | None = None, user_id: str | None = None) -> list[MemorySignature]:
        return [
            signature
            for signature in self.all_signatures()
            if self._visible_to_scope(signature, workspace_id=workspace_id, user_id=user_id)
        ]

    def get(self, signature_id: str) -> MemorySignature | None:
        return self.semantic.get(signature_id) or self.episodic.get(signature_id) or self.working.get(signature_id) or self.sensory.get(signature_id)

    def delete(self, signature_id: str) -> MemorySignature | None:
        existing = self.get(signature_id)
        self.sensory.pop(signature_id, None)
        self.working.pop(signature_id, None)
        self.episodic.pop(signature_id, None)
        self.semantic.pop(signature_id, None)
        self.importance_index.pop(signature_id, None)
        if existing:
            self._remove_from_indexes(signature_id)
        return existing

    def update(self, signature: MemorySignature) -> MemorySignature:
        return self.insert(signature)

    def by_entity(self, entity: str) -> list[MemorySignature]:
        return [self.get(sid) for sid in self.entity_index.get(entity.lower(), set()) if self.get(sid)]

    def _remove_from_indexes(self, signature_id: str) -> None:
        for index in (self.entity_index, self.temporal_index, self.causal_index):
            for key in list(index.keys()):
                index[key].discard(signature_id)
                if not index[key]:
                    index.pop(key, None)

    def _visible_to_scope(self, signature: MemorySignature, workspace_id: str | None, user_id: str | None) -> bool:
        if signature.metadata.get("validity") in {"superseded", "deleted", "invalid"}:
            return False
        if signature.workspace_id and workspace_id and signature.workspace_id != workspace_id:
            return False
        if signature.workspace_id and not workspace_id:
            return False
        if not signature.workspace_id and signature.user_id and user_id and signature.user_id != user_id:
            return False
        if not signature.workspace_id and signature.user_id and not user_id:
            return False
        return True

    def stats(self) -> dict[str, int]:
        return {
            "sensory": len(self.sensory),
            "working": len(self.working),
            "episodic": len(self.episodic),
            "semantic": len(self.semantic),
            "entity_terms": len(self.entity_index),
            "causal_terms": len(self.causal_index),
        }
