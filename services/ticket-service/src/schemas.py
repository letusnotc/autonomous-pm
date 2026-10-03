"""
schemas.py – Pydantic v2 models.
These are the CANONICAL enum values. ALL services must use these exact strings.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

# ── Canonical enumerations ────────────────────────────────────────────────────
VALID_STATUSES   = {"Open", "In Progress", "In Review", "Done", "Closed", "Blocked"}
VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}
VALID_TYPES      = {"bug", "feature", "task", "incident", "code_review", "epic", "story", "spike"}
VALID_SOURCES    = {"slack", "slack-command", "github", "api", "orchestrator", "agent"}


class TicketCreate(BaseModel):
    title:            str           = Field(..., min_length=1, max_length=200)
    description:      Optional[str] = None
    ticket_type:      Optional[str] = Field("task")
    priority:         Optional[str] = Field("Medium")
    assignee:         Optional[str] = None
    reported_by:      Optional[str] = None
    source:           Optional[str] = Field("api")
    channel:          Optional[str] = None
    slack_message_ts: Optional[str] = None
    parent_id:        Optional[str] = Field(None, description="Parent ticket, e.g. APM-3")
    actor:            Optional[str] = Field(None, description="Who is creating it (for the timeline)")


class TicketUpdate(BaseModel):
    title:            Optional[str] = Field(None, min_length=1, max_length=200)
    description:      Optional[str] = None
    ticket_type:      Optional[str] = None
    status:           Optional[str] = None
    priority:         Optional[str] = None
    priority_score:   Optional[int] = Field(None, ge=1, le=100)
    assignee:         Optional[str] = None
    reported_by:      Optional[str] = None
    # Links: "APM-3" sets the link, "" clears it
    parent_id:        Optional[str] = None
    duplicate_of:     Optional[str] = None
    # Timeline metadata – not stored on the ticket itself
    actor:            Optional[str] = Field(None, description="Who made the change, e.g. priority-agent")
    reason:           Optional[str] = Field(None, description="Why – shown on the timeline")


class TicketAssign(BaseModel):
    assignee: str = Field(..., min_length=1)


class TicketResponse(BaseModel):
    id:               int
    ticket_id:        str
    title:            str
    description:      Optional[str]
    ticket_type:      str
    status:           str
    priority:         str
    priority_score:   Optional[int]
    assignee:         Optional[str]
    reported_by:      Optional[str]
    source:           Optional[str]
    channel:          Optional[str]
    slack_message_ts: Optional[str]
    parent_id:        Optional[str] = None
    duplicate_of:     Optional[str] = None
    created_at:       datetime
    updated_at:       datetime

    model_config = {"from_attributes": True}


class TicketListResponse(BaseModel):
    tickets:   List[TicketResponse]
    total:     int
    page:      int
    page_size: int


class DashboardStats(BaseModel):
    total_tickets:     int
    active_tickets:    int
    completed_tickets: int
    blocked_tickets:   int
    critical_tickets:  int
    success_rate:      float
    by_status:         Dict[str, int]
    by_priority:       Dict[str, int]


# ── Timeline ─────────────────────────────────────────────────────────────────
EVENT_KINDS = {
    "created", "status_changed", "priority_changed", "assigned", "edited",
    "linked", "possible_duplicates", "subtasks_created", "agent_session", "note",
}


class TicketEventCreate(BaseModel):
    kind:    str            = Field("note")
    actor:   Optional[str]  = None
    summary: str            = Field(..., min_length=1, max_length=2000)
    data:    Optional[Dict[str, Any]] = None


class TicketEventResponse(BaseModel):
    id:         int
    ticket_id:  str
    kind:       str
    actor:      Optional[str]
    summary:    str
    data:       Optional[Dict[str, Any]] = None
    created_at: datetime


# ── Similarity / duplicates ──────────────────────────────────────────────────
class SimilarQuery(BaseModel):
    title:       str           = Field(..., min_length=1)
    description: Optional[str] = None
    limit:       int           = Field(5, ge=1, le=20)
    min_score:   float         = Field(0.2, ge=0, le=1)


class SimilarTicket(BaseModel):
    ticket_id: str
    title:     str
    status:    str
    priority:  str
    score:     float


# ── Sub-tasks ────────────────────────────────────────────────────────────────
class SubtaskItem(BaseModel):
    title:       str           = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    ticket_type: Optional[str] = "task"
    priority:    Optional[str] = None
    assignee:    Optional[str] = None


class SubtaskBatch(BaseModel):
    subtasks: List[SubtaskItem] = Field(..., min_length=1, max_length=20)
    actor:    Optional[str]     = None
