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
from server.interview import (  # noqa: E402
    DEFAULT_FOLLOWUPS,
    parse_questions,
    parse_reasoning_steps,
)
from server.jsonutil import extract_json  # noqa: E402
from server.knowledge import (  # noqa: E402
    UPLOAD_GUIDANCE,
    build_deep_search_confirm_prompt,
    list_knowledge_catalog,
    no_match_payload,
    parse_confirm_payload,
    rank_knowledge_matches,
)
from server.lessons_pipeline import (  # noqa: E402
    TARGET_FINDINGS,
    ensure_fifty,
    run_multipass_extraction,
)

app = FastAPI(title="Lessons Learned", version="0.5.0")
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


class ProjectConfirmRequest(BaseModel):
    project: str


class FollowupsRequest(BaseModel):
    prompt: str = ""
    project: str = ""
    knowledge_name: str = ""
    prior: list[QAItem] = Field(default_factory=list)


class LessonsRequest(BaseModel):
    prompt: str = ""
    project: str = ""
    knowledge_id: str = ""
    knowledge_name: str = ""
    answers: list[QAItem] = Field(default_factory=list)


class LessonsContinueRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    prompt: str = ""
    project: str = ""
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


def _build_extraction_brief(body: LessonsRequest) -> str:
    if body.prompt.strip():
        return body.prompt.strip()
    project = body.project.strip() or "unspecified project"
    knowledge = body.knowledge_name.strip() or "workspace knowledge"
    return (
        f"Extract buried, correlative lessons learned for project '{project}' "
        f"using Datagrid knowledge '{knowledge}'. "
        "Prioritize evidence that is hard to find across RFIs, meetings, change events, "
        "submittals, schedule, and field reports."
    )


def _build_followup_prompt(body: FollowupsRequest) -> str:
    prior_block = _format_answers(body.prior)
    project = body.project.strip() or body.prompt.strip() or "(unspecified)"
    knowledge = body.knowledge_name.strip() or "(confirmed workspace knowledge)"
    return f"""
You are scoping a lessons-learned extraction against Datagrid project knowledge.

## Confirmed project
{project}

## Confirmed knowledge source
{knowledge}

## Answers already collected
{prior_block}

## Instructions
Write 4 to 6 scope-narrowing questions that help the extractor do a good job.
Ask how to approach confirmation of lessons-learned guidance — not a generic
"what happened" postmortem interview.
Good angles:
- which phase/package/time window to prioritize
- which artifact types to weight
- what kinds of lessons matter most
- how to verify a lesson is real (recurrence, impact, owners)
- what to exclude
Do not repeat questions already asked.
Ask one thing per question. Be concrete and construction-specific.
Do not answer the questions. Do not include commentary.

Return ONLY valid JSON:
{{
  "questions":["question 1","question 2","question 3"],
  "reasoning_steps":[
    {{"id":"scope","label":"Framing scope questions","status":"done","detail":"..."}}
  ]
}}
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


@app.post("/api/context/confirm-project")
def confirm_project(body: ProjectConfirmRequest) -> dict[str, Any]:
    project = body.project.strip()
    if not project:
        raise HTTPException(status_code=400, detail="project is required")

    reasoning: list[dict[str, Any]] = [
        {
            "id": "ask",
            "label": "Received project request",
            "status": "done",
            "detail": project,
        },
        {
            "id": "catalog",
            "label": "Listing Datagrid knowledge sources",
            "status": "running",
            "detail": "Secondary catalog for ids / accessible names",
        },
    ]

    catalog: list[dict[str, Any]] = []
    catalog_error = ""
    try:
        catalog = list_knowledge_catalog()
    except Exception as exc:  # noqa: BLE001
        catalog_error = str(exc)
        reasoning[1] = {
            "id": "catalog",
            "label": "Knowledge catalog unavailable",
            "status": "partial",
            "detail": catalog_error,
        }
    else:
        reasoning[1] = {
            "id": "catalog",
            "label": f"Found {len(catalog)} knowledge sources",
            "status": "done",
            "detail": ", ".join(item["name"] for item in catalog[:6])
            + ("…" if len(catalog) > 6 else ""),
        }

    ranked = rank_knowledge_matches(project, catalog) if catalog else []
    reasoning.append(
        {
            "id": "deep-search",
            "label": "Deep searching project documents for matching project names",
            "status": "running",
            "detail": "Matching your request to names found in accessible files",
        }
    )

    try:
        result = _converse(
            "deep_search",
            build_deep_search_confirm_prompt(project, catalog),
        )
    except HTTPException as exc:
        confirmation = no_match_payload(
            project,
            catalog=catalog,
            detail=f"Deep search failed: {exc.detail}",
        )
        reasoning.append(
            {
                "id": "deep-search",
                "label": "Deep search failed",
                "status": "error",
                "detail": str(exc.detail),
            }
        )
        return {
            "ok": True,
            "project": project,
            "matched": False,
            "match_kind": "none",
            "project_name": None,
            "knowledge_id": None,
            "knowledge_name": None,
            "confidence": "low",
            "rationale": confirmation["rationale"],
            "evidence": [],
            "accessible_projects": confirmation.get("accessible_projects") or [],
            "alternatives": confirmation.get("alternatives") or [],
            "upload_required": True,
            "next_step": UPLOAD_GUIDANCE,
            "candidates": ranked[:5],
            "catalog_count": len(catalog),
            "reasoning": reasoning + confirmation.get("reasoning", []),
            "agent": None,
        }

    reasoning[2] = {
        "id": "deep-search",
        "label": "Deep search complete",
        "status": "done",
        "detail": "Parsed project identity from accessible Datagrid documents",
    }

    parsed = extract_json(result.get("text") or "")
    if isinstance(parsed, dict):
        confirmation = parse_confirm_payload(parsed, catalog=catalog, ranked=ranked)
    else:
        # If the model returned prose only, treat as no match but keep catalog names.
        confirmation = no_match_payload(
            project,
            catalog=catalog,
            detail="Deep search did not return structured project identity JSON.",
        )

    if confirmation.get("reasoning"):
        reasoning.extend(confirmation["reasoning"])
    else:
        reasoning.append(
            {
                "id": "decide",
                "label": (
                    f'{confirmation.get("match_kind", "none").title()} match: '
                    f'{confirmation.get("project_name") or confirmation.get("knowledge_name")}'
                    if confirmation.get("matched")
                    else "No project match in accessible Datagrid data"
                ),
                "status": "done" if confirmation.get("matched") else "partial",
                "detail": confirmation.get("rationale") or "",
            }
        )

    return {
        "ok": True,
        "project": project,
        "matched": confirmation["matched"],
        "match_kind": confirmation.get("match_kind") or ("exact" if confirmation["matched"] else "none"),
        "project_name": confirmation.get("project_name") or confirmation.get("knowledge_name"),
        "knowledge_id": confirmation.get("knowledge_id"),
        "knowledge_name": confirmation.get("knowledge_name"),
        "confidence": confirmation.get("confidence"),
        "rationale": confirmation.get("rationale"),
        "evidence": confirmation.get("evidence") or [],
        "accessible_projects": confirmation.get("accessible_projects") or [],
        "alternatives": confirmation.get("alternatives") or [],
        "upload_required": bool(confirmation.get("upload_required")),
        "next_step": confirmation.get("next_step") or (
            UPLOAD_GUIDANCE if not confirmation["matched"] else ""
        ),
        "candidates": confirmation.get("candidates") or ranked[:5],
        "catalog_count": len(catalog),
        "reasoning": reasoning,
        "agent": {
            "role": "deep_search",
            "agent_id": result.get("agent_id"),
            "agent_name": result.get("agent_name"),
            "conversation_id": result.get("conversation_id"),
        },
    }


@app.post("/api/context/followups")
def context_followups(body: FollowupsRequest) -> dict[str, Any]:
    if not body.project.strip() and not body.prompt.strip():
        raise HTTPException(status_code=400, detail="project is required")

    result = _converse("lessons_extractor", _build_followup_prompt(body))
    questions = parse_questions(result.get("text") or "")
    reasoning = parse_reasoning_steps(result.get("text") or "")
    used_fallback = False
    if not questions:
        used_fallback = True
        questions = list(DEFAULT_FOLLOWUPS)
        if body.prior:
            asked = {item.question.strip().lower() for item in body.prior}
            questions = [q for q in questions if q.lower() not in asked] or questions
    if not reasoning:
        reasoning = [
            {
                "id": "scope",
                "label": "Built scope-narrowing questions",
                "status": "done",
                "detail": f"{len(questions)} questions to confirm extraction guidance",
            }
        ]

    return {
        "ok": True,
        "questions": questions,
        "used_fallback": used_fallback,
        "reasoning": reasoning,
        "interviewer": {
            "agent_id": result.get("agent_id"),
            "agent_name": result.get("agent_name"),
            "conversation_id": result.get("conversation_id"),
        },
    }


def _run_lessons_job(body: LessonsRequest, emit) -> dict[str, Any]:
    """Fan out analysis passes through the Datagrid orchestrator."""
    interview = _format_answers(body.answers)
    brief = _build_extraction_brief(body)

    return run_multipass_extraction(
        prompt=brief,
        interview=interview,
        on_event=emit,
        cache=False,
        project=body.project.strip(),
        knowledge_name=body.knowledge_name.strip(),
    )


@app.post("/api/lessons/extract")
def lessons_extract(body: LessonsRequest) -> dict[str, Any]:
    if not body.project.strip() and not body.prompt.strip():
        raise HTTPException(status_code=400, detail="project is required")

    events: list[tuple[str, dict[str, Any]]] = []

    def emit(event: str, data: dict[str, Any]) -> None:
        events.append((event, data))

    payload = _run_lessons_job(body, emit)
    return {"ok": True, **payload, "events": [{"event": e, "data": d} for e, d in events]}


@app.post("/api/lessons/extract/stream")
def lessons_extract_stream(body: LessonsRequest) -> StreamingResponse:
    if not body.project.strip() and not body.prompt.strip():
        raise HTTPException(status_code=400, detail="project is required")

    event_queue: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

    def emit(event: str, data: dict[str, Any]) -> None:
        event_queue.put((event, data))

    def worker() -> None:
        try:
            project = body.project.strip() or "selected project"
            emit(
                "step",
                {
                    "id": "start",
                    "label": f"Starting correlative extraction for {project}",
                    "status": "running",
                    "detail": "Orchestrator fan-out: 20 analysis calls + buried-pattern aggregate",
                },
            )
            payload = _run_lessons_job(body, emit)
            emit(
                "step",
                {
                    "id": "start",
                    "label": f"Extraction finished for {project}",
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
                "detail": "Streaming generative reasoning and pass progress",
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

    context = f"\n\n## Project\n{body.project.strip()}" if body.project.strip() else ""
    if body.prompt.strip():
        context += f"\n\n## Extraction brief\n{body.prompt.strip()}"
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
Prefer correlative explanations that show how evidence was joined across sources.
If the user asks to revise, filter, expand, or re-rank findings, return updated structured output.
When you update findings, include EXACTLY {TARGET_FINDINGS} rows.

Prefer this JSON shape when updating the table:
{{
  "reply": "natural language answer",
  "summary": "optional updated summary",
  "actions": ["optional", "actions"],
  "findings": [{{"rank": 1, "finding": "...", "category": "...", "evidence": "...", "recommendation": "...", "priority": "high|med|low", "sources": ["..."], "correlation": "..."}}],
  "reasoning_steps": [{{"id":"r1","label":"...","status":"done","detail":"..."}}]
}}

If no table update is needed, still return JSON: {{"reply": "...", "reasoning_steps":[...]}}
""".strip()

    result = _converse("lessons_extractor", prompt, conversation_id=body.conversation_id)
    parsed = extract_json(result.get("text") or "")
    reply = result.get("text") or ""
    findings = body.findings
    summary = None
    actions = None
    reasoning = parse_reasoning_steps(result.get("text") or "")

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
        "reasoning": reasoning,
    }
