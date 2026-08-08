"""Construction Lessons Learned web API — extractor + mentor over Datagrid."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env", override=False)
# Cloud / local secret name variants
if not os.environ.get("DATAGRID_API_KEY") and os.environ.get("Datagrid_API_KEY"):
    os.environ["DATAGRID_API_KEY"] = os.environ["Datagrid_API_KEY"]

from datagrid_agents import service  # noqa: E402
from datagrid_agents.orchestrator.registry import load_role  # noqa: E402
from server.interview import DEFAULT_FOLLOWUPS, parse_questions  # noqa: E402

app = FastAPI(title="Construction Lessons Learned", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QAItem(BaseModel):
    question: str
    answer: str = ""


class FollowupsRequest(BaseModel):
    mode: Literal["lessons", "mentor"]
    prompt: str
    prior: list[QAItem] = Field(default_factory=list)


class LessonsRequest(BaseModel):
    prompt: str
    answers: list[QAItem] = Field(default_factory=list)


class MentorStartRequest(BaseModel):
    prompt: str
    followups: list[QAItem] = Field(default_factory=list)


class MentorContinueRequest(BaseModel):
    conversation_id: str | None = None
    helper_conversation_id: str | None = None
    message: str
    prompt: str = ""


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


def _format_answers(answers: list[QAItem]) -> str:
    if not answers:
        return "(none yet)"
    blocks = []
    for item in answers:
        answer = item.answer.strip() or "(no answer)"
        blocks.append(f"Q: {item.question.strip()}\nA: {answer}")
    return "\n\n".join(blocks)


def _build_followup_prompt(body: FollowupsRequest) -> str:
    prior_block = _format_answers(body.prior)
    if body.mode == "lessons":
        focus = (
            "Focus on what happened, root causes, impacts, decisions, "
            "stakeholders, and what should change next time."
        )
        purpose = "extract durable lessons learned from a construction experience"
    else:
        focus = (
            "Focus on the live decision, options, constraints, stakes, "
            "what has already been tried, and what good looks like."
        )
        purpose = "mentor a construction professional on a live problem"

    return f"""
You are interviewing someone so a specialist agent can later {purpose}.

## Their opening statement
{body.prompt.strip()}

## Answers already collected
{prior_block}

## Instructions
Write 4 to 6 specific follow-up questions that dig into missing context.
{focus}
Do not repeat questions already asked.
Ask one thing per question. Be concrete and construction-specific.
Do not answer the questions. Do not include commentary.

Return ONLY valid JSON in this exact shape:
{{"questions":["question 1","question 2","question 3"]}}
""".strip()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/context/followups")
def context_followups(body: FollowupsRequest) -> dict[str, Any]:
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    # Mentor is the conversational interviewer for both paths.
    result = _converse("mentor", _build_followup_prompt(body))
    questions = parse_questions(result.get("text") or "")
    used_fallback = False
    if not questions:
        used_fallback = True
        questions = list(DEFAULT_FOLLOWUPS[body.mode])
        if body.prior:
            asked = {item.question.strip().lower() for item in body.prior}
            questions = [q for q in questions if q.lower() not in asked] or questions

    return {
        "ok": True,
        "mode": body.mode,
        "questions": questions,
        "used_fallback": used_fallback,
        "interviewer": {
            "agent_id": result.get("agent_id"),
            "agent_name": result.get("agent_name"),
            "conversation_id": result.get("conversation_id"),
        },
    }


@app.post("/api/lessons/extract")
def lessons_extract(body: LessonsRequest) -> dict[str, Any]:
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    prompt = f"""
You are extracting lessons learned from a construction professional's account.

## Opening statement
{body.prompt.strip()}

## Follow-up interview
{_format_answers(body.answers)}

## Task
Produce a clear lessons-learned brief for the project archive:
1. Executive summary (5-8 sentences)
2. Ranked lessons table: Lesson | Category | What happened | Recommendation | Priority (high/med/low)
3. Top 5 actions the organization should institutionalize
4. Risks of ignoring these lessons

Be concrete and construction-specific. Use the opening statement and interview answers as primary evidence.
""".strip()
    result = _converse("lessons_extractor", prompt)
    return {"ok": True, "result": result}


@app.post("/api/mentor/session")
def mentor_session(body: MentorStartRequest) -> dict[str, Any]:
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    mentor_prompt = f"""
You are advising a construction professional.

## Their opening statement
{body.prompt.strip()}

## Follow-up interview
{_format_answers(body.followups)}

## Task
1. Reflect their situation in 2-4 sentences.
2. Give a practical mentoring response with prioritized guidance.
3. End with 3 sharp clarifying questions only if truly needed; otherwise give a decisive recommendation.
""".strip()

    mentor = _converse("mentor", mentor_prompt)

    helper_prompt = f"""
A construction mentor is helping a user. Use project lessons / historical patterns to strengthen the advice.

## User opening statement
{body.prompt.strip()}

## Follow-up interview
{_format_answers(body.followups)}

## Mentor response so far
{mentor.get("text") or "(empty)"}

## Task
Provide complementary evidence-backed support:
1. Relevant historical patterns or failure modes
2. A short table: Insight | Why it matters | What to do Monday morning
3. One warning the mentor may have underweighted
""".strip()

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

    context = f"\n\n## Original opening statement\n{body.prompt.strip()}" if body.prompt.strip() else ""

    mentor_prompt = f"""
Continue mentoring this construction professional.{context}

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
Support the mentor with lessons-learned evidence for this follow-up.{context}

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
