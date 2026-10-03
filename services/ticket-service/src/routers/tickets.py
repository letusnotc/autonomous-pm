"""
routers/tickets.py – Ticket CRUD, timeline, similarity and sub-task endpoints.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..schemas import (
    TicketCreate, TicketUpdate, TicketAssign, TicketResponse, TicketListResponse,
    TicketEventCreate, TicketEventResponse, SimilarQuery, SimilarTicket, SubtaskBatch,
)
from .. import crud

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket(payload: TicketCreate, db: AsyncSession = Depends(get_db)):
    return await crud.create_ticket(db, payload)


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    status:      Optional[str] = Query(None),
    priority:    Optional[str] = Query(None),
    ticket_type: Optional[str] = Query(None),
    assignee:    Optional[str] = Query(None),
    search:      Optional[str] = Query(None),
    parent:      Optional[str] = Query(None, description="Only sub-tasks of this ticket, e.g. APM-3"),
    page:        int           = Query(1,  ge=1),
    page_size:   int           = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await crud.list_tickets(db, status, priority, ticket_type, assignee, search, parent, page, page_size)


# Static paths must come before /{ticket_id}
@router.post("/similar", response_model=List[SimilarTicket], tags=["similarity"])
async def similar_to_text(payload: SimilarQuery, db: AsyncSession = Depends(get_db)):
    """Tickets similar to a draft title/description – used to warn before creating a duplicate."""
    return await crud.similar_to_text(db, payload)


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, db: AsyncSession = Depends(get_db)):
    return await crud.get_ticket(db, ticket_id)


@router.put("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(ticket_id: str, payload: TicketUpdate, db: AsyncSession = Depends(get_db)):
    return await crud.update_ticket(db, ticket_id, payload)


@router.post("/{ticket_id}/assign", response_model=TicketResponse)
async def assign_ticket(ticket_id: str, payload: TicketAssign, db: AsyncSession = Depends(get_db)):
    return await crud.assign_ticket(db, ticket_id, payload.assignee)


@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: str, db: AsyncSession = Depends(get_db)):
    return await crud.delete_ticket(db, ticket_id)


@router.get("/{ticket_id}/events", response_model=List[TicketEventResponse], tags=["timeline"])
async def list_events(ticket_id: str, db: AsyncSession = Depends(get_db)):
    """Activity timeline: creation, status/priority changes (with AI reasoning), links, agent sessions."""
    return await crud.list_events(db, ticket_id)


@router.post("/{ticket_id}/events", response_model=TicketEventResponse, status_code=201, tags=["timeline"])
async def add_event(ticket_id: str, payload: TicketEventCreate, db: AsyncSession = Depends(get_db)):
    return await crud.add_event(db, ticket_id, payload)


@router.get("/{ticket_id}/similar", response_model=List[SimilarTicket], tags=["similarity"])
async def similar_to_ticket(
    ticket_id: str,
    limit:     int   = Query(5,   ge=1, le=20),
    min_score: float = Query(0.2, ge=0, le=1),
    db: AsyncSession = Depends(get_db),
):
    return await crud.similar_to_ticket(db, ticket_id, limit, min_score)


@router.post("/{ticket_id}/subtasks", response_model=List[TicketResponse], status_code=201, tags=["sub-tasks"])
async def create_subtasks(ticket_id: str, payload: SubtaskBatch, db: AsyncSession = Depends(get_db)):
    """Create several sub-tasks under a ticket at once (e.g. an approved AI breakdown)."""
    return await crud.create_subtasks(db, ticket_id, payload)
