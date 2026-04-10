"""
LangGraph orchestration pipeline.
Nodes run sequentially: retrieve → plan → content → chart → image → critic → template
"""
from __future__ import annotations

from typing import TypedDict
from langgraph.graph import StateGraph, END
from logger import get_logger

logger = get_logger(__name__)


# ── Shared pipeline state ─────────────────────────────────────────────────────

class PipelineState(TypedDict):
    # ── inputs ──────────────────────────────────────
    query: str
    doc_id: str
    template_id: str
    output_id: str
    user_id: str
    # ── intermediate ────────────────────────────────
    retrieved: list[dict]        # top-k subsections from RAG
    plan: list[dict]             # [{title, subsection_id, type}]
    slides: list[dict]           # [{title, content, subsection_id, type}]
    charts: list[dict]           # one entry per slide (empty dict if no chart)
    images: dict[str, str]       # {slide_idx_str: unsplash_url}
    # ── output ──────────────────────────────────────
    critiqued_slides: list[dict] # refined version of slides
    pptx_bytes: bytes
    error: str | None


# ── Graph factory ─────────────────────────────────────────────────────────────

def build_pipeline() -> object:
    from agents.retriever_agent import retriever_node
    from agents.planner_agent import planner_node
    from agents.content_agent import content_node
    from agents.chart_agent import chart_node
    from agents.image_agent import image_node
    from agents.critic_agent import critic_node
    from agents.template_agent import template_node

    graph: StateGraph = StateGraph(PipelineState)

    graph.add_node("retriever", retriever_node)
    graph.add_node("planner",   planner_node)
    graph.add_node("content",   content_node)
    graph.add_node("chart",     chart_node)
    graph.add_node("image",     image_node)
    graph.add_node("critic",    critic_node)
    graph.add_node("template",  template_node)

    graph.set_entry_point("retriever")
    graph.add_edge("retriever", "planner")
    graph.add_edge("planner",   "content")
    graph.add_edge("content",   "chart")
    graph.add_edge("chart",     "image")
    graph.add_edge("image",     "critic")
    graph.add_edge("critic",    "template")
    graph.add_edge("template",  END)

    compiled = graph.compile()
    logger.info("LangGraph pipeline compiled successfully")
    return compiled


# Lazy-initialised singleton — avoids import-time circular dependency
_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline
