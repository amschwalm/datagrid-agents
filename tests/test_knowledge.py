from server.knowledge import (
    UPLOAD_GUIDANCE,
    build_deep_search_confirm_prompt,
    no_match_payload,
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


def test_deep_search_prompt_mentions_file_match_and_upload():
    prompt = build_deep_search_confirm_prompt("Harborview", [{"id": "kn_1", "name": "Harborview"}])
    assert "User-requested project" in prompt
    assert "exact" in prompt and "fuzzy" in prompt
    assert "upload" in prompt.lower()


def test_parse_confirm_payload_fuzzy_and_accessible():
    parsed = parse_confirm_payload(
        {
            "matched": True,
            "match_kind": "fuzzy",
            "project_name": "Harborview Medical Center Phase 2",
            "confidence": "med",
            "rationale": "Close name in RFIs",
            "accessible_projects": [
                {"name": "Metro Utility Expansion", "notes": "seen in specs"}
            ],
            "upload_required": False,
        },
        catalog=[{"id": "kn_metro", "name": "Metro Utility Expansion", "status": "ready"}],
    )
    assert parsed["matched"] is True
    assert parsed["match_kind"] == "fuzzy"
    assert parsed["project_name"] == "Harborview Medical Center Phase 2"
    assert parsed["accessible_projects"][0]["knowledge_id"] == "kn_metro"


def test_parse_confirm_payload_none_sets_upload_guidance():
    parsed = parse_confirm_payload(
        {
            "matched": False,
            "match_kind": "none",
            "accessible_projects": [{"name": "Tower A"}],
        }
    )
    assert parsed["matched"] is False
    assert parsed["upload_required"] is True
    assert "Upload" in parsed["next_step"] or "upload" in parsed["next_step"].lower()


def test_no_match_payload_includes_upload_guidance():
    payload = no_match_payload("Missing Job", catalog=[{"id": "1", "name": "Tower A"}])
    assert payload["matched"] is False
    assert payload["upload_required"] is True
    assert payload["next_step"] == UPLOAD_GUIDANCE
    assert payload["accessible_projects"][0]["name"] == "Tower A"
