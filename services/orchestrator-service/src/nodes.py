"""
nodes.py – LangGraph node functions.
"""
import logging
from datetime import datetime
from .schemas import WorkflowState
from . import clients

logger = logging.getLogger("orchestrator.nodes")


async def create_ticket_node(state: WorkflowState) -> WorkflowState:
    logger.info("[create_ticket_node] starting")
    if state.slack_payload is None:
        state.errors.append("create_ticket_node: no slack_payload")
        return state
    p = state.slack_payload
    try:
        ticket = await clients.create_ticket(
            title=p.title, description=p.description,
            ticket_type=p.ticket_type, priority=p.priority,
            reported_by=p.reported_by, source=p.source,
            channel=p.channel, slack_message_ts=p.slack_message_ts,
        )
        state.created_ticket = ticket
        state.steps_completed.append(f"create_ticket:{ticket.get('ticket_id')}")
        logger.info(f"[create_ticket_node] created {ticket.get('ticket_id')}")
    except Exception as e:
        err = f"create_ticket_node failed: {e}"
        logger.error(err)
        state.errors.append(err)
    return state


async def check_duplicates_node(state: WorkflowState) -> WorkflowState:
    logger.info("[check_duplicates_node] starting")
    if not state.created_ticket:
        return state
    try:
        state.duplicates = await clients.find_duplicates(state.created_ticket["ticket_id"])
        state.steps_completed.append(f"check_duplicates:found={len(state.duplicates)}")
    except Exception as e:
        err = f"check_duplicates_node failed: {e}"
        logger.error(err)
        state.errors.append(err)
    return state


async def prepare_agent_node(state: WorkflowState) -> WorkflowState:
    """Optional step - a missing dev-agent service is logged, not treated as a failure."""
    logger.info("[prepare_agent_node] starting")
    if not state.created_ticket:
        return state
    try:
        result = await clients.auto_prepare_agent(state.created_ticket["ticket_id"])
        if result.get("prepared"):
            state.agent_session = result["session"]
        state.steps_completed.append(f"prepare_agent:prepared={bool(result.get('prepared'))}")
    except Exception as e:
        logger.warning(f"[prepare_agent_node] skipped: {e}")
        state.steps_completed.append("prepare_agent:unavailable")
    return state


async def prioritize_node(state: WorkflowState) -> WorkflowState:
    logger.info("[prioritize_node] starting")
    try:
        report = await clients.run_prioritization()
        state.priority_report = report
        state.steps_completed.append(f"prioritize:total={report.get('total_tickets','?')}")
    except Exception as e:
        err = f"prioritize_node failed: {e}"
        logger.error(err)
        state.errors.append(err)
    return state


async def standup_node(state: WorkflowState) -> WorkflowState:
    logger.info("[standup_node] starting")
    try:
        report = await clients.generate_standup(
            post_to_slack=state.post_standup_to_slack,
            channel=state.standup_channel,
        )
        state.standup_report = report
        state.steps_completed.append(f"standup:posted={report.get('channel_posted')}")
    except Exception as e:
        err = f"standup_node failed: {e}"
        logger.error(err)
        state.errors.append(err)
    return state
