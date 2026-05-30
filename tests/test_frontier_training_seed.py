from scripts.generate_frontier_training_seed import training_records


def test_frontier_training_seed_covers_major_capability_domains():
    records = training_records()
    domains = {record.domain_hint for record in records}

    assert "frontier_memory_chat" in domains
    assert "frontier_code_generation" in domains
    assert "frontier_media_generation" in domains
    assert "frontier_agentic_tasks" in domains
    assert all(record.source_trust >= 0.9 for record in records)


def test_frontier_training_seed_uses_structured_relation_language():
    records = training_records()
    relation_phrases = (" depends on ", " causes ", " requires ", " is ")

    assert all(any(phrase in record.content for phrase in relation_phrases) for record in records)
    assert all("jimstechinnovations@gmail.com" not in record.content.lower() for record in records)
