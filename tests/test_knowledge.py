from server.knowledge import (
    parse_confirm_payload,
    rank_knowledge_matches,
    score_knowledge_match,
)


def test_score_exact_and_partial():
    assert score_knowledge_match("Harborview", "Harborview") == 1.0
    assert score_knowledge_match("Harborview Phase 2", "Harborview") >= 0.8
    assert score_knowledge_match("zzz", "Harborview") == 0.0


def test_rank_knowledge_matches_orders_best_first():
    items = [
        {"id": "1", "name": "Metro Utility Expansion"},
        {"id": "2", "name": "Harborview Phase 2"},
        {"id": "3", "name": "Unrelated Tower"},
    ]
    ranked = rank_knowledge_matches("Harborview Phase 2", items)
    assert ranked[0]["id"] == "2"
    assert ranked[0]["score"] >= 0.9


def test_parse_confirm_payload_falls_back_to_ranked():
    ranked = [{"id": "kn_1", "name": "Harborview", "score": 0.95}]
    parsed = parse_confirm_payload(
        {"matched": True, "confidence": "high", "rationale": "Exact"},
        ranked,
    )
    assert parsed["knowledge_id"] == "kn_1"
    assert parsed["knowledge_name"] == "Harborview"
