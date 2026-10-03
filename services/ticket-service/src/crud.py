"""
crud.py – Database operations supporting both MongoDB and SQL backends.
The router layer doesn't know or care which backend is active.

Every mutation also appends to the ticket's activity timeline (ticket_events).
"""
import json
import os
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import HTTPException

from .schemas import (
    TicketCreate, TicketUpdate, TicketEventCreate, SimilarQuery, SubtaskBatch,
    VALID_STATUSES, VALID_PRIORITIES, VALID_TYPES, EVENT_KINDS,
)
from . import similarity

DATABASE_BACKEND = os.getenv("DATABASE_BACKEND", "sql").lower()


def _validate(ticket_type=None, priority=None, status=None):
    if ticket_type and ticket_type not in VALID_TYPES:
        raise HTTPException(422, f"Invalid ticket_type. Must be one of: {sorted(VALID_TYPES)}")
    if priority and priority not in VALID_PRIORITIES:
        raise HTTPException(422, f"Invalid priority. Must be one of: {sorted(VALID_PRIORITIES)}")
    if status and status not in VALID_STATUSES:
        raise HTTPException(422, f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}")


def _fmt_id(raw: Optional[int]) -> Optional[str]:
    return f"APM-{raw}" if raw is not None else None


def _parse_link(value: Optional[str], self_id: Optional[int] = None) -> Optional[int]:
    """'APM-3' → 3, '' → None (clear). Rejects self-links."""
    if value is None or value == "":
        return None
    raw = _parse_id(value)
    if self_id is not None and raw == self_id:
        raise HTTPException(422, "A ticket cannot be linked to itself")
    return raw


# ─────────────────────────────────────────────────────────────────────────────
# Timeline – backend-independent description of what changed
# ─────────────────────────────────────────────────────────────────────────────

def _describe_changes(before: dict, after: dict, reason: Optional[str]) -> List[dict]:
    """Turn a before/after pair of ticket dicts into timeline events."""
    events = []
    extra = {"reason": reason} if reason else {}

    if before["status"] != after["status"]:
        events.append({
            "kind": "status_changed",
            "summary": f"Status {before['status']} → {after['status']}",
            "data": {"from": before["status"], "to": after["status"], **extra},
        })

    prio_changed  = before["priority"] != after["priority"]
    old_score, new_score = before["priority_score"], after["priority_score"]
    # Score-only changes are recorded when meaningful, so hourly re-scoring
    # doesn't flood the timeline.
    score_changed = new_score is not None and (old_score is None or abs(new_score - old_score) >= 10)
    if prio_changed or score_changed:
        score_txt = f" (score {new_score})" if new_score is not None else ""
        summary = (f"Priority {before['priority']} → {after['priority']}{score_txt}" if prio_changed
                   else f"Priority score {old_score if old_score is not None else '–'} → {new_score}")
        events.append({
            "kind": "priority_changed",
            "summary": summary,
            "data": {"from": before["priority"], "to": after["priority"],
                     "score_from": old_score, "score_to": new_score, **extra},
        })

    if before["assignee"] != after["assignee"]:
        summary = f"Assigned to {after['assignee']}" if after["assignee"] else "Unassigned"
        events.append({"kind": "assigned", "summary": summary,
                       "data": {"from": before["assignee"], "to": after["assignee"], **extra}})

    edited = [f for f in ("title", "description", "ticket_type", "reported_by") if before[f] != after[f]]
    if edited:
        labels = {"ticket_type": "type", "reported_by": "reporter"}
        events.append({"kind": "edited",
                       "summary": "Edited " + ", ".join(labels.get(f, f) for f in edited),
                       "data": {"fields": edited, **extra}})

    for field, verb_set, verb_clear in (
        ("parent_id",    "Moved under {}",          "Removed from parent {}"),
        ("duplicate_of", "Marked as duplicate of {}", "No longer a duplicate of {}"),
    ):
        if before[field] != after[field]:
            summary = verb_set.format(after[field]) if after[field] else verb_clear.format(before[field])
            events.append({"kind": "linked", "summary": summary,
                           "data": {"field": field, "from": before[field], "to": after[field], **extra}})
    return events


def _creation_events(ticket: dict) -> List[dict]:
    via = ticket.get("source") or "api"
    who = f" by {ticket['reported_by']}" if ticket.get("reported_by") else ""
    summary = f"Created{who} via {via}"
    if ticket.get("parent_id"):
        summary += f" as a sub-task of {ticket['parent_id']}"
    return [{"kind": "created", "summary": summary,
             "data": {"source": via, "priority": ticket["priority"], "ticket_type": ticket["ticket_type"]}}]


def _duplicate_event(ticket: dict, all_tickets: List[dict]) -> Optional[dict]:
    """Flag likely duplicates of a newly created ticket (skipped for sub-tasks)."""
    if ticket.get("parent_id"):
        return None
    matches = _rank_similar(ticket["title"], ticket.get("description"), all_tickets,
                            exclude={ticket["ticket_id"]}, limit=3,
                            min_score=similarity.DUPLICATE_THRESHOLD)
    if not matches:
        return None
    ids = ", ".join(f"{m['ticket_id']} ({round(m['score'] * 100)}%)" for m in matches)
    return {"kind": "possible_duplicates", "summary": f"Possible duplicate of {ids}",
            "data": {"matches": matches}}


def _rank_similar(title, description, tickets: List[dict], exclude=frozenset(),
                  limit=5, min_score=0.2) -> List[dict]:
    by_id = {t["ticket_id"]: t for t in tickets if t["ticket_id"] not in exclude}
    corpus = [(tid, similarity.ticket_tokens(t["title"], t.get("description"))) for tid, t in by_id.items()]
    ranked = similarity.rank(similarity.ticket_tokens(title, description), corpus, limit, min_score)
    return [{
        "ticket_id": tid, "title": by_id[tid]["title"], "status": by_id[tid]["status"],
        "priority": by_id[tid]["priority"], "score": score,
    } for tid, score in ranked]


# ─────────────────────────────────────────────────────────────────────────────
# MongoDB implementation
# ─────────────────────────────────────────────────────────────────────────────

def _mongo_to_dict(doc: dict) -> dict:
    """Convert a MongoDB document to the canonical response dict."""
    return {
        "id":               doc["id"],
        "ticket_id":        f"APM-{doc['id']}",
        "title":            doc["title"],
        "description":      doc.get("description"),
        "ticket_type":      doc.get("ticket_type", "task"),
        "status":           doc.get("status", "Open"),
        "priority":         doc.get("priority", "Medium"),
        "priority_score":   doc.get("priority_score"),
        "assignee":         doc.get("assignee"),
        "reported_by":      doc.get("reported_by"),
        "source":           doc.get("source"),
        "channel":          doc.get("channel"),
        "slack_message_ts": doc.get("slack_message_ts"),
        "parent_id":        _fmt_id(doc.get("parent_id")),
        "duplicate_of":     _fmt_id(doc.get("duplicate_of")),
        "created_at":       doc.get("created_at", datetime.now(timezone.utc)),
        "updated_at":       doc.get("updated_at", datetime.now(timezone.utc)),
    }


async def _mongo_next_id(db, counter: str = "ticket_seq") -> int:
    result = await db.counters.find_one_and_update(
        {"_id": counter},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return result["seq"]


async def _mongo_resolve(db, ticket_id: str):
    raw_id = _parse_id(ticket_id)
    doc = await db.tickets.find_one({"id": raw_id})
    if not doc:
        raise HTTPException(404, f"Ticket '{ticket_id}' not found")
    return doc


async def _mongo_require(db, raw_id: Optional[int], label: str):
    if raw_id is not None and not await db.tickets.find_one({"id": raw_id}, {"_id": 1}):
        raise HTTPException(422, f"{label} APM-{raw_id} does not exist")


async def _mongo_add_events(db, raw_id: int, events: List[dict], actor: Optional[str]):
    for e in events:
        await db.ticket_events.insert_one({
            "id":         await _mongo_next_id(db, "event_seq"),
            "ticket_id":  raw_id,
            "kind":       e["kind"],
            "actor":      e.get("actor") or actor or "api",
            "summary":    e["summary"],
            "data":       e.get("data"),
            "created_at": datetime.now(timezone.utc),
        })


async def _mongo_all(db) -> List[dict]:
    docs = await db.tickets.find({}).to_list(length=None)
    return [_mongo_to_dict(d) for d in docs]


async def _mongo_create(db, data: TicketCreate) -> dict:
    _validate(ticket_type=data.ticket_type, priority=data.priority)
    parent = _parse_link(data.parent_id)
    await _mongo_require(db, parent, "Parent ticket")
    now = datetime.now(timezone.utc)
    seq = await _mongo_next_id(db)
    doc = {
        "id":               seq,
        "title":            data.title,
        "description":      data.description,
        "ticket_type":      data.ticket_type or "task",
        "status":           "Open",
        "priority":         data.priority or "Medium",
        "priority_score":   None,
        "assignee":         data.assignee,
        "reported_by":      data.reported_by,
        "source":           data.source or "api",
        "channel":          data.channel,
        "slack_message_ts": data.slack_message_ts,
        "parent_id":        parent,
        "duplicate_of":     None,
        "created_at":       now,
        "updated_at":       now,
    }
    await db.tickets.insert_one(doc)
    ticket = _mongo_to_dict(doc)
    events = _creation_events(ticket)
    dup = _duplicate_event(ticket, await _mongo_all(db))
    if dup:
        events.append({**dup, "actor": "duplicate-detector"})
    await _mongo_add_events(db, seq, events, data.actor or data.reported_by or data.source)
    return ticket


async def _mongo_get(db, ticket_id: str) -> dict:
    return _mongo_to_dict(await _mongo_resolve(db, ticket_id))


async def _mongo_list(db, status=None, priority=None, ticket_type=None,
                       assignee=None, search=None, parent=None, page=1, page_size=20) -> dict:
    query = {}
    if status:      query["status"]      = status
    if priority:    query["priority"]    = priority
    if ticket_type: query["ticket_type"] = ticket_type
    if assignee:    query["assignee"]    = assignee
    if parent:      query["parent_id"]   = _parse_id(parent)
    if search:
        query["$text"] = {"$search": search}

    total = await db.tickets.count_documents(query)
    cursor = db.tickets.find(query).sort("created_at", -1).skip((page - 1) * page_size).limit(page_size)
    docs = await cursor.to_list(length=page_size)
    return {
        "tickets":   [_mongo_to_dict(d) for d in docs],
        "total":     total,
        "page":      page,
        "page_size": page_size,
    }


async def _mongo_update(db, ticket_id: str, data: TicketUpdate) -> dict:
    doc = await _mongo_resolve(db, ticket_id)
    _validate(ticket_type=data.ticket_type, priority=data.priority, status=data.status)
    before = _mongo_to_dict(doc)
    updates = {"updated_at": datetime.now(timezone.utc)}
    if data.title is not None:          updates["title"]          = data.title
    if data.description is not None:    updates["description"]    = data.description
    if data.ticket_type is not None:    updates["ticket_type"]    = data.ticket_type
    if data.status is not None:         updates["status"]         = data.status
    if data.priority is not None:       updates["priority"]       = data.priority
    if data.priority_score is not None: updates["priority_score"] = data.priority_score
    if data.assignee is not None:       updates["assignee"]       = data.assignee
    if data.reported_by is not None:    updates["reported_by"]    = data.reported_by
    for field in ("parent_id", "duplicate_of"):
        value = getattr(data, field)
        if value is not None:
            raw = _parse_link(value, self_id=doc["id"])
            await _mongo_require(db, raw, "Linked ticket")
            updates[field] = raw
    await db.tickets.update_one({"id": doc["id"]}, {"$set": updates})
    after = _mongo_to_dict(await db.tickets.find_one({"id": doc["id"]}))
    await _mongo_add_events(db, doc["id"], _describe_changes(before, after, data.reason), data.actor)
    return after


async def _mongo_assign(db, ticket_id: str, assignee: str) -> dict:
    return await _mongo_update(db, ticket_id, TicketUpdate(assignee=assignee))


async def _mongo_delete(db, ticket_id: str) -> dict:
    doc = await _mongo_resolve(db, ticket_id)
    await db.tickets.delete_one({"id": doc["id"]})
    await db.ticket_events.delete_many({"ticket_id": doc["id"]})
    await db.tickets.update_many({"parent_id": doc["id"]},    {"$set": {"parent_id": None}})
    await db.tickets.update_many({"duplicate_of": doc["id"]}, {"$set": {"duplicate_of": None}})
    return {"deleted": True, "ticket_id": ticket_id}


async def _mongo_events(db, ticket_id: str) -> List[dict]:
    doc = await _mongo_resolve(db, ticket_id)
    cursor = db.ticket_events.find({"ticket_id": doc["id"]}).sort([("created_at", 1), ("id", 1)])
    return [{
        "id": e["id"], "ticket_id": _fmt_id(e["ticket_id"]), "kind": e["kind"], "actor": e.get("actor"),
        "summary": e["summary"], "data": e.get("data"), "created_at": e["created_at"],
    } for e in await cursor.to_list(length=None)]


async def _mongo_add_event(db, ticket_id: str, data: TicketEventCreate) -> dict:
    doc = await _mongo_resolve(db, ticket_id)
    await _mongo_add_events(db, doc["id"], [data.model_dump()], data.actor)
    return (await _mongo_events(db, ticket_id))[-1]


async def _mongo_stats(db) -> dict:
    docs = await db.tickets.find({}).to_list(length=None)
    by_status: dict   = {}
    by_priority: dict = {}
    active_statuses   = {"Open", "In Progress", "In Review"}
    done_statuses     = {"Done", "Closed"}
    for d in docs:
        s = d.get("status",   "Open")
        p = d.get("priority", "Medium")
        by_status[s]   = by_status.get(s, 0)   + 1
        by_priority[p] = by_priority.get(p, 0) + 1
    total     = len(docs)
    active    = sum(v for k, v in by_status.items() if k in active_statuses)
    completed = sum(v for k, v in by_status.items() if k in done_statuses)
    blocked   = by_status.get("Blocked", 0)
    critical  = by_priority.get("Critical", 0)
    return {
        "total_tickets":     total,
        "active_tickets":    active,
        "completed_tickets": completed,
        "blocked_tickets":   blocked,
        "critical_tickets":  critical,
        "success_rate":      round(completed / total * 100, 1) if total > 0 else 0.0,
        "by_status":         by_status,
        "by_priority":       by_priority,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SQL implementation (SQLAlchemy)
# ─────────────────────────────────────────────────────────────────────────────

def _sql_to_dict(ticket) -> dict:
    return {
        "id":               ticket.id,
        "ticket_id":        ticket.ticket_id,
        "title":            ticket.title,
        "description":      ticket.description,
        "ticket_type":      ticket.ticket_type,
        "status":           ticket.status,
        "priority":         ticket.priority,
        "priority_score":   ticket.priority_score,
        "assignee":         ticket.assignee,
        "reported_by":      ticket.reported_by,
        "source":           ticket.source,
        "channel":          ticket.channel,
        "slack_message_ts": ticket.slack_message_ts,
        "parent_id":        _fmt_id(ticket.parent_id),
        "duplicate_of":     _fmt_id(ticket.duplicate_of),
        "created_at":       ticket.created_at,
        "updated_at":       ticket.updated_at,
    }


async def _sql_resolve(db, ticket_id: str):
    from sqlalchemy import select
    from .models import Ticket
    raw_id = _parse_id(ticket_id)
    result = await db.execute(select(Ticket).where(Ticket.id == raw_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(404, f"Ticket '{ticket_id}' not found")
    return ticket


async def _sql_require(db, raw_id: Optional[int], label: str):
    from .models import Ticket
    if raw_id is not None and await db.get(Ticket, raw_id) is None:
        raise HTTPException(422, f"{label} APM-{raw_id} does not exist")


async def _sql_add_events(db, raw_id: int, events: List[dict], actor: Optional[str]):
    from .models import TicketEvent
    for e in events:
        db.add(TicketEvent(
            ticket_id=raw_id, kind=e["kind"], actor=e.get("actor") or actor or "api",
            summary=e["summary"], data=json.dumps(e["data"], default=str) if e.get("data") else None,
        ))
    await db.flush()


async def _sql_all(db) -> List[dict]:
    from sqlalchemy import select
    from .models import Ticket
    result = await db.execute(select(Ticket))
    return [_sql_to_dict(t) for t in result.scalars().all()]


async def _sql_create(db, data: TicketCreate) -> dict:
    from .models import Ticket
    _validate(ticket_type=data.ticket_type, priority=data.priority)
    parent = _parse_link(data.parent_id)
    await _sql_require(db, parent, "Parent ticket")
    ticket = Ticket(
        title=data.title, description=data.description,
        ticket_type=data.ticket_type or "task", priority=data.priority or "Medium",
        assignee=data.assignee, reported_by=data.reported_by,
        source=data.source or "api", channel=data.channel,
        slack_message_ts=data.slack_message_ts, parent_id=parent,
    )
    db.add(ticket)
    await db.flush()
    await db.refresh(ticket)
    result = _sql_to_dict(ticket)
    events = _creation_events(result)
    dup = _duplicate_event(result, await _sql_all(db))
    if dup:
        events.append({**dup, "actor": "duplicate-detector"})
    await _sql_add_events(db, ticket.id, events, data.actor or data.reported_by or data.source)
    return result


async def _sql_get(db, ticket_id: str) -> dict:
    return _sql_to_dict(await _sql_resolve(db, ticket_id))


async def _sql_list(db, status=None, priority=None, ticket_type=None,
                     assignee=None, search=None, parent=None, page=1, page_size=20) -> dict:
    from sqlalchemy import select, func, or_
    from .models import Ticket
    stmt = select(Ticket)
    if status:      stmt = stmt.where(Ticket.status == status)
    if priority:    stmt = stmt.where(Ticket.priority == priority)
    if ticket_type: stmt = stmt.where(Ticket.ticket_type == ticket_type)
    if assignee:    stmt = stmt.where(Ticket.assignee == assignee)
    if parent:      stmt = stmt.where(Ticket.parent_id == _parse_id(parent))
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Ticket.title.ilike(like), Ticket.description.ilike(like)))
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar_one()
    stmt = stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    tickets = result.scalars().all()
    return {"tickets": [_sql_to_dict(t) for t in tickets], "total": total, "page": page, "page_size": page_size}


async def _sql_update(db, ticket_id: str, data: TicketUpdate) -> dict:
    ticket = await _sql_resolve(db, ticket_id)
    _validate(ticket_type=data.ticket_type, priority=data.priority, status=data.status)
    before = _sql_to_dict(ticket)
    if data.title is not None:          ticket.title          = data.title
    if data.description is not None:    ticket.description    = data.description
    if data.ticket_type is not None:    ticket.ticket_type    = data.ticket_type
    if data.status is not None:         ticket.status         = data.status
    if data.priority is not None:       ticket.priority       = data.priority
    if data.priority_score is not None: ticket.priority_score = data.priority_score
    if data.assignee is not None:       ticket.assignee       = data.assignee
    if data.reported_by is not None:    ticket.reported_by    = data.reported_by
    for field in ("parent_id", "duplicate_of"):
        value = getattr(data, field)
        if value is not None:
            raw = _parse_link(value, self_id=ticket.id)
            await _sql_require(db, raw, "Linked ticket")
            setattr(ticket, field, raw)
    await db.flush()
    await db.refresh(ticket)
    after = _sql_to_dict(ticket)
    await _sql_add_events(db, ticket.id, _describe_changes(before, after, data.reason), data.actor)
    return after


async def _sql_assign(db, ticket_id: str, assignee: str) -> dict:
    return await _sql_update(db, ticket_id, TicketUpdate(assignee=assignee))


async def _sql_delete(db, ticket_id: str) -> dict:
    from sqlalchemy import delete, update
    from .models import Ticket, TicketEvent
    ticket = await _sql_resolve(db, ticket_id)
    raw_id = ticket.id
    await db.delete(ticket)
    await db.execute(delete(TicketEvent).where(TicketEvent.ticket_id == raw_id))
    await db.execute(update(Ticket).where(Ticket.parent_id == raw_id).values(parent_id=None))
    await db.execute(update(Ticket).where(Ticket.duplicate_of == raw_id).values(duplicate_of=None))
    return {"deleted": True, "ticket_id": ticket_id}


def _sql_event_dict(e) -> dict:
    return {
        "id": e.id, "ticket_id": _fmt_id(e.ticket_id), "kind": e.kind, "actor": e.actor,
        "summary": e.summary, "data": json.loads(e.data) if e.data else None, "created_at": e.created_at,
    }


async def _sql_events(db, ticket_id: str) -> List[dict]:
    from sqlalchemy import select
    from .models import TicketEvent
    ticket = await _sql_resolve(db, ticket_id)
    result = await db.execute(
        select(TicketEvent).where(TicketEvent.ticket_id == ticket.id)
        .order_by(TicketEvent.created_at, TicketEvent.id)
    )
    return [_sql_event_dict(e) for e in result.scalars().all()]


async def _sql_add_event(db, ticket_id: str, data: TicketEventCreate) -> dict:
    ticket = await _sql_resolve(db, ticket_id)
    await _sql_add_events(db, ticket.id, [data.model_dump()], data.actor)
    return (await _sql_events(db, ticket_id))[-1]


async def _sql_stats(db) -> dict:
    from sqlalchemy import select
    from .models import Ticket
    result = await db.execute(select(Ticket))
    tickets = result.scalars().all()
    by_status: dict = {}
    by_priority: dict = {}
    active_statuses = {"Open", "In Progress", "In Review"}
    done_statuses   = {"Done", "Closed"}
    for t in tickets:
        by_status[t.status]     = by_status.get(t.status, 0)     + 1
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
    total     = len(tickets)
    active    = sum(v for k, v in by_status.items() if k in active_statuses)
    completed = sum(v for k, v in by_status.items() if k in done_statuses)
    return {
        "total_tickets": total, "active_tickets": active,
        "completed_tickets": completed, "blocked_tickets": by_status.get("Blocked", 0),
        "critical_tickets": by_priority.get("Critical", 0),
        "success_rate": round(completed / total * 100, 1) if total > 0 else 0.0,
        "by_status": by_status, "by_priority": by_priority,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public API — router calls these; backend is chosen automatically
# ─────────────────────────────────────────────────────────────────────────────

def _parse_id(ticket_id: str) -> int:
    try:
        if isinstance(ticket_id, str) and "-" in ticket_id:
            return int(ticket_id.split("-", 1)[1])
        return int(ticket_id)
    except (ValueError, IndexError):
        raise HTTPException(422, f"Invalid ticket ID format: '{ticket_id}'")


def _mongo() -> bool:
    return DATABASE_BACKEND == "mongo"


async def create_ticket(db, data: TicketCreate) -> dict:
    return await (_mongo_create if _mongo() else _sql_create)(db, data)

async def get_ticket(db, ticket_id: str) -> dict:
    return await (_mongo_get if _mongo() else _sql_get)(db, ticket_id)

async def list_tickets(db, status=None, priority=None, ticket_type=None,
                        assignee=None, search=None, parent=None, page=1, page_size=20) -> dict:
    fn = _mongo_list if _mongo() else _sql_list
    return await fn(db, status, priority, ticket_type, assignee, search, parent, page, page_size)

async def update_ticket(db, ticket_id: str, data: TicketUpdate) -> dict:
    return await (_mongo_update if _mongo() else _sql_update)(db, ticket_id, data)

async def assign_ticket(db, ticket_id: str, assignee: str) -> dict:
    return await (_mongo_assign if _mongo() else _sql_assign)(db, ticket_id, assignee)

async def delete_ticket(db, ticket_id: str) -> dict:
    return await (_mongo_delete if _mongo() else _sql_delete)(db, ticket_id)

async def get_stats(db) -> dict:
    return await (_mongo_stats if _mongo() else _sql_stats)(db)


async def list_events(db, ticket_id: str) -> List[dict]:
    return await (_mongo_events if _mongo() else _sql_events)(db, ticket_id)

async def add_event(db, ticket_id: str, data: TicketEventCreate) -> dict:
    if data.kind not in EVENT_KINDS:
        raise HTTPException(422, f"Invalid kind. Must be one of: {sorted(EVENT_KINDS)}")
    return await (_mongo_add_event if _mongo() else _sql_add_event)(db, ticket_id, data)


async def similar_to_ticket(db, ticket_id: str, limit: int, min_score: float) -> List[dict]:
    ticket = await get_ticket(db, ticket_id)
    tickets = await (_mongo_all if _mongo() else _sql_all)(db)
    # A ticket's own sub-tasks and parent are related by design, not duplicates.
    family = {ticket["ticket_id"], ticket["parent_id"]} | {
        t["ticket_id"] for t in tickets if t["parent_id"] == ticket["ticket_id"]}
    return _rank_similar(ticket["title"], ticket["description"], tickets,
                         exclude=family, limit=limit, min_score=min_score)


async def similar_to_text(db, query: SimilarQuery) -> List[dict]:
    tickets = await (_mongo_all if _mongo() else _sql_all)(db)
    return _rank_similar(query.title, query.description, tickets,
                         limit=query.limit, min_score=query.min_score)


async def create_subtasks(db, ticket_id: str, batch: SubtaskBatch) -> List[dict]:
    parent = await get_ticket(db, ticket_id)
    created = []
    for item in batch.subtasks:
        created.append(await create_ticket(db, TicketCreate(
            title=item.title, description=item.description,
            ticket_type=item.ticket_type or "task",
            priority=item.priority or parent["priority"],
            assignee=item.assignee, source="agent" if batch.actor else "api",
            parent_id=parent["ticket_id"], actor=batch.actor,
        )))
    ids = ", ".join(t["ticket_id"] for t in created)
    await add_event(db, parent["ticket_id"], TicketEventCreate(
        kind="subtasks_created", actor=batch.actor,
        summary=f"Broken down into {len(created)} sub-tasks: {ids}",
        data={"subtasks": [t["ticket_id"] for t in created]},
    ))
    return created
