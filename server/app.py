"""Construction Lessons Learned web API — extractor + mentor over Datagrid."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

load_dotenv(ROOT / ".env", override=False)
# Cloud / local secret name variants
if not os.environ.get("DATAGRID_API_KEY") and os.environ.get("Datagrid_API_KEY"):
    os.environ["DATAGRID_API_KEY"] = os.environ["Datagrid_API_KEY"]

from datagrid_agents import service  # noqa: E402
from datagrid_agents.orchestrator.registry import load_role  # noqa: E402

app = FastAPI(title="Construction Lessons Learned", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SurveyAnswer(BaseModel):
    id: str
    question: str
    answer: str


class LessonsRequest(BaseModel):
    profile: dict[str, str] = Field(default_factory=dict)
    answers: list[SurveyAnswer] = Field(default_factory=list)


class MentorStartRequest(BaseModel):
    profile: dict[str, str] = Field(default_factory=dict)
    prompt: str
    followups: list[SurveyAnswer] = Field(default_factory=list)


class MentorContinueRequest(BaseModel):
    conversation_id: str | None = None
    helper_conversation_id: str | None = None
    message: str
    profile: dict[str, str] = Field(default_factory=dict)


def _converse(role_key: str, prompt: str, *, conversation_id: str | None = None) -> dict[str, Any]:
    role = load_role(role_key)
    try:
        response = service.converse_with_agent(
            role.id,
            prompt,
            chat_mode=role.chat_mode or "full_agent",
            conversation_id=conversation_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Datagrid error: {exc}") from exc
    return {
        "role": role_key,
        "agent_id": role.id,
        "agent_name": role.name,
        "text": service.response_text(response),
        "conversation_id": getattr(response, "conversation_id", None),
    }


def _format_profile(profile: dict[str, str]) -> str:
    if not profile:
        return "(not provided)"
    return "\n".join(f"- {key}: {value}" for key, value in profile.items() if value)


def _format_answers(answers: list[SurveyAnswer]) -> str:
    if not answers:
        return "(none)"
    blocks = []
    for item in answers:
        blocks.append(f"Q: {item.question}\nA: {item.answer}")
    return "\n\n".join(blocks)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/lessons/extract")
def lessons_extract(body: LessonsRequest) -> dict[str, Any]:
    prompt = f"""
You are extracting lessons learned from a construction project closeout survey.

## Respondent
{_format_profile(body.profile)}

## Closeout survey responses
{_format_answers(body.answers)}

## Task
Produce a clear lessons-learned brief for the project archive:
1. Executive summary (5-8 sentences)
2. Ranked lessons table: Lesson | Category | What happened | Recommendation | Priority (high/med/low)
3. Top 5 actions the organization should institutionalize
4. Risks of ignoring these lessons

Be concrete and construction-specific. Use the survey answers as primary evidence.
""".strip()
    result = _converse("lessons_extractor", prompt)
    return {"ok": True, "result": result}


@app.post("/api/mentor/session")
def mentor_session(body: MentorStartRequest) -> dict[str, Any]:
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    mentor_prompt = f"""
You are advising a construction professional.

## Who they are
{_format_profile(body.profile)}

## Their initial ask
{body.prompt.strip()}

## Follow-up answers
{_format_answers(body.followups)}

## Task
1. Reflect their situation in 2-4 sentences.
2. Give a practical mentoring response with prioritized guidance.
3. End with 3 sharp clarifying questions only if truly needed; otherwise give a decisive recommendation.
""".strip()

    mentor = _converse("mentor", mentor_prompt)

    helper_prompt = f"""
A construction mentor is helping a user. Use project lessons / historical patterns to strengthen the advice.

## User profile
{_format_profile(body.profile)}

## User ask
{body.prompt.strip()}

## Follow-ups
{_format_answers(body.followups)}

## Mentor response so far
{mentor.get("text") or "(empty)"}

## Task
Provide complementary evidence-backed support:
1. Relevant historical patterns or failure modes
2. A short table: Insight | Why it matters | What to do Monday morning
3. One warning the mentor may have underweighted
""".strip()

    # Second agent: lessons extractor as research/support for the mentor.
    helper = _converse("lessons_extractor", helper_prompt)

    return {
        "ok": True,
        "mentor": mentor,
        "helper": helper,
    }


@app.post("/api/mentor/continue")
def mentor_continue(body: MentorContinueRequest) -> dict[str, Any]:
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    mentor_prompt = f"""
Continue mentoring this construction professional.

## Profile
{_format_profile(body.profile)}

## Their message
{body.message.strip()}

Stay practical, decisive, and specific.
""".strip()
    mentor = _converse(
        "mentor",
        mentor_prompt,
        conversation_id=body.conversation_id,
    )

    helper_prompt = f"""
Support the mentor with lessons-learned evidence for this follow-up.

## Profile
{_format_profile(body.profile)}

## User message
{body.message.strip()}

## Latest mentor reply
{mentor.get("text") or "(empty)"}

Give a concise evidence supplement (max 1 short table + 3 bullets).
""".strip()
    helper = _converse(
        "lessons_extractor",
        helper_prompt,
        conversation_id=body.helper_conversation_id,
    )
    return {"ok": True, "mentor": mentor, "helper": helper}
