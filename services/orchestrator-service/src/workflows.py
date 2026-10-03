"""
workflows.py – LangGraph StateGraph definitions.
"""
import logging
from langgraph.graph import StateGraph, END
from .schemas import WorkflowState, TriggerKind
from .nodes import (
    create_ticket_node, check_duplicates_node, prioritize_node, prepare_agent_node, standup_node,
)

logger = logging.getLogger("orchestrator.workflows")


def _wrap(node_fn):
    async def wrapped(state: dict) -> dict:
        ws = WorkflowState(**state)
        updated = await node_fn(ws)
        return updated.model_dump()
    wrapped.__name__ = node_fn.__name__
    return wrapped


def _add_intake_nodes(g: StateGraph):
    """create_ticket -> check_duplicates -> prioritize -> prepare_agent"""
    g.add_node("create_ticket",    _wrap(create_ticket_node))
    g.add_node("check_duplicates", _wrap(check_duplicates_node))
    g.add_node("prioritize",       _wrap(prioritize_node))
    g.add_node("prepare_agent",    _wrap(prepare_agent_node))
    g.set_entry_point("create_ticket")
    g.add_edge("create_ticket",    "check_duplicates")
    g.add_edge("check_duplicates", "prioritize")
    g.add_edge("prioritize",       "prepare_agent")


def build_slack_graph():
    g = StateGraph(dict)
    _add_intake_nodes(g)
    g.add_edge("prepare_agent", END)
    return g.compile()


def build_standup_graph():
    g = StateGraph(dict)
    g.add_node("standup", _wrap(standup_node))
    g.set_entry_point("standup")
    g.add_edge("standup", END)
    return g.compile()


def build_full_pipeline_graph():
    g = StateGraph(dict)
    _add_intake_nodes(g)
    g.add_node("standup", _wrap(standup_node))
    g.add_edge("prepare_agent", "standup")
    g.add_edge("standup",       END)
    return g.compile()


_REGISTRY = {
    "slack_message":  build_slack_graph,
    "manual_standup": build_standup_graph,
    "full_pipeline":  build_full_pipeline_graph,
}


def get_graph(trigger: TriggerKind):
    builder = _REGISTRY.get(trigger)
    return builder() if builder else None
