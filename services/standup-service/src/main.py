"""
main.py – Standup Service
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import StandupReport, StandupTriggerRequest

logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO))
logger = logging.getLogger("standup-service")

_last_report: Optional[StandupReport] = None

# Crontab expression for the automatic daily standup (default 09:00 Mon–Fri).
# Set STANDUP_CRON=off to disable.
STANDUP_CRON     = os.getenv("STANDUP_CRON", "0 9 * * 1-5").strip()
STANDUP_TIMEZONE = os.getenv("STANDUP_TIMEZONE", "UTC")


async def scheduled_standup():
    from .agent import StandupAgent
    global _last_report
    try:
        _last_report = await StandupAgent().run(StandupTriggerRequest(post_to_slack=True))
        logger.info(f"Scheduled standup generated (posted to Slack: {_last_report.channel_posted})")
    except Exception as e:
        logger.error(f"Scheduled standup failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Standup Service starting…")
    scheduler = None
    if STANDUP_CRON and STANDUP_CRON.lower() not in ("off", "none", "0", "false"):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            scheduled_standup,
            CronTrigger.from_crontab(STANDUP_CRON, timezone=STANDUP_TIMEZONE),
            id="standup", max_instances=1, coalesce=True,
        )
        scheduler.start()
        logger.info(f"Daily standup scheduled: '{STANDUP_CRON}' ({STANDUP_TIMEZONE})")
    else:
        logger.info("Daily standup schedule disabled (STANDUP_CRON=off)")
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="Autonomous PM – Standup Service",
    description="LLM-powered daily standup generator.",
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
        "service": "standup-service",
        "schedule": None if STANDUP_CRON.lower() in ("", "off", "none", "0", "false")
                    else f"{STANDUP_CRON} ({STANDUP_TIMEZONE})",
    }


@app.get("/standup/summary", response_model=StandupReport)
async def get_standup_summary():
    if _last_report is None:
        raise HTTPException(404, "No report yet. POST /standup/generate first.")
    return _last_report


@app.post("/standup/generate", response_model=StandupReport)
async def generate_standup(request: StandupTriggerRequest = StandupTriggerRequest()):
    from .agent import StandupAgent
    global _last_report
    try:
        agent  = StandupAgent()
        report = await agent.run(request)
        _last_report = report
        return report
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        logger.error(f"Standup generation failed: {e}")
        raise HTTPException(500, f"Internal error: {e}")
