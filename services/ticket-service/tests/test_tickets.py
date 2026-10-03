"""
API tests for the Ticket Service: CRUD, timeline, links, duplicates, sub-tasks.
"""


async def test_create_and_get_ticket(client, create, events):
    t = await create("Login page crashes on Safari", ticket_type="bug", reported_by="alice", source="slack")
    assert t["ticket_id"] == f"APM-{t['id']}"
    assert (t["status"], t["priority"], t["parent_id"], t["duplicate_of"]) == ("Open", "Medium", None, None)

    resp = await client.get(f"/tickets/{t['ticket_id']}")
    assert resp.status_code == 200 and resp.json()["title"] == "Login page crashes on Safari"

    timeline = await events(t["ticket_id"])
    assert timeline[0]["kind"] == "created"
    assert timeline[0]["summary"] == "Created by alice via slack"


async def test_invalid_values_are_rejected(client, create):
    resp = await client.post("/tickets", json={"title": "x", "priority": "Urgent"})
    assert resp.status_code == 422
    t = await create("Valid ticket")
    resp = await client.put(f"/tickets/{t['ticket_id']}", json={"status": "Finished"})
    assert resp.status_code == 422
    assert (await client.get("/tickets/APM-9999")).status_code == 404


async def test_update_records_who_and_why(client, create, events):
    t = await create("Payment API returns 500")
    tid = t["ticket_id"]

    await client.put(f"/tickets/{tid}", json={
        "priority": "Critical", "priority_score": 90,
        "actor": "priority-agent", "reason": "Checkout is failing for paying users.",
    })
    await client.put(f"/tickets/{tid}", json={"status": "In Progress", "actor": "github",
                                              "reason": "PR #12 opened"})
    await client.put(f"/tickets/{tid}", json={"assignee": "bob"})

    timeline = await events(tid)
    kinds = [e["kind"] for e in timeline]
    assert kinds == ["created", "priority_changed", "status_changed", "assigned"]

    prio = timeline[1]
    assert prio["actor"] == "priority-agent"
    assert prio["summary"] == "Priority Medium → Critical (score 90)"
    assert prio["data"]["reason"] == "Checkout is failing for paying users."
    assert timeline[2]["summary"] == "Status Open → In Progress"
    assert timeline[2]["actor"] == "github"
    assert timeline[3]["summary"] == "Assigned to bob"


async def test_small_rescores_do_not_flood_the_timeline(client, create, events):
    t = await create("Rescore me")
    tid = t["ticket_id"]
    await client.put(f"/tickets/{tid}", json={"priority_score": 50, "actor": "priority-agent"})
    await client.put(f"/tickets/{tid}", json={"priority_score": 55, "actor": "priority-agent"})   # < 10 apart
    await client.put(f"/tickets/{tid}", json={"priority_score": 70, "actor": "priority-agent"})   # >= 10 apart
    scores = [e["summary"] for e in await events(tid) if e["kind"] == "priority_changed"]
    assert scores == ["Priority score – → 50", "Priority score 55 → 70"]


async def test_new_ticket_is_flagged_as_possible_duplicate(create, events):
    original = await create("Login page crashes on Safari",
                            description="Users on Safari 17 get a blank screen after submitting credentials")
    unrelated = await create("Add dark mode to settings page")
    dup = await create("Safari login page crash after entering credentials",
                       description="blank screen on Safari 17 when logging in")

    dup_events = [e for e in await events(dup["ticket_id"]) if e["kind"] == "possible_duplicates"]
    assert len(dup_events) == 1
    matches = [m["ticket_id"] for m in dup_events[0]["data"]["matches"]]
    assert matches[0] == original["ticket_id"]
    assert unrelated["ticket_id"] not in matches
    assert dup_events[0]["actor"] == "duplicate-detector"

    assert not [e for e in await events(unrelated["ticket_id"]) if e["kind"] == "possible_duplicates"]


async def test_similar_to_draft_text(client, create):
    payment = await create("Payment API returning 500 errors in production")
    await create("Add dark mode to settings")
    resp = await client.post("/tickets/similar", json={"title": "checkout payment returns 500"})
    assert resp.status_code == 200
    results = resp.json()
    assert [r["ticket_id"] for r in results] == [payment["ticket_id"]]
    assert 0 < results[0]["score"] <= 1


async def test_duplicate_link_set_and_clear(client, create, events):
    a = await create("Original issue")
    b = await create("Same issue reported again")
    resp = await client.put(f"/tickets/{b['ticket_id']}",
                            json={"duplicate_of": a["ticket_id"], "status": "Closed"})
    assert resp.json()["duplicate_of"] == a["ticket_id"]

    resp = await client.put(f"/tickets/{b['ticket_id']}", json={"duplicate_of": ""})
    assert resp.json()["duplicate_of"] is None

    linked = [e["summary"] for e in await events(b["ticket_id"]) if e["kind"] == "linked"]
    assert linked == [f"Marked as duplicate of {a['ticket_id']}", f"No longer a duplicate of {a['ticket_id']}"]


async def test_invalid_links_are_rejected(client, create):
    t = await create("Linkable")
    tid = t["ticket_id"]
    resp = await client.put(f"/tickets/{tid}", json={"duplicate_of": tid})
    assert resp.status_code == 422 and "itself" in resp.json()["detail"]
    resp = await client.put(f"/tickets/{tid}", json={"parent_id": "APM-9999"})
    assert resp.status_code == 422 and "does not exist" in resp.json()["detail"]
    resp = await client.post("/tickets", json={"title": "orphan", "parent_id": "APM-9999"})
    assert resp.status_code == 422


async def test_subtasks(client, create, events):
    parent = await create("Migrate auth tokens to rotating refresh flow", priority="High")
    pid = parent["ticket_id"]
    resp = await client.post(f"/tickets/{pid}/subtasks", json={
        "actor": "breakdown-agent",
        "subtasks": [{"title": "Add refresh token table"}, {"title": "Rotate refresh token on use"}],
    })
    assert resp.status_code == 201
    children = resp.json()
    assert [c["parent_id"] for c in children] == [pid, pid]
    assert all(c["priority"] == "High" for c in children)          # inherited from the parent

    listed = (await client.get("/tickets", params={"parent": pid})).json()
    assert sorted(t["ticket_id"] for t in listed["tickets"]) == sorted(c["ticket_id"] for c in children)

    parent_events = await events(pid)
    assert parent_events[-1]["kind"] == "subtasks_created"
    assert parent_events[-1]["actor"] == "breakdown-agent"

    # Sub-tasks are related to their parent by design – never reported as duplicates
    child_events = await events(children[0]["ticket_id"])
    assert "possible_duplicates" not in [e["kind"] for e in child_events]
    similar = (await client.get(f"/tickets/{pid}/similar", params={"min_score": 0})).json()
    assert not {s["ticket_id"] for s in similar} & {c["ticket_id"] for c in children}


async def test_delete_clears_links_and_timeline(client, create):
    parent = await create("Parent")
    child = (await client.post(f"/tickets/{parent['ticket_id']}/subtasks",
                               json={"subtasks": [{"title": "Child"}]})).json()[0]
    dup = await create("Dup of parent")
    await client.put(f"/tickets/{dup['ticket_id']}", json={"duplicate_of": parent["ticket_id"]})

    resp = await client.delete(f"/tickets/{parent['ticket_id']}")
    assert resp.json() == {"deleted": True, "ticket_id": parent["ticket_id"]}
    assert (await client.get(f"/tickets/{child['ticket_id']}")).json()["parent_id"] is None
    assert (await client.get(f"/tickets/{dup['ticket_id']}")).json()["duplicate_of"] is None
    assert (await client.get(f"/tickets/{parent['ticket_id']}/events")).status_code == 404


async def test_ticket_ids_are_never_reused(client, create):
    first = await create("First")
    await client.delete(f"/tickets/{first['ticket_id']}")
    second = await create("Second")
    assert second["id"] > first["id"]


async def test_notes_and_invalid_event_kinds(client, create, events):
    t = await create("Noted")
    resp = await client.post(f"/tickets/{t['ticket_id']}/events",
                             json={"kind": "note", "actor": "coding-agent", "summary": "Found the cause"})
    assert resp.status_code == 201 and resp.json()["summary"] == "Found the cause"
    resp = await client.post(f"/tickets/{t['ticket_id']}/events", json={"kind": "bogus", "summary": "x"})
    assert resp.status_code == 422


async def test_stats(client, create):
    a = await create("One", priority="Critical")
    await create("Two")
    await client.put(f"/tickets/{a['ticket_id']}", json={"status": "Done"})
    stats = (await client.get("/stats")).json()
    assert stats["total_tickets"] == 2
    assert stats["completed_tickets"] == 1
    assert stats["critical_tickets"] == 1
    assert stats["by_status"] == {"Done": 1, "Open": 1}
