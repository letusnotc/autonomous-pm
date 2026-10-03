"""
sessions.py – Prepares a manual-mode coding-agent session for a ticket.

1. Gather ticket context (details, timeline, parent/sub-tasks, similar tickets)
2. Resolve the linked repo and create a dedicated worktree + branch
3. Analyse the code for relevant files, conventions and test commands
4. Optionally ask the LLM for acceptance criteria and a plan
5. Write the brief (.apm/APM-x.md) and MCP config into the worktree
6. Return ready-to-run commands for Claude Code, Codex and Cursor

No code is changed and nothing is pushed – the developer starts the agent.
"""
import asyncio
import json
import logging
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import brief, planning, tickets
from . import repo as git
from .config import (
    AGENT_LABELS, DATA_DIR, MCP_PYTHON, MCP_SERVER_PATH, TICKET_SERVICE_PUBLIC_URL,
    AgentSettings, load_sessions, save_session,
)
from .context import build_code_context

logger = logging.getLogger("dev-agent.sessions")

_locks: Dict[str, asyncio.Lock] = {}


def branch_name(ticket: Dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", ticket["title"].lower()).strip("-")[:40].rstrip("-")
    return f"apm/{ticket['ticket_id']}-{slug}" if slug else f"apm/{ticket['ticket_id']}"


def resolve_repo(settings: AgentSettings) -> Optional[Path]:
    if settings.repo_path:
        path = Path(settings.repo_path).expanduser()
        if not git.is_git_repo(path):
            raise git.GitError(f"{path} is not a git repository")
        return git.toplevel(path)
    if settings.repo_url:
        return git.clone_or_update(settings.repo_url, DATA_DIR / "repos" / git.repo_name_from_url(settings.repo_url))
    return None


def _mcp_python() -> str:
    # The MCP server is stdlib-only, so this service's own interpreter is a safe default.
    return MCP_PYTHON if MCP_PYTHON != "python" else sys.executable


def _prepare_workspace(settings: AgentSettings, ticket: Dict) -> Tuple[Optional[Path], Optional[Path], Optional[str], Optional[str], bool, List[str]]:
    """Returns (repo, workdir, branch, base_branch, branch_created, notes). Runs in a thread."""
    notes: List[str] = []
    try:
        repo = resolve_repo(settings)
    except (git.GitError, OSError, subprocess.TimeoutExpired) as e:
        return None, None, None, None, False, [f"Linked repository unavailable: {e}"]
    if repo is None:
        return None, None, None, None, False, [
            "No repository is linked yet, so this brief has no code context. Link one in Agent settings."]

    branch = branch_name(ticket)
    base = git.default_branch(repo, settings.base_branch)
    if not settings.use_worktrees:
        notes.append(f"Worktrees are disabled – create the branch yourself: git switch -c {branch}")
        return repo, repo, branch, base, False, notes

    workdir = settings.workspaces() / repo.name / ticket["ticket_id"]
    try:
        git.ensure_worktree(repo, workdir, branch, base)
        git.add_local_excludes(repo, [".apm/", ".cursor/mcp.json"])
        return repo, workdir, branch, base, True, notes
    except (git.GitError, OSError) as e:
        notes.append(f"Could not create a worktree ({e}); using the main checkout read-only. "
                     f"Create the branch yourself: git switch -c {branch}")
        return repo, repo, branch, base, False, notes


def _write_files(ticket_id: str, workdir: Optional[Path], in_worktree: bool,
                 brief_md: str) -> Dict[str, Optional[str]]:
    """Write the brief and MCP configs. Never writes into the developer's main checkout."""
    archive = DATA_DIR / "briefs"
    archive.mkdir(parents=True, exist_ok=True)
    (archive / f"{ticket_id}.md").write_text(brief_md, encoding="utf-8")

    mcp = brief.mcp_config(_mcp_python(), str(MCP_SERVER_PATH), TICKET_SERVICE_PUBLIC_URL, ticket_id)
    mcp_json = json.dumps(mcp, indent=2)

    if in_worktree and workdir:
        apm = workdir / ".apm"
        apm.mkdir(exist_ok=True)
        (apm / f"{ticket_id}.md").write_text(brief_md, encoding="utf-8")
        (apm / "mcp.json").write_text(mcp_json, encoding="utf-8")
        cursor_cfg = workdir / ".cursor" / "mcp.json"
        tracked = git.git(workdir, "ls-files", ".cursor/mcp.json", check=False).strip()
        if not tracked and not cursor_cfg.exists():
            cursor_cfg.parent.mkdir(exist_ok=True)
            cursor_cfg.write_text(mcp_json, encoding="utf-8")
        return {"brief_path": str(apm / f"{ticket_id}.md"), "brief_ref": f".apm/{ticket_id}.md",
                "mcp_config_path": str(apm / "mcp.json"), "mcp_config_ref": ".apm/mcp.json"}

    mcp_file = archive / f"{ticket_id}.mcp.json"
    mcp_file.write_text(mcp_json, encoding="utf-8")
    brief_path = str(archive / f"{ticket_id}.md")
    return {"brief_path": brief_path, "brief_ref": brief_path,
            "mcp_config_path": str(mcp_file), "mcp_config_ref": f'"{mcp_file}"'}


async def prepare(ticket_id: str, settings: AgentSettings, agent: Optional[str] = None,
                  include_ai_plan: bool = True) -> Dict:
    lock = _locks.setdefault(ticket_id, asyncio.Lock())
    async with lock:
        return await _prepare(ticket_id, settings, agent or settings.default_agent, include_ai_plan)


async def _prepare(ticket_id: str, settings: AgentSettings, agent: str, include_ai_plan: bool) -> Dict:
    ticket = await tickets.get_ticket(ticket_id)
    tid = ticket["ticket_id"]
    events, children, similar, parent, duplicate_of = await asyncio.gather(
        tickets.get_events(tid), tickets.get_children(tid), tickets.get_similar(tid),
        tickets.get_optional(ticket.get("parent_id")), tickets.get_optional(ticket.get("duplicate_of")),
    )

    repo, workdir, branch, base, branch_created, notes = await asyncio.to_thread(_prepare_workspace, settings, ticket)

    code = None
    if workdir:
        related = [t for t in [ticket.get("parent_id"), ticket.get("duplicate_of"), *(s["ticket_id"] for s in similar)] if t]
        code = await asyncio.to_thread(build_code_context, workdir, ticket["title"], ticket.get("description"), related)

    plan = await planning.plan_for_brief(ticket, code["relevant_files"] if code else []) if include_ai_plan else None
    if include_ai_plan and plan is None:
        notes.append("AI acceptance criteria and plan were skipped (no working LLM key).")

    brief_md = brief.render(
        ticket, events, parent, children, similar, duplicate_of, code, plan,
        branch if branch_created else None, base, agent, mcp_enabled=True, notes=notes,
    )
    files = await asyncio.to_thread(_write_files, tid, workdir, branch_created, brief_md)
    commands = brief.launch_commands(tid, str(workdir) if workdir else None, files["brief_ref"],
                                     files["mcp_config_ref"])

    session = {
        "ticket_id": tid,
        "agent": agent,
        "mode": "manual",
        "repo_path": str(repo) if repo else None,
        "workdir": str(workdir) if workdir else None,
        "branch": branch,
        "branch_created": branch_created,
        "base_branch": base,
        "brief_path": files["brief_path"],
        "mcp_config_path": files["mcp_config_path"],
        "codex_mcp_toml": brief.codex_mcp_toml(_mcp_python(), str(MCP_SERVER_PATH), TICKET_SERVICE_PUBLIC_URL),
        "commands": commands,
        "relevant_files": [{"path": f["path"], "matched": f["matched"]} for f in (code or {}).get("relevant_files", [])],
        "test_commands": (code or {}).get("test_commands", []),
        "ai_plan": plan is not None,
        "notes": notes,
        "created_at": (load_sessions().get(tid) or {}).get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    refreshed = tid in load_sessions()
    save_session(tid, session)

    where = f" on branch {branch}" if branch_created else ""
    verb = "refreshed" if refreshed else "prepared"
    try:
        await tickets.add_event(
            tid, "agent_session",
            f"Agent session {verb} for {AGENT_LABELS.get(agent, agent)}{where}",
            {"agent": agent, "branch": branch if branch_created else None,
             "workdir": session["workdir"], "files": len(session["relevant_files"])},
        )
    except Exception as e:  # the session is still usable without the timeline entry
        logger.warning(f"Could not record timeline event for {tid}: {e}")
    return session
