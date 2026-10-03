"""
brief.py – Renders the context pack as Markdown and builds per-agent launch commands.

The brief is the single source of context for any coding agent. It is written
for manual mode: the agent is told to propose a plan and wait for the
developer before changing code.
"""
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

from .config import AGENT_LABELS


def _cell(value) -> str:
    return str(value).replace("|", "\\|") if value not in (None, "") else "—"


def _ai_reasoning(events: List[Dict]) -> Optional[str]:
    for e in reversed(events):
        if e["kind"] == "priority_changed" and (e.get("data") or {}).get("reason"):
            return e["data"]["reason"]
    return None


def kickoff_prompt(ticket_id: str, brief_ref: str) -> str:
    # No ticket text in here: it is passed on a command line, so keep it free of quotes.
    return (f"Read {brief_ref} and work on ticket {ticket_id}. Start by summarising the ticket "
            f"and proposing a plan, then wait for my go-ahead before changing any code.")


def launch_commands(ticket_id: str, workdir: Optional[str], brief_ref: str,
                    mcp_config: Optional[str]) -> Dict[str, Dict]:
    prompt = kickoff_prompt(ticket_id, brief_ref)
    cd = [f'cd "{workdir}"'] if workdir else []
    claude = f'claude "{prompt}"' + (f" --mcp-config {mcp_config}" if mcp_config else "")
    return {
        "claude-code": {"label": AGENT_LABELS["claude-code"], "lines": cd + [claude]},
        "codex":       {"label": AGENT_LABELS["codex"],       "lines": cd + [f'codex "{prompt}"']},
        "cursor": {
            "label": AGENT_LABELS["cursor"],
            "lines": [f'cursor "{workdir}"'] if workdir else [],
            "cli_lines": cd + [f'cursor-agent "{prompt}"'],
            # Opens Cursor's chat with the prompt pre-filled (after opening the folder)
            "deeplink": "cursor://anysphere.cursor-deeplink/prompt?text=" + quote(prompt),
        },
    }


def mcp_config(python: str, server_path: str, ticket_service_url: str, ticket_id: str) -> Dict:
    return {"mcpServers": {"autonomous-pm": {
        "command": python,
        "args": [server_path],
        "env": {"TICKET_SERVICE_URL": ticket_service_url, "APM_TICKET_ID": ticket_id},
    }}}


def codex_mcp_toml(python: str, server_path: str, ticket_service_url: str) -> str:
    return (
        "[mcp_servers.autonomous-pm]\n"
        f"command = {json.dumps(python)}\n"
        f"args = [{json.dumps(server_path)}]\n"
        f"env = {{ TICKET_SERVICE_URL = {json.dumps(ticket_service_url)} }}\n"
    )


def render(
    ticket: Dict,
    events: List[Dict],
    parent: Optional[Dict],
    children: List[Dict],
    similar: List[Dict],
    duplicate_of: Optional[Dict],
    code: Optional[Dict],
    plan: Optional[Dict],
    branch: Optional[str],
    base_branch: Optional[str],
    agent: str,
    mcp_enabled: bool,
    notes: List[str],
) -> str:
    tid = ticket["ticket_id"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out: List[str] = []
    w = out.append

    w(f"# {tid} · {ticket['title']}\n")
    where = f" on branch `{branch}` (from `{base_branch}`)" if branch else ""
    w(f"> Context pack prepared by **Autonomous PM** for {AGENT_LABELS.get(agent, agent)}{where} · {now}\n")

    w("## Ticket\n")
    w("| Type | Status | Priority | AI score | Assignee | Reporter | Source |")
    w("|---|---|---|---|---|---|---|")
    w(f"| {_cell(ticket['ticket_type'])} | {_cell(ticket['status'])} | {_cell(ticket['priority'])} | "
      f"{_cell(ticket.get('priority_score'))} | {_cell(ticket.get('assignee'))} | "
      f"{_cell(ticket.get('reported_by'))} | {_cell(ticket.get('source'))} |\n")
    w("### Description\n")
    w((ticket.get("description") or "_No description was provided. Ask the developer for details if the "
       "title alone is ambiguous._").strip() + "\n")

    reasoning = _ai_reasoning(events)
    if reasoning:
        w("### Why it matters (AI priority reasoning)\n")
        w(f"> {reasoning}\n")

    w("## Definition of done\n")
    if plan and plan.get("acceptance_criteria"):
        w("_AI-drafted – confirm with the developer before relying on it._\n")
        out.extend(f"- [ ] {c}" for c in plan["acceptance_criteria"])
        w("")
    else:
        w("No acceptance criteria recorded. Propose some in your plan and confirm them with the developer.\n")

    if plan and plan.get("plan"):
        w("## Suggested approach\n")
        out.extend(f"{i}. {step}" for i, step in enumerate(plan["plan"], 1))
        w("")
        if plan.get("risks"):
            w("**Watch out for:**\n")
            out.extend(f"- {r}" for r in plan["risks"])
            w("")

    related_lines = []
    if parent:
        related_lines.append(f"- **Parent:** {parent['ticket_id']} – {parent['title']} ({parent['status']})")
    if duplicate_of:
        related_lines.append(f"- **Marked duplicate of:** {duplicate_of['ticket_id']} – {duplicate_of['title']} "
                             f"({duplicate_of['status']})")
    for c in children:
        related_lines.append(f"- **Sub-task:** {c['ticket_id']} – {c['title']} ({c['status']})")
    for s in similar:
        related_lines.append(f"- **Similar ({round(s['score'] * 100)}%):** {s['ticket_id']} – {s['title']} "
                             f"({s['status']}) – check whether it was already fixed or overlaps")
    if code:
        for c in code["related_commits"]:
            related_lines.append(f"- **Commit `{c['sha']}`** for {c['ticket']}: {c['subject']} "
                                 f"({c['author']}, {c['when']})")
    if related_lines:
        w("## Related work\n")
        out.extend(related_lines)
        w("")

    if code:
        w("## Where to look in the code\n")
        if code["relevant_files"]:
            w(f"Ranked by how strongly they match the ticket (search terms: "
              f"{', '.join(f'`{t}`' for t in code['terms'])}). Treat these as leads, not certainties.\n")
            for f in code["relevant_files"]:
                w(f"### `{f['path']}`\n")
                w(f"Matches: {', '.join(f['matched'])}")
                for c in f["commits"]:
                    w(f"- last changed in `{c['sha']}` {c['when']} by {c['author']}: {c['subject']}")
                w("")
                for ex in f["excerpts"]:
                    w(f"Lines {ex['start']}–{ex['end']}:")
                    w(f"```{f['language']}\n{ex['code']}\n```")
                w("")
        else:
            w("No files matched the ticket's keywords – explore the repository layout below.\n")

        w("### Repository layout\n")
        out.extend(f"- `{d['dir']}/` – {d['files']} files" if d["dir"] != "(root files)"
                   else f"- root – {d['files']} files" for d in code["layout"])
        w("")

        conv = code["conventions"]
        if conv["files"] or code["test_commands"]:
            w("## Repository conventions\n")
            if conv["files"]:
                w("Read and follow: " + ", ".join(f"`{f}`" for f in conv["files"]) + "\n")
            for name, preview in conv["previews"].items():
                w(f"<details><summary>{name} (first lines)</summary>\n\n```markdown\n{preview}\n```\n</details>\n")
            if code["test_commands"]:
                w("Checks to run before you finish:\n")
                out.extend(f"- `{c}`" for c in code["test_commands"])
                w("")

    history = [e for e in events if e["kind"] != "agent_session"][-8:]
    if history:
        w("## Ticket history\n")
        for e in history:
            reason = (e.get("data") or {}).get("reason")
            when = str(e["created_at"])[:16].replace("T", " ")
            w(f"- {when} · {e.get('actor') or 'system'}: {e['summary']}" + (f" – _{reason}_" if reason else ""))
        w("")

    w("## How to work on this ticket\n")
    steps = [
        "Summarise the ticket in your own words and propose a short plan. **Wait for the developer to "
        "confirm before editing code** – this session runs in manual mode.",
    ]
    if branch:
        steps.append(f"You are already on branch `{branch}` in a dedicated worktree. Stay on it.")
    steps += [
        f"Reference the ticket in every commit message, e.g. `{tid}: <what changed>`. The GitHub "
        "integration uses this to move the ticket automatically.",
        f"When the developer is ready, the pull request title should start with `{tid}:`.",
    ]
    if mcp_enabled:
        steps.append("The `autonomous-pm` MCP tools are available: use `get_ticket`, `get_ticket_timeline` and "
                     "`find_similar_tickets` for context, `add_progress_note` to log progress, and "
                     "`update_ticket_status` (In Progress / In Review / Blocked) as work moves.")
    out.extend(f"{i}. {s}" for i, s in enumerate(steps, 1))
    w("")

    if notes:
        w("---\n")
        out.extend(f"_Note: {n}_" for n in notes)
        w("")
    return "\n".join(out)
