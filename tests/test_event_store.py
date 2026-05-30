from prototype.jimsai.event_store import AuditEventStore, VerifiedResultCache


def test_audit_event_store_persists_events_and_projection(tmp_path):
    db_path = tmp_path / "events.sqlite3"
    store = AuditEventStore(str(db_path))

    event = store.append(
        "memory_signature_inserted",
        "sig_1",
        {"confidence": 0.91, "modality": "text"},
        user_id="user_1",
    )

    reopened = AuditEventStore(str(db_path))
    events = reopened.tail(limit=10)
    stats = reopened.stats()

    assert events[-1]["event_id"] == event["event_id"]
    assert events[-1]["payload"]["confidence"] == 0.91
    assert stats["audit_events_total"] == 1
    assert stats["cqrs_read_models"] == 1


def test_verified_result_cache_persists_and_clears(tmp_path):
    db_path = tmp_path / "events.sqlite3"
    cache = VerifiedResultCache(str(db_path))
    key = cache.key("query", {"workspace_id": "w1", "query": "same"})

    cache.set(key, {"response": "cached", "confidence": 0.8})
    reopened = VerifiedResultCache(str(db_path))

    assert reopened.get(key)["value"]["response"] == "cached"
    assert reopened.stats()["result_cache_entries"] == 1
    assert reopened.clear() == 1
    assert reopened.get(key) is None
