"""Compose a Datagrid orchestration DAG from natural language."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from datagrid_agents.orchestrator.dag import DagCall, DagPlan, DagStage, validate_plan
from datagrid_agents.orchestrator.parallel import AgentCall
from datagrid_agents.orchestrator.registry import load_role, load_roles
from datagrid_agents import service

DEFAULT_PLANNER_ROLE = "mentor"

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def compose_plan(
    goal: str,
    *,
    mode: str = "auto",
    planner_role: str = DEFAULT_PLANNER_ROLE,
    converse: Callable[[AgentCall], Any] | None = None,
) -> DagPlan:
    """
    Build a DAG plan from a natural-language goal.

    mode:
      - heuristic: local rules only
      - llm: Datagrid planner agent returns JSON
      - auto: heuristic first; if the goal looks multi-step/open-ended, try llm and
              fall back to heuristic on failure
    """
    if not goal or not str(goal).strip():
        raise ValueError("goal is required")
    normalized = mode.lower().strip()
    if normalized not in {"auto", "heuristic", "llm"}:
        raise ValueError("mode must be one of: auto, heuristic, llm")

    if normalized == "heuristic":
        plan = plan_heuristic(goal)
        validate_plan(plan)
        return plan

    if normalized == "llm":
        plan = plan_with_llm(goal, planner_role=planner_role, converse=converse)
        validate_plan(plan)
        return plan

    # auto
    heuristic = plan_heuristic(goal)
    if not _looks_open_ended(goal):
        validate_plan(heuristic)
        return heuristic
    try:
        plan = plan_with_llm(goal, planner_role=planner_role, converse=converse)
        validate_plan(plan)
        return plan
    except Exception:
        validate_plan(heuristic)
        return heuristic


def _looks_open_ended(goal: str) -> bool:
    text = goal.lower()
    markers = (
        " then ",
        " after ",
        " followed by",
        "multi-step",
        "first ",
        "second ",
        " and then ",
        "compose",
        "orchestrate",
        "depending on",
        "based on the",
    )
    if any(marker in text for marker in markers):
        return True
    # Longish goals with multiple concerns often need a custom DAG.
    return len(text.split()) >= 28


def plan_heuristic(goal: str) -> DagPlan:
    """Deterministic NL → DAG mapping using keyword intents."""
    text = goal.lower()
    rationale_bits: list[str] = []

    if _matches(text, ("buyout", "buy out", "utility package", "elec utility", "electrical utility")):
        rationale_bits.append("Matched utility/electrical buyout intent.")
        return DagPlan(
            goal=goal,
            planner="heuristic",
            rationale=" ".join(rationale_bits),
            stages=[
                DagStage(
                    id="buyout_risks",
                    name="Buyout specialty risks",
                    calls=[
                        DagCall("mentor", "Lessons-learned buyout risks"),
                        DagCall("schedule", "Schedule/lead-time risks"),
                        DagCall("change_order", "Commercial / COR exposure"),
                    ],
                )
            ],
        )

    if _matches(text, ("submittal", "shop drawing", "product data")):
        rationale_bits.append("Matched submittal disposition intent.")
        stages = [
            DagStage(
                id="submittal_review",
                name="Submittal review",
                calls=[
                    DagCall("submittal", "Disposition against specs"),
                    DagCall("drawings_specs", "Drawing/spec cross-check"),
                    DagCall("deep_search", "Project-document evidence"),
                ],
            )
        ]
        if _matches(text, ("risk", "lesson", "commercial", "change order")):
            rationale_bits.append("Added mentor synthesis stage.")
            stages.append(
                DagStage(
                    id="synthesize",
                    name="Lessons synthesis",
                    depends_on=["submittal_review"],
                    include_prior=True,
                    calls=[DagCall("mentor", "Synthesize risks/lessons from prior findings")],
                )
            )
        return DagPlan(
            goal=goal,
            planner="heuristic",
            rationale=" ".join(rationale_bits),
            stages=stages,
        )

    if _matches(text, ("rfi", "request for information")):
        rationale_bits.append("Matched RFI packet QA intent.")
        stages = [
            DagStage(
                id="rfi_qa",
                name="RFI packet QA",
                calls=[
                    DagCall("deep_search", "Completeness and project-doc references"),
                    DagCall("drawings_specs", "Drawing/spec reference check"),
                    DagCall("drawing_revision", "Revision/coordination conflicts"),
                ],
            )
        ]
        if _matches(text, ("risk", "lesson", "then", "after", "schedule", "synthes")):
            rationale_bits.append("Added synthesis follow-on stage.")
            follow_calls = [
                DagCall("mentor", "Field lessons and issue risks from the RFI findings")
            ]
            if _matches(text, ("schedule", "delay", "lead time", "critical path")):
                follow_calls.append(
                    DagCall("schedule", "Schedule implications from the RFI findings")
                )
            stages.append(
                DagStage(
                    id="synthesize",
                    name="Synthesis follow-up",
                    depends_on=["rfi_qa"],
                    include_prior=True,
                    calls=follow_calls,
                )
            )
        return DagPlan(
            goal=goal,
            planner="heuristic",
            rationale=" ".join(rationale_bits),
            stages=stages,
        )

    # Generic / multi-step: gather then synthesize when sequencing words exist.
    if _matches(text, (" then ", " after ", "followed by", "first ", "second ", "based on")):
        rationale_bits.append("Detected multi-step language; using gather → synthesize DAG.")
        return DagPlan(
            goal=goal,
            planner="heuristic",
            rationale=" ".join(rationale_bits),
            stages=[
                DagStage(
                    id="gather",
                    name="Evidence gather",
                    calls=[
                        DagCall("deep_search", "Gather project evidence relevant to the goal"),
                        DagCall("drawings_specs", "Pull drawing/spec details relevant to the goal"),
                    ],
                ),
                DagStage(
                    id="synthesize",
                    name="Specialty synthesis",
                    depends_on=["gather"],
                    include_prior=True,
                    calls=[
                        DagCall("mentor", "Synthesize lessons and critical risks from prior evidence"),
                        DagCall("schedule", "Call out schedule implications from prior evidence"),
                    ],
                ),
            ],
        )

    rationale_bits.append("Fallback parallel scout: deep_search + mentor.")
    return DagPlan(
        goal=goal,
        planner="heuristic",
        rationale=" ".join(rationale_bits),
        stages=[
            DagStage(
                id="scout",
                name="General scout",
                calls=[
                    DagCall("deep_search", "Find relevant project evidence"),
                    DagCall("mentor", "Lessons-learned framing and risks"),
                ],
            )
        ],
    )


def plan_with_llm(
    goal: str,
    *,
    planner_role: str = DEFAULT_PLANNER_ROLE,
    converse: Callable[[AgentCall], Any] | None = None,
) -> DagPlan:
    """Ask a Datagrid agent to propose a DAG plan as JSON."""
    role = load_role(planner_role)
    available = ", ".join(sorted(load_roles()))
    prompt = f"""
You are composing an orchestration DAG for Cursor + Datagrid agents.

Return ONLY valid JSON (no markdown prose) matching this schema:
{{
  "goal": string,
  "planner": "llm",
  "rationale": string,
  "stages": [
    {{
      "id": string,
      "name": string,
      "depends_on": [string],
      "include_prior": true,
      "calls": [
        {{"role": string, "focus": string, "repeats": 1}}
      ]
    }}
  ]
}}

Rules:
- Use only these role keys: {available}
- Prefer 1-3 stages and at most 4 calls per stage
- Use depends_on for sequencing; put independent work in the same stage for parallelism
- repeats may be >1 only when the same role should take distinct angles
- include_prior should be true for stages that need earlier outputs

User goal:
{goal.strip()}
""".strip()

    call = AgentCall(
        role=f"planner:{role.key}",
        agent_id=role.id,
        prompt=prompt,
        chat_mode="light_agent",
    )
    if converse is None:
        response = service.converse_with_agent(
            call.agent_id,
            call.prompt,
            chat_mode=call.chat_mode,
        )
        text = service.response_text(response)
    else:
        response = converse(call)
        text = service.response_text(response)

    data = _extract_json_object(text)
    data["goal"] = data.get("goal") or goal
    data["planner"] = "llm"
    return DagPlan.from_dict(data)


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("planner returned empty response")
    candidates = []
    fenced = _JSON_BLOCK_RE.search(cleaned)
    if fenced:
        candidates.append(fenced.group(1))
    # Whole text / first balanced object
    candidates.append(cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(cleaned[start : end + 1])

    errors: list[str] = []
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(str(exc))
            continue
        if isinstance(data, dict):
            return data
        errors.append("JSON root was not an object")
    raise ValueError("could not parse planner JSON: " + "; ".join(errors[:2]))


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)
