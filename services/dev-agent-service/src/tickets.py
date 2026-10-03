"""
tickets.py – Client for the Ticket Service.
"""
from typing import Any, Dict, List, Optional
import httpx

from .config import TICKET_SERVICE_URL

TIMEOUT = 15


class TicketNotFound(Exception):
    pass


async def _get(path: str, **params) -> Any:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.get(f"{TICKET_SERVICE_URL}{path}", params=params or None)
        if resp.status_code == 404:
            raise TicketNotFound(path)
        resp.raise_for_status()
        return resp.json()


async def get_ticket(ticket_id: str) -> Dict:
    return await _get(f"/tickets/{ticket_id}")


async def get_events(ticket_id: str) -> List[Dict]:
    return await _get(f"/tickets/{ticket_id}/events")


async def get_children(ticket_id: str) -> List[Dict]:
    return (await _get("/tickets", parent=ticket_id, page_size=100))["tickets"]


async def get_similar(ticket_id: str, limit: int = 3, min_score: float = 0.3) -> List[Dict]:
    return await _get(f"/tickets/{ticket_id}/similar", limit=limit, min_score=min_score)


async def get_optional(ticket_id: Optional[str]) -> Optional[Dict]:
    if not ticket_id:
        return None
    try:
        return await get_ticket(ticket_id)
    except TicketNotFound:
        return None


async def add_event(ticket_id: str, kind: str, summary: str, data: Optional[Dict] = None,
                    actor: str = "dev-agent") -> None:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.post(f"{TICKET_SERVICE_URL}/tickets/{ticket_id}/events",
                            json={"kind": kind, "actor": actor, "summary": summary, "data": data})
        resp.raise_for_status()


async def create_subtasks(ticket_id: str, subtasks: List[Dict], actor: str) -> List[Dict]:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        resp = await c.post(f"{TICKET_SERVICE_URL}/tickets/{ticket_id}/subtasks",
                            json={"subtasks": subtasks, "actor": actor})
        resp.raise_for_status()
        return resp.json()
