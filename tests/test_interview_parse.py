from server.interview import DEFAULT_FOLLOWUPS, parse_questions, parse_reasoning_steps


def test_parse_questions_from_object():
    text = '{"questions":["One?","Two?"]}'
    assert parse_questions(text) == ["One?", "Two?"]


def test_parse_questions_from_fenced_markdown():
    text = """Here you go:
```json
{"questions": ["A?", "B?", "C?"]}
```
"""
    assert parse_questions(text) == ["A?", "B?", "C?"]


def test_parse_questions_from_array():
    assert parse_questions('["Alpha?", "Beta?"]') == ["Alpha?", "Beta?"]


def test_parse_questions_empty_on_garbage():
    assert parse_questions("No JSON here") == []


def test_default_followups_are_scope_oriented():
    joined = " ".join(DEFAULT_FOLLOWUPS).lower()
    assert "artifact" in joined or "phase" in joined
    assert "verify" in joined or "confirm" in joined


def test_parse_reasoning_steps():
    text = """
    {"reasoning_steps":[{"id":"a","label":"Scanning","status":"done","detail":"ok"}]}
    """
    steps = parse_reasoning_steps(text)
    assert steps[0]["label"] == "Scanning"
