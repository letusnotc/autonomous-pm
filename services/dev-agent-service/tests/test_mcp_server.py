"""The MCP server, driven over stdio exactly as a coding agent would."""
import json
import os
import subprocess
import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "mcp" / "ticket_mcp_server.py"


def converse(*messages, ticket_id="APM-7"):
    """Send JSON-RPC messages to a fresh server process; return replies keyed by id."""
    env = {**os.environ, "TICKET_SERVICE_URL": "http://127.0.0.1:9", "APM_TICKET_ID": ticket_id}
    proc = subprocess.run(
        [sys.executable, str(SERVER)],
        input="\n".join(json.dumps(m) for m in messages) + "\n",
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
    )
    return {r["id"]: r for r in map(json.loads, proc.stdout.splitlines())}


def call(msg_id, name, arguments):
    return {"jsonrpc": "2.0", "id": msg_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


def test_handshake_and_tool_listing():
    replies = converse(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},   # notification: no reply
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "ping"},
    )
    assert set(replies) == {1, 2, 3}
    init = replies[1]["result"]
    assert init["protocolVersion"] == "2025-06-18"
    assert init["serverInfo"]["name"] == "autonomous-pm"
    tools = {t["name"]: t for t in replies[2]["result"]["tools"]}
    assert set(tools) == {"get_ticket", "get_ticket_timeline", "find_similar_tickets", "list_subtasks",
                          "search_tickets", "add_progress_note", "update_ticket_status"}
    assert "Defaults to APM-7" in tools["get_ticket"]["inputSchema"]["properties"]["ticket_id"]["description"]
    assert tools["update_ticket_status"]["inputSchema"]["required"] == ["status"]


def test_unknown_protocol_version_falls_back_to_a_supported_one():
    replies = converse({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
    assert replies[1]["result"]["protocolVersion"] == "2025-06-18"


def test_agents_cannot_close_tickets():
    replies = converse(call(1, "update_ticket_status", {"status": "Done"}))
    result = replies[1]["result"]
    assert result["isError"] is True
    assert "Done/Closed are set when the PR merges" in result["content"][0]["text"]


def test_errors_are_reported_not_crashed():
    replies = converse(
        call(1, "add_progress_note", {"note": "   "}),
        call(2, "get_ticket", {}),                        # ticket service unreachable in this test
        call(3, "no_such_tool", {}),
        {"jsonrpc": "2.0", "id": 4, "method": "resources/read"},
    )
    assert replies[1]["result"]["isError"] and "must not be empty" in replies[1]["result"]["content"][0]["text"]
    assert replies[2]["result"]["isError"] and "Cannot reach the Ticket Service" in replies[2]["result"]["content"][0]["text"]
    assert replies[3]["error"]["code"] == -32602
    assert replies[4]["error"]["code"] == -32601
