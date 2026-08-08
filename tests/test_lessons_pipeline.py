import json
from types import SimpleNamespace

from datagrid_agents.orchestrator.parallel import AgentCall
from datagrid_agents.orchestrator.workflows.lessons_multipass import build_pass_calls
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


def test_build_pass_calls_uses_orchestrator_role():
    calls = build_pass_calls("Utility buyout slipped", "Q: Why?\nA: As-builts wrong")
    assert len(calls) == ANALYSIS_PASSES
    assert all(isinstance(call, AgentCall) for call in calls)
    assert calls[0].role.startswith("lessons_extractor:")
    assert "Cost & contingency" in calls[0].prompt


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


def test_run_multipass_extraction_via_orchestrator():
    events: list[tuple[str, dict]] = []

    def converse(call: AgentCall):
        prompt = call.prompt
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
            text = json.dumps(
                {
                    "summary": "Aggregated summary.",
                    "actions": ["A1", "A2", "A3", "A4", "A5"],
                    "findings": findings,
                }
            )
        else:
            text = json.dumps(
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
            )
        # Passes cost 1.5 each; aggregate costs 2.5 — total 20*1.5+2.5=32.5
        credits = 2.5 if "aggregation analyst" in prompt else 1.5
        return SimpleNamespace(
            content=[SimpleNamespace(text=text)],
            conversation_id="c-test",
            credits=SimpleNamespace(consumed=credits),
        )

    result = run_multipass_extraction(
        prompt="Utility buyout slipped",
        interview="Q: Why?\nA: As-builts wrong",
        converse=converse,
        on_event=lambda event, data: events.append((event, data)),
        max_workers=8,
        cache=False,
        project="Harborview Phase 2",
        knowledge_name="Harborview",
    )

    assert result["pass_count"] == 20
    assert result["passes_completed"] == 20
    assert len(result["findings"]) == TARGET_FINDINGS
    assert result["orchestrator"]["workflow"] == "lessons_multipass"
    assert result["orchestrator"]["max_workers"] == 8
    assert result["project"] == "Harborview Phase 2"
    assert result["credits"]["consumed"] == 32.5
    assert result["credits"]["billed_calls"] == 21
    assert any(event == "pass" for event, _ in events)
    assert any(event == "link" for event, _ in events)
    assert any(event == "step" for event, _ in events)
    # Generative per-lens plan steps should appear before completions.
    lens_steps = [
        data for event, data in events
        if event == "step" and str(data.get("id", "")).startswith("lens-")
    ]
    assert len(lens_steps) >= 20
    assert any(
        event == "step" and "correlative" in (data.get("label") or "").lower()
        for event, data in events
    )


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
