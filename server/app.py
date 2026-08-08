"""Lessons Learned web API — multi-pass extractor over Datagrid."""

from __future__ import annotations

import json
import os
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
from server.jsonutil import extract_json  # noqa: E402
from server.lessons_pipeline import (  # noqa: E402
    TARGET_FINDINGS,
    ensure_fifty,
    run_multipass_extraction,
)

app = FastAPI(title="Lessons Learned", version="0.4.0")
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
    prompt: str
    prior: list[QAItem] = Field(default_factory=list)


class LessonsRequest(BaseModel):
    prompt: str
    answers: list[QAItem] = Field(default_factory=list)


class LessonsContinueRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    prompt: str = ""
    findings: list[dict[str, Any]] = Field(default_factory=list)


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
    return f"""
You are interviewing someone so a lessons-learned extractor can capture durable project insights.

## Their opening statement
{body.prompt.strip()}

## Answers already collected
{prior_block}

## Instructions
Write 4 to 6 specific follow-up questions that dig into missing context.
Focus on what happened, root causes, impacts, decisions, stakeholders, and what should change next time.
Do not repeat questions already asked.
Ask one thing per question. Be concrete and construction-specific.
Do not answer the questions. Do not include commentary.

Return ONLY valid JSON in this exact shape:
{{"questions":["question 1","question 2","question 3"]}}
""".strip()


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@app.get("/api/health")
def health() -> dict[str, Any]:
    routes = sorted(
        {
            getattr(route, "path", "")
            for route in app.routes
            if getattr(route, "path", "").startswith("/api/")
        }
    )
    return {
        "status": "ok",
        "version": app.version,
        "routes": routes,
    }


@app.post("/api/context/followups")
def context_followups(body: FollowupsRequest) -> dict[str, Any]:
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    result = _converse("lessons_extractor", _build_followup_prompt(body))
    questions = parse_questions(result.get("text") or "")
    used_fallback = False
    if not questions:
        used_fallback = True
        questions = list(DEFAULT_FOLLOWUPS)
        if body.prior:
            asked = {item.question.strip().lower() for item in body.prior}
            questions = [q for q in questions if q.lower() not in asked] or questions

    return {
        "ok": True,
        "questions": questions,
        "used_fallback": used_fallback,
        "interviewer": {
            "agent_id": result.get("agent_id"),
            "agent_name": result.get("agent_name"),
            "conversation_id": result.get("conversation_id"),
        },
    }


def _run_lessons_job(body: LessonsRequest, emit) -> dict[str, Any]:
    """Fan out analysis passes through the Datagrid orchestrator."""
    interview = _format_answers(body.answers)

    # Default orchestrator converse (budgets/timeouts/cache handled in pipeline).
    # Per-call errors are captured by run_parallel as AgentResult.error.
    return run_multipass_extraction(
        prompt=body.prompt.strip(),
        interview=interview,
        on_event=emit,
        cache=False,
    )


@app.post("/api/lessons/extract")
def lessons_extract(body: LessonsRequest) -> dict[str, Any]:
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    events: list[tuple[str, dict[str, Any]]] = []

    def emit(event: str, data: dict[str, Any]) -> None:
        events.append((event, data))

    payload = _run_lessons_job(body, emit)
    return {"ok": True, **payload, "events": [{"event": e, "data": d} for e, d in events]}


@app.post("/api/lessons/extract/stream")
def lessons_extract_stream(body: LessonsRequest) -> StreamingResponse:
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    event_queue: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

    def emit(event: str, data: dict[str, Any]) -> None:
        event_queue.put((event, data))

    def worker() -> None:
        try:
            emit(
                "step",
                {
                    "id": "start",
                    "label": "Starting multi-pass lessons extraction",
                    "status": "running",
                    "detail": "Orchestrator fan-out: 20 analysis calls + cross-reference aggregate",
                },
            )
            payload = _run_lessons_job(body, emit)
            emit(
                "step",
                {
                    "id": "start",
                    "label": "Starting multi-pass lessons extraction",
                    "status": "done",
                    "detail": "Pipeline finished",
                },
            )
            emit("result", {"ok": True, **payload})
        except Exception as exc:  # noqa: BLE001
            emit("error", {"detail": str(exc)})
        finally:
            event_queue.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_iter() -> Iterator[str]:
        yield _sse(
            "step",
            {
                "id": "connect",
                "label": "Connected to extraction pipeline",
                "status": "done",
                "detail": "Streaming reasoning and pass progress",
            },
        )
        while True:
            item = event_queue.get()
            if item is None:
                yield _sse("done", {"ok": True})
                break
            event, data = item
            yield _sse(event, data)

    return StreamingResponse(
        event_iter(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/lessons/continue")
def lessons_continue(body: LessonsContinueRequest) -> dict[str, Any]:
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    context = f"\n\n## Original opening statement\n{body.prompt.strip()}" if body.prompt.strip() else ""
    findings_block = ""
    if body.findings:
        findings_block = (
            f"\n\n## Current top findings table ({min(len(body.findings), TARGET_FINDINGS)} rows)\n"
            f"{json.dumps(body.findings[:TARGET_FINDINGS], ensure_ascii=False)}"
        )

    prompt = f"""
Continue the lessons-learned extraction conversation with the user.{context}{findings_block}

## Their follow-up question
{body.message.strip()}

## Instructions
Answer clearly and specifically.
If the user asks to revise, filter, expand, or re-rank findings, return updated structured output.
When you update findings, include EXACTLY {TARGET_FINDINGS} rows.

Prefer this JSON shape when updating the table:
{{
  "reply": "natural language answer",
  "summary": "optional updated summary",
  "actions": ["optional", "actions"],
  "findings": [{{"rank": 1, "finding": "...", "category": "...", "evidence": "...", "recommendation": "...", "priority": "high|med|low", "sources": ["..."]}}]
}}

If no table update is needed, still return JSON: {{"reply": "..."}}
""".strip()

    result = _converse("lessons_extractor", prompt, conversation_id=body.conversation_id)
    parsed = extract_json(result.get("text") or "")
    reply = result.get("text") or ""
    findings = body.findings
    summary = None
    actions = None

    if isinstance(parsed, dict):
        reply = str(parsed.get("reply") or parsed.get("answer") or reply).strip()
        if isinstance(parsed.get("findings"), list) and parsed["findings"]:
            ensured = ensure_fifty(parsed, [])
            findings = ensured["findings"]
            summary = ensured.get("summary") or parsed.get("summary")
            actions = ensured.get("actions") or parsed.get("actions")
        else:
            if parsed.get("summary"):
                summary = str(parsed["summary"]).strip()
            if isinstance(parsed.get("actions"), list):
                actions = [str(a).strip() for a in parsed["actions"] if str(a).strip()]

    return {
        "ok": True,
        "result": result,
        "reply": reply,
        "summary": summary,
        "actions": actions,
        "findings": findings,
    }
