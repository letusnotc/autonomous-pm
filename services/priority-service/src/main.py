"""
main.py – Priority Service
LLM-powered ticket prioritisation agent.
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .agent import PriorityAgent
from .models import PrioritizeRequest, PriorityReport

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
logger = logging.getLogger("priority-service")

_last_report: Optional[PriorityReport] = None
_is_running = False

# Minutes between automatic prioritisation runs; 0 disables the schedule.
PRIORITY_SCHEDULE_MINUTES = int(os.getenv("PRIORITY_SCHEDULE_MINUTES", "60"))


class AlreadyRunning(Exception):
    pass


async def run_prioritization(project_key: Optional[str] = None) -> PriorityReport:
    """Single entry point for both the API and the scheduler, sharing one lock."""
    global _is_running, _last_report
    if _is_running:
        raise AlreadyRunning()
    _is_running = True
    try:
        report = await PriorityAgent().run(filter_project=project_key)
        _last_report = report
        return report
    finally:
        _is_running = False


async def scheduled_prioritization():
    try:
        report = await run_prioritization()
        logger.info(f"Scheduled prioritisation done: {report.total_tickets} tickets, "
                    f"{report.high_priority_count} high/critical")
    except AlreadyRunning:
        logger.info("Scheduled prioritisation skipped – a run is already in progress")
    except Exception as e:
        logger.error(f"Scheduled prioritisation failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Priority Service starting…")
    scheduler = None
    if PRIORITY_SCHEDULE_MINUTES > 0:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            scheduled_prioritization, "interval",
            minutes=PRIORITY_SCHEDULE_MINUTES, id="prioritize",
            max_instances=1, coalesce=True,
        )
        scheduler.start()
        logger.info(f"Auto-prioritisation scheduled every {PRIORITY_SCHEDULE_MINUTES} min")
    else:
        logger.info("Auto-prioritisation disabled (PRIORITY_SCHEDULE_MINUTES=0)")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)
    logger.info("Priority Service shutting down")


app = FastAPI(
    title="Autonomous PM – Priority Service",
    description="LLM-powered ticket priority agent. Reads from and writes to the Ticket Service.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["meta"])
async def health():
    return {
        "status": "ok",
        "service": "priority-service",
        "schedule_minutes": PRIORITY_SCHEDULE_MINUTES or None,
    }


@app.post("/tickets/prioritize", response_model=PriorityReport)
async def prioritize_tickets(request: PrioritizeRequest = PrioritizeRequest()):
    try:
        return await run_prioritization(request.project_key)
    except AlreadyRunning:
        raise HTTPException(409, "Prioritisation already in progress. Try GET /tickets/priorities for cached result.")
    except Exception as e:
        logger.error(f"Prioritisation failed: {e}")
        raise HTTPException(500, str(e))


@app.get("/tickets/priorities", response_model=PriorityReport)
async def get_latest_priorities():
    if _last_report is None:
        raise HTTPException(404, "No report yet. POST /tickets/prioritize first.")
    return _last_report
