"""
planning.py – LLM-backed planning: ticket breakdown and the brief's suggested plan.
"""
import logging
from typing import Dict, List, Optional

from .llm import call_llm, parse_json_response, active_model, llm_configured

logger = logging.getLogger("dev-agent.planning")

SUBTASK_TYPES = {"task", "bug", "feature", "spike", "story"}

BREAKDOWN_SYSTEM = """You are a pragmatic senior tech lead breaking a ticket into sub-tasks.

Rules:
- 3 to 8 sub-tasks, each small enough for one developer to finish in under two days.
- Each sub-task must be independently reviewable (its own pull request).
- Order them in the sequence they should be done. Include testing work where it matters.
- Do not repeat work already covered by existing sub-tasks.
- Titles are imperative and specific ("Add refresh-token table migration", not "Database").

Return ONLY valid JSON:
{
  "summary": "<one or two sentences on how you split the work>",
  "subtasks": [
    {
      "title": "<max 120 chars>",
      "description": "<what to do and how to verify it, 1-3 sentences>",
      "ticket_type": "<task|feature|bug|spike|story>",
      "estimate_hours": <integer 1-16>,
      "depends_on": [<1-based numbers of earlier sub-tasks this needs>]
    }
  ]
}"""

PLAN_SYSTEM = """You are a senior engineer preparing a ticket for a coding agent.
Given the ticket and the files most likely involved, return ONLY valid JSON:
{
  "acceptance_criteria": ["<testable statement>", "... 3-6 items"],
  "plan": ["<concrete step referencing files where possible>", "... 3-7 steps"],
  "risks": ["<edge case or risk to check>", "... 0-4 items"]
}
Be specific to the ticket. Do not invent files that are not listed unless you say they need to be created."""


def _ticket_block(ticket: Dict) -> str:
    return (f"Ticket {ticket['ticket_id']} ({ticket['ticket_type']}, priority {ticket['priority']})\n"
            f"Title: {ticket['title']}\n"
            f"Description: {ticket.get('description') or '(none)'}")


async def breakdown(ticket: Dict, existing_children: List[Dict], layout: Optional[List[Dict]]) -> Dict:
    if not llm_configured():
        raise RuntimeError("No LLM API key configured – set GEMINI_API_KEY, OPENAI_API_KEY or ANTHROPIC_API_KEY")

    prompt = [_ticket_block(ticket)]
    if existing_children:
        prompt.append("Existing sub-tasks:\n" + "\n".join(f"- {c['title']} ({c['status']})" for c in existing_children))
    if layout:
        prompt.append("Repository top-level layout:\n" + "\n".join(f"- {d['dir']} ({d['files']} files)" for d in layout))

    raw = await call_llm("\n\n".join(prompt), BREAKDOWN_SYSTEM, temperature=0.3)
    data = parse_json_response(raw)

    subtasks = []
    for i, s in enumerate(data.get("subtasks", [])[:8], 1):
        title = str(s.get("title", "")).strip()[:200]
        if not title:
            continue
        ttype = s.get("ticket_type", "task")
        deps = [int(d) for d in s.get("depends_on", []) if str(d).isdigit() and 0 < int(d) < i]
        try:
            estimate = max(1, min(40, int(s.get("estimate_hours", 4))))
        except (TypeError, ValueError):
            estimate = None
        subtasks.append({
            "title": title,
            "description": str(s.get("description", "")).strip() or None,
            "ticket_type": ttype if ttype in SUBTASK_TYPES else "task",
            "estimate_hours": estimate,
            "depends_on": deps,
        })
    if not subtasks:
        raise RuntimeError("The model did not return any sub-tasks")
    return {"ticket_id": ticket["ticket_id"], "summary": data.get("summary", ""),
            "subtasks": subtasks, "model": active_model()}


async def plan_for_brief(ticket: Dict, relevant_files: List[Dict]) -> Optional[Dict]:
    """Acceptance criteria + plan for the brief. Returns None (never raises) if unavailable."""
    if not llm_configured():
        return None
    files = "\n".join(f"- {f['path']} (matches: {', '.join(f['matched'])})" for f in relevant_files) or "(none found)"
    try:
        raw = await call_llm(f"{_ticket_block(ticket)}\n\nLikely relevant files:\n{files}", PLAN_SYSTEM,
                             temperature=0.2, max_tokens=1500)
        data = parse_json_response(raw)
        clean = lambda key, n: [str(x).strip() for x in data.get(key, []) if str(x).strip()][:n]
        return {"acceptance_criteria": clean("acceptance_criteria", 6), "plan": clean("plan", 7),
                "risks": clean("risks", 4), "model": active_model()}
    except Exception as e:
        logger.warning(f"AI plan for {ticket['ticket_id']} unavailable: {e}")
        return None
