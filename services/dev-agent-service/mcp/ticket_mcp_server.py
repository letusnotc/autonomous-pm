#!/usr/bin/env python3
"""
ticket_mcp_server.py – MCP server exposing the Autonomous PM ticket board to
coding agents (Claude Code, Codex, Cursor).

Speaks the Model Context Protocol over stdio (newline-delimited JSON-RPC 2.0)
using only the Python standard library, so any Python 3.8+ can run it with no
installs.

Environment:
  TICKET_SERVICE_URL  Ticket Service base URL (default http://localhost:3001)
  APM_TICKET_ID       Ticket this session is about; tools default to it
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

SERVER_NAME    = "autonomous-pm"
SERVER_VERSION = "1.0.0"
SUPPORTED_PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"]

TICKET_SERVICE_URL = os.environ.get("TICKET_SERVICE_URL", "http://localhost:3001").rstrip("/")
DEFAULT_TICKET     = os.environ.get("APM_TICKET_ID") or None
AGENT_STATUSES     = ["In Progress", "In Review", "Blocked"]
ACTOR              = "coding-agent"


def log(msg):
    print(f"[{SERVER_NAME}] {msg}", file=sys.stderr, flush=True)


# ── Ticket Service client ────────────────────────────────────────────────────

class ToolError(Exception):
    pass


def api(method, path, body=None, params=None):
    url = TICKET_SERVICE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, "")})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("detail", detail)
        except ValueError:
            pass
        raise ToolError(f"Ticket Service returned {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise ToolError(f"Cannot reach the Ticket Service at {TICKET_SERVICE_URL}: {e.reason}")


def ticket_arg(args):
    tid = args.get("ticket_id") or DEFAULT_TICKET
    if not tid:
        raise ToolError("ticket_id is required (no default ticket for this session)")
    tid = str(tid).strip().upper()
    return tid if tid.startswith("APM-") else f"APM-{tid}"


# ── Tools ────────────────────────────────────────────────────────────────────

def _ticket_prop(required=False):
    desc = "Ticket ID like APM-12."
    if DEFAULT_TICKET:
        desc += f" Defaults to {DEFAULT_TICKET}, the ticket this session is about."
    return {"ticket_id": {"type": "string", "description": desc}}


def tool_get_ticket(args):
    return api("GET", f"/tickets/{ticket_arg(args)}")


def tool_get_ticket_timeline(args):
    events = api("GET", f"/tickets/{ticket_arg(args)}/events")
    return [{"when": e["created_at"], "who": e.get("actor"), "what": e["summary"],
             "reason": (e.get("data") or {}).get("reason")} for e in events]


def tool_find_similar_tickets(args):
    return api("GET", f"/tickets/{ticket_arg(args)}/similar", params={"limit": 5, "min_score": 0.2})


def tool_list_subtasks(args):
    tickets = api("GET", "/tickets", params={"parent": ticket_arg(args), "page_size": 100})["tickets"]
    return [{"ticket_id": t["ticket_id"], "title": t["title"], "status": t["status"],
             "assignee": t.get("assignee")} for t in tickets]


def tool_search_tickets(args):
    limit = max(1, min(int(args.get("limit") or 10), 50))
    res = api("GET", "/tickets", params={"search": args.get("query"), "status": args.get("status"),
                                         "page_size": limit})
    return [{"ticket_id": t["ticket_id"], "title": t["title"], "status": t["status"],
             "priority": t["priority"], "assignee": t.get("assignee")} for t in res["tickets"]]


def tool_add_progress_note(args):
    note = (args.get("note") or "").strip()
    if not note:
        raise ToolError("note must not be empty")
    tid = ticket_arg(args)
    api("POST", f"/tickets/{tid}/events", {"kind": "note", "actor": ACTOR, "summary": note[:2000]})
    return {"ok": True, "ticket_id": tid, "note": note}


def tool_update_ticket_status(args):
    status = args.get("status")
    if status not in AGENT_STATUSES:
        raise ToolError(f"status must be one of {AGENT_STATUSES}. Done/Closed are set when the PR merges.")
    tid = ticket_arg(args)
    ticket = api("PUT", f"/tickets/{tid}", {"status": status, "actor": ACTOR, "reason": args.get("note")})
    return {"ok": True, "ticket_id": tid, "status": ticket["status"]}


TOOLS = {
    "get_ticket": (tool_get_ticket, "Get a ticket's full details (title, description, status, priority, links).",
                   {}, []),
    "get_ticket_timeline": (tool_get_ticket_timeline,
                            "Activity history of a ticket, including the reasoning behind AI priority changes.",
                            {}, []),
    "find_similar_tickets": (tool_find_similar_tickets,
                             "Tickets with similar wording – check them for earlier fixes or overlapping work.",
                             {}, []),
    "list_subtasks": (tool_list_subtasks, "Sub-tasks of a ticket with their status.", {}, []),
    "search_tickets": (tool_search_tickets, "Search the ticket board by text and/or status.", {
        "query":  {"type": "string", "description": "Text to search in titles and descriptions"},
        "status": {"type": "string", "enum": ["Open", "In Progress", "In Review", "Done", "Closed", "Blocked"]},
        "limit":  {"type": "integer", "minimum": 1, "maximum": 50},
    }, []),
    "add_progress_note": (tool_add_progress_note,
                          "Log a short progress note on the ticket's timeline (visible to the team).",
                          {"note": {"type": "string", "description": "What was done or decided"}}, ["note"]),
    "update_ticket_status": (tool_update_ticket_status,
                             "Move the ticket to In Progress, In Review (PR ready) or Blocked.", {
        "status": {"type": "string", "enum": AGENT_STATUSES},
        "note":   {"type": "string", "description": "Why – shown on the timeline"},
    }, ["status"]),
}


def tool_list():
    tools = []
    for name, (_, description, props, required) in TOOLS.items():
        schema = {"type": "object", "properties": {**_ticket_prop(), **props}}
        if required:
            schema["required"] = required
        tools.append({"name": name, "description": description, "inputSchema": schema})
    return tools


def call_tool(name, args):
    if name not in TOOLS:
        raise KeyError(name)
    try:
        result = TOOLS[name][0](args or {})
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}], "isError": False}
    except ToolError as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}


# ── JSON-RPC / MCP plumbing ──────────────────────────────────────────────────

def handle(msg):
    method, msg_id, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if msg_id is None:            # notification (e.g. notifications/initialized) – no reply
        return None
    if method == "initialize":
        requested = params.get("protocolVersion")
        return {"protocolVersion": requested if requested in SUPPORTED_PROTOCOLS else SUPPORTED_PROTOCOLS[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "Ticket board for this repository. Use get_ticket first; log progress with "
                                "add_progress_note and move status with update_ticket_status."}
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": tool_list()}
    if method == "tools/call":
        try:
            return call_tool(params.get("name"), params.get("arguments"))
        except KeyError:
            raise RpcError(-32602, f"Unknown tool: {params.get('name')}")
    raise RpcError(-32601, f"Method not found: {method}")


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def main():
    for stream in (sys.stdin, sys.stdout):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    log(f"ready (ticket service {TICKET_SERVICE_URL}, default ticket {DEFAULT_TICKET or 'none'})")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            try:
                result = handle(msg)
                if result is None:
                    continue
                reply = {"jsonrpc": "2.0", "id": msg.get("id"), "result": result}
            except RpcError as e:
                reply = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": e.code, "message": str(e)}}
            except Exception as e:  # never crash the agent's session
                log(f"internal error: {e!r}")
                reply = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": str(e)}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
