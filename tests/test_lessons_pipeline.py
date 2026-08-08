import json

from server.lessons_pipeline import (
    ANALYSIS_LENSES,
    ANALYSIS_PASSES,
    TARGET_FINDINGS,
    ensure_fifty,
    local_aggregate,
    parse_aggregate_result,
    parse_pass_result,
    run_multipass_extraction,
)


def test_twenty_lenses_configured():
    assert len(ANALYSIS_LENSES) == ANALYSIS_PASSES == 20


def test_parse_pass_result_json():
    text = """
```json
{
  "lens": "cost",
  "summary": "Buyout missed utility risk.",
  "findings": [
    {
      "finding": "Late utility commitment",
      "category": "Procurement",
      "evidence": "Shutdown window never locked",
      "recommendation": "Require utility LOI before buyout",
      "priority": "high",
      "artifacts": ["Buyout", "Schedule"]
    }
  ]
}
```
"""
    parsed = parse_pass_result(text, ANALYSIS_LENSES[0])
    assert parsed["parse_ok"] is True
    assert parsed["findings"][0]["finding"] == "Late utility commitment"


def test_local_aggregate_always_fifty():
    passes = [
        {
            "lens": "cost",
            "title": "Cost",
            "summary": "Cost pressure from extras.",
            "findings": [
                {
                    "finding": f"Finding {i}",
                    "category": "Cost",
                    "evidence": "evidence",
                    "recommendation": "fix it",
                    "priority": "high",
                    "sources": ["cost"],
                }
                for i in range(3)
            ],
        }
        for _ in range(5)
    ]
    result = local_aggregate(passes)
    assert len(result["findings"]) == TARGET_FINDINGS
    assert result["findings"][0]["rank"] == 1
    assert result["findings"][-1]["rank"] == TARGET_FINDINGS


def test_ensure_fifty_pads_short_aggregate():
    result = ensure_fifty(
        {
            "summary": "Short set",
            "actions": ["Do A"],
            "findings": [
                {
                    "finding": "Only one",
                    "category": "General",
                    "evidence": "x",
                    "recommendation": "y",
                    "priority": "med",
                    "sources": ["cost"],
                }
            ],
        },
        [
            {
                "lens": "schedule",
                "title": "Schedule",
                "summary": "Float burned on shutdowns.",
                "findings": [],
            }
        ],
    )
    assert len(result["findings"]) == TARGET_FINDINGS


def test_run_multipass_extraction_with_stub_converse():
    events: list[tuple[str, dict]] = []

    def converse(prompt: str):
        if "aggregation analyst" in prompt:
            findings = [
                {
                    "rank": i,
                    "finding": f"Agg {i}",
                    "category": "General",
                    "evidence": "cross-pass",
                    "recommendation": "institutionalize",
                    "priority": "high" if i < 10 else "med",
                    "sources": ["cost", "schedule"],
                }
                for i in range(1, TARGET_FINDINGS + 1)
            ]
            return {
                "agent_id": "agg",
                "agent_name": "Lessons",
                "conversation_id": "c-agg",
                "text": json.dumps(
                    {
                        "summary": "Aggregated summary.",
                        "actions": ["A1", "A2", "A3", "A4", "A5"],
                        "findings": findings,
                    }
                ),
            }
        return {
            "agent_id": "pass",
            "agent_name": "Lessons",
            "conversation_id": "c-pass",
            "text": json.dumps(
                {
                    "lens": "x",
                    "summary": "Pass summary.",
                    "findings": [
                        {
                            "finding": "Sample",
                            "category": "General",
                            "evidence": "e",
                            "recommendation": "r",
                            "priority": "med",
                            "artifacts": ["RFIs", "Meetings"],
                        }
                    ],
                }
            ),
        }

    result = run_multipass_extraction(
        prompt="Utility buyout slipped",
        interview="Q: Why?\nA: As-builts wrong",
        converse=converse,
        on_event=lambda event, data: events.append((event, data)),
        max_workers=4,
    )

    assert result["pass_count"] == 20
    assert result["passes_completed"] == 20
    assert len(result["findings"]) == TARGET_FINDINGS
    assert any(event == "pass" for event, _ in events)
    assert any(event == "link" for event, _ in events)
    assert any(event == "step" for event, _ in events)


def test_parse_aggregate_falls_back_without_json():
    result = parse_aggregate_result(
        "no json here",
        [
            {
                "lens": "cost",
                "title": "Cost",
                "summary": "Money burned on extras.",
                "findings": [
                    {
                        "finding": "Extras uncontrolled",
                        "category": "Cost",
                        "evidence": "No log",
                        "recommendation": "Daily extras log",
                        "priority": "high",
                        "sources": ["cost"],
                    }
                ],
            }
        ],
    )
    assert len(result["findings"]) == TARGET_FINDINGS
    assert result["aggregated_locally"] is True
