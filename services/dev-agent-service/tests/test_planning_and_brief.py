"""AI breakdown validation (with a stubbed LLM) and the brief / launch commands."""
import json

import pytest

from src import brief, planning

TICKET = {"ticket_id": "APM-4", "ticket_type": "story", "priority": "High", "status": "Open",
          "title": "Migrate auth tokens to rotating refresh flow", "description": "Short-lived access tokens."}


@pytest.fixture
def llm(monkeypatch):
    """Replace the LLM with a canned reply; returns the list of prompts it received."""
    prompts = []

    def install(reply):
        async def fake_call_llm(prompt, system, **kwargs):
            prompts.append(prompt)
            return reply
        monkeypatch.setattr(planning, "call_llm", fake_call_llm)
        monkeypatch.setattr(planning, "llm_configured", lambda: True)
        return prompts
    return install


async def test_breakdown_cleans_up_model_output(llm):
    prompts = llm("```json\n" + json.dumps({"summary": "By layer.", "subtasks": [
        {"title": "Add refresh_tokens table", "ticket_type": "task", "estimate_hours": 3, "depends_on": []},
        {"title": "Issue short-lived tokens", "ticket_type": "feature", "estimate_hours": "6", "depends_on": [1]},
        {"title": "Rotate on use", "ticket_type": "nonsense", "estimate_hours": 99, "depends_on": [1, 3, 9, "x"]},
        {"title": "   ", "description": "dropped – empty title"},
    ]}) + "\n```")
    result = await planning.breakdown(TICKET, [{"title": "Existing child", "status": "Open"}], None)

    assert [s["title"] for s in result["subtasks"]] == [
        "Add refresh_tokens table", "Issue short-lived tokens", "Rotate on use"]
    third = result["subtasks"][2]
    assert third["ticket_type"] == "task"          # unknown type normalised
    assert third["estimate_hours"] == 40           # clamped
    assert third["depends_on"] == [1]              # only earlier, valid items
    assert result["subtasks"][1]["estimate_hours"] == 6
    assert "Existing sub-tasks" in prompts[0]      # avoids duplicating existing work


async def test_breakdown_without_key_or_output_fails_clearly(llm, monkeypatch):
    monkeypatch.setattr(planning, "llm_configured", lambda: False)
    with pytest.raises(RuntimeError, match="No LLM API key"):
        await planning.breakdown(TICKET, [], None)

    llm(json.dumps({"summary": "", "subtasks": []}))
    with pytest.raises(RuntimeError, match="did not return any sub-tasks"):
        await planning.breakdown(TICKET, [], None)


async def test_plan_for_brief_never_raises(llm, monkeypatch):
    llm("not json at all")
    assert await planning.plan_for_brief(TICKET, []) is None
    monkeypatch.setattr(planning, "llm_configured", lambda: False)
    assert await planning.plan_for_brief(TICKET, []) is None


def test_launch_commands_are_safe_to_paste():
    cmds = brief.launch_commands("APM-7", r"C:\work\APM-7", ".apm/APM-7.md", ".apm/mcp.json")
    claude = cmds["claude-code"]["lines"]
    assert claude[0] == r'cd "C:\work\APM-7"'
    assert claude[1].startswith('claude "Read .apm/APM-7.md')
    assert claude[1].endswith("--mcp-config .apm/mcp.json")    # variadic flag last, after the prompt
    prompt = claude[1].split('"')[1]
    assert "wait for my go-ahead" in prompt
    assert cmds["codex"]["lines"][1].startswith('codex "Read .apm/APM-7.md')
    assert cmds["cursor"]["deeplink"].startswith("cursor://anysphere.cursor-deeplink/prompt?text=Read%20")


def test_brief_contains_context_and_manual_mode_rules():
    events = [{"kind": "priority_changed", "actor": "priority-agent", "summary": "Priority Medium → High",
               "created_at": "2026-10-03T10:00:00", "data": {"reason": "Blocks all sign-ins."}}]
    code = {"terms": ["token"], "relevant_files": [{"path": "auth/tokens.py", "matched": ["token"], "language": "python",
                                                    "excerpts": [{"start": 1, "end": 2, "code": "def rotate(): ..."}],
                                                    "commits": []}],
            "related_commits": [], "layout": [{"dir": "auth", "files": 3}],
            "conventions": {"files": ["AGENTS.md"], "previews": {}}, "test_commands": ["pytest"]}
    md = brief.render(TICKET, events, None, [], [], None, code, None,
                      "apm/APM-4-migrate", "main", "claude-code", mcp_enabled=True, notes=[])

    assert md.startswith("# APM-4 · Migrate auth tokens to rotating refresh flow")
    assert "> Blocks all sign-ins." in md
    assert "### `auth/tokens.py`" in md and "```python" in md
    assert "`pytest`" in md
    assert "Wait for the developer to confirm before editing code" in md
    assert "`APM-4: <what changed>`" in md
    assert "update_ticket_status" in md


def test_mcp_config_points_at_the_ticket():
    cfg = brief.mcp_config("python", "/srv/mcp.py", "http://localhost:3001", "APM-9")
    server = cfg["mcpServers"]["autonomous-pm"]
    assert server["args"] == ["/srv/mcp.py"]
    assert server["env"] == {"TICKET_SERVICE_URL": "http://localhost:3001", "APM_TICKET_ID": "APM-9"}
