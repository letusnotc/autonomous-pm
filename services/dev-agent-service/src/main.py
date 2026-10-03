"""
main.py – Dev Agent Service
Turns tickets into ready-to-do work: AI breakdown into sub-tasks, and
manual-mode coding-agent sessions (Claude Code, Codex, Cursor) with full
ticket + codebase context.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from . import planning, sessions, tickets
from . import repo as git
from .config import DATA_DIR, AgentKind, AgentSettings, load_sessions, load_settings, save_settings
from .llm import llm_configured

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
logger = logging.getLogger("dev-agent")

app = FastAPI(
    title="Autonomous PM – Dev Agent Service",
    description="Ticket breakdown and coding-agent session preparation (manual mode).",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _upstream_error(e: Exception) -> HTTPException:
    if isinstance(e, tickets.TicketNotFound):
        return HTTPException(404, "Ticket not found")
    if isinstance(e, httpx.HTTPError):
        return HTTPException(502, f"Ticket Service error: {e}")
    return HTTPException(500, str(e))


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok", "service": "dev-agent-service", "llm_configured": llm_configured()}


# ── Settings ─────────────────────────────────────────────────────────────────

@app.get("/settings", response_model=AgentSettings, tags=["settings"])
async def get_settings():
    return load_settings()


@app.put("/settings", response_model=AgentSettings, tags=["settings"])
async def put_settings(settings: AgentSettings):
    settings.repo_path = (settings.repo_path or "").strip() or None
    settings.repo_url = (settings.repo_url or "").strip() or None
    settings.base_branch = (settings.base_branch or "").strip() or None
    settings.workspaces_dir = (settings.workspaces_dir or "").strip() or None
    if settings.repo_path and not await asyncio.to_thread(git.is_git_repo, Path(settings.repo_path).expanduser()):
        raise HTTPException(422, f"'{settings.repo_path}' is not a git repository")
    save_settings(settings)
    return settings


@app.get("/repo/status", tags=["settings"])
async def repo_status():
    settings = load_settings()
    if not (settings.repo_path or settings.repo_url):
        return {"configured": False, "llm_configured": llm_configured()}
    try:
        repo = await asyncio.to_thread(sessions.resolve_repo, settings)
        info = await asyncio.to_thread(git.head_info, repo)
        base = await asyncio.to_thread(git.default_branch, repo, settings.base_branch)
        return {"configured": True, "ok": True, "path": str(repo), "base_branch": base,
                "workspaces_dir": str(settings.workspaces()), "llm_configured": llm_configured(), **info}
    except Exception as e:
        return {"configured": True, "ok": False, "error": str(e), "llm_configured": llm_configured()}


# ── Breakdown ────────────────────────────────────────────────────────────────

class ProposedSubtask(BaseModel):
    title:          str = Field(..., min_length=1, max_length=200)
    description:    Optional[str] = None
    ticket_type:    str = "task"
    estimate_hours: Optional[int] = None
    depends_on:     List[int] = []


class ApplyBreakdown(BaseModel):
    subtasks: List[ProposedSubtask] = Field(..., min_length=1, max_length=20)


@app.post("/tickets/{ticket_id}/breakdown", tags=["breakdown"])
async def propose_breakdown(ticket_id: str):
    """Ask the LLM to split a ticket into sub-tasks. Nothing is created until /apply."""
    try:
        ticket = await tickets.get_ticket(ticket_id)
        children = await tickets.get_children(ticket["ticket_id"])
    except Exception as e:
        raise _upstream_error(e)

    layout = None
    settings = load_settings()
    if settings.repo_path or settings.repo_url:
        try:
            from .context import layout as repo_layout
            repo = await asyncio.to_thread(sessions.resolve_repo, settings)
            layout = repo_layout(await asyncio.to_thread(git.ls_files, repo))
        except Exception as e:
            logger.info(f"Breakdown without repo layout: {e}")
    try:
        return await planning.breakdown(ticket, children, layout)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception as e:
        logger.error(f"Breakdown failed for {ticket_id}: {e}")
        raise HTTPException(502, f"LLM breakdown failed: {e}")


@app.post("/tickets/{ticket_id}/breakdown/apply", tags=["breakdown"])
async def apply_breakdown(ticket_id: str, payload: ApplyBreakdown):
    """Create the approved sub-tasks under the ticket."""
    items = payload.subtasks
    subtasks = []
    for i, s in enumerate(items, 1):
        extra = []
        if s.estimate_hours:
            extra.append(f"Estimate: ~{s.estimate_hours}h")
        deps = [items[d - 1].title for d in s.depends_on if 0 < d < i]
        if deps:
            extra.append("Depends on: " + "; ".join(deps))
        description = "\n\n".join(x for x in [s.description, " · ".join(extra)] if x) or None
        subtasks.append({"title": s.title, "description": description, "ticket_type": s.ticket_type})
    try:
        return await tickets.create_subtasks(ticket_id, subtasks, actor="breakdown-agent")
    except Exception as e:
        raise _upstream_error(e)


# ── Agent sessions (manual mode) ─────────────────────────────────────────────

class PrepareRequest(BaseModel):
    agent:           Optional[AgentKind] = None
    include_ai_plan: bool = True


@app.post("/tickets/{ticket_id}/session", tags=["agent-session"])
async def prepare_session(ticket_id: str, payload: PrepareRequest = PrepareRequest()):
    """Build the context pack, worktree and launch commands for a coding agent."""
    try:
        return await sessions.prepare(ticket_id, load_settings(), payload.agent, payload.include_ai_plan)
    except Exception as e:
        logger.error(f"Session prep failed for {ticket_id}: {e}", exc_info=not isinstance(e, tickets.TicketNotFound))
        raise _upstream_error(e)


@app.get("/tickets/{ticket_id}/session", tags=["agent-session"])
async def get_session(ticket_id: str):
    tid = ticket_id.upper() if ticket_id.upper().startswith("APM-") else f"APM-{ticket_id}"
    session = load_sessions().get(tid)
    if not session:
        raise HTTPException(404, "No agent session prepared for this ticket yet")
    return session


@app.get("/tickets/{ticket_id}/brief", response_class=PlainTextResponse, tags=["agent-session"])
async def get_brief(ticket_id: str):
    tid = ticket_id.upper() if ticket_id.upper().startswith("APM-") else f"APM-{ticket_id}"
    path = DATA_DIR / "briefs" / f"{tid}.md"
    if not path.exists():
        raise HTTPException(404, "No brief prepared for this ticket yet")
    return path.read_text(encoding="utf-8")


@app.post("/auto-prepare/{ticket_id}", tags=["agent-session"])
async def auto_prepare(ticket_id: str):
    """Called by the orchestrator for new tickets; only acts when auto-prepare is enabled."""
    settings = load_settings()
    if not settings.auto_prepare:
        return {"prepared": False, "reason": "auto_prepare disabled"}
    try:
        session = await sessions.prepare(ticket_id, settings)
        return {"prepared": True, "session": session}
    except Exception as e:
        logger.warning(f"Auto-prepare failed for {ticket_id}: {e}")
        return {"prepared": False, "reason": str(e)}
