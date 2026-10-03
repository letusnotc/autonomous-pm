"""
config.py – Service configuration and the persisted agent settings.

Settings (linked repo, default agent, auto-prepare) are edited from the
dashboard and stored as JSON in DATA_DIR, so they survive restarts.
"""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field

SERVICE_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR     = Path(os.getenv("DEV_AGENT_DATA_DIR", SERVICE_ROOT / "data")).resolve()

TICKET_SERVICE_URL = os.getenv("TICKET_SERVICE_URL", "http://localhost:3001")
# URL the coding agent's MCP server uses to reach the Ticket Service from the
# developer's machine (differs from TICKET_SERVICE_URL inside Docker).
TICKET_SERVICE_PUBLIC_URL = os.getenv("TICKET_SERVICE_PUBLIC_URL", TICKET_SERVICE_URL)

MCP_SERVER_PATH = Path(os.getenv("MCP_SERVER_PATH", SERVICE_ROOT / "mcp" / "ticket_mcp_server.py")).resolve()
# Any Python 3.8+ works – the MCP server only uses the standard library.
MCP_PYTHON = os.getenv("MCP_PYTHON", "python")

AgentKind = Literal["claude-code", "codex", "cursor"]
AGENT_LABELS: Dict[str, str] = {"claude-code": "Claude Code", "codex": "Codex", "cursor": "Cursor"}


class AgentSettings(BaseModel):
    repo_path:      Optional[str] = Field(None, description="Local clone of the codebase linked to the board")
    repo_url:       Optional[str] = Field(None, description="Git URL to clone when no local path is set")
    base_branch:    Optional[str] = Field(None, description="Branch new ticket branches start from (default: repo default)")
    workspaces_dir: Optional[str] = Field(None, description="Where per-ticket worktrees are created")
    default_agent:  AgentKind     = "claude-code"
    auto_prepare:   bool          = Field(False, description="Prepare an agent session for every new ticket")
    use_worktrees:  bool          = Field(True,  description="Create a git worktree + branch per ticket")

    def workspaces(self) -> Path:
        path = Path(self.workspaces_dir).expanduser() if self.workspaces_dir else Path.home() / "apm-workspaces"
        return path.resolve()


_lock = threading.Lock()


def _settings_file() -> Path:
    return DATA_DIR / "settings.json"


def load_settings() -> AgentSettings:
    f = _settings_file()
    if f.exists():
        return AgentSettings.model_validate_json(f.read_text(encoding="utf-8"))
    return AgentSettings(
        repo_path=os.getenv("AGENT_REPO_PATH") or None,
        repo_url=os.getenv("AGENT_REPO_URL") or None,
        default_agent=os.getenv("AGENT_DEFAULT", "claude-code"),
        auto_prepare=os.getenv("AGENT_AUTO_PREPARE", "false").lower() == "true",
    )


def save_settings(settings: AgentSettings):
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _settings_file().write_text(settings.model_dump_json(indent=2), encoding="utf-8")


# ── Session records ──────────────────────────────────────────────────────────

def _sessions_file() -> Path:
    return DATA_DIR / "sessions.json"


def load_sessions() -> Dict[str, dict]:
    f = _sessions_file()
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def save_session(ticket_id: str, session: dict):
    with _lock:
        sessions = load_sessions()
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        sessions[ticket_id] = session
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _sessions_file().write_text(json.dumps(sessions, indent=2), encoding="utf-8")
