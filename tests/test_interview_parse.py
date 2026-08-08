from server.interview import parse_questions


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
