"""
Section Grouper Agent — merges fragmented RAG chunks into coherent slide groups.

Problem solved:
  RAG returns individual subsections as isolated chunks.  The same section
  can appear multiple times as separate results, producing slides that look like:
    "10.2 Stress Testing..."
    "10.2 Stress Testing..."   ← duplicate
    "10.2 Stress Testing..."   ← duplicate again

  This node eliminates that by:
  1. Grouping chunks by parent section_id (natural document boundary)
  2. Merging content within each group into one coherent block
  3. Deduplicating across groups by content fingerprint
  4. Classifying each group's semantic INTENT (intro / problem / analysis / …)
  5. Mapping intent → best layout type
  6. Capping at MAX_GROUPS to prevent slide explosion

Output per group:
  {
    "id"               : primary subsection id (real DB id, usable by content agent)
    "all_ids"          : all subsection ids merged into this group
    "section_id"       : parent section id
    "title"            : clean, presentation-ready title
    "raw_title"        : original subsection title (for debug)
    "combined_content" : merged content text (≤3000 chars)
    "intent"           : intro | problem | analysis | solution | policy | results | content
    "layout"           : matching layout type for template agent
    "has_table"        : True if any subsection in group has table data
    "keywords"         : merged keywords list
  }
"""
from __future__ import annotations

import re
from logger import get_logger

logger = get_logger(__name__)

MAX_GROUPS = 8   # leaves room for planner to add intro + Q&A slides

# ── Intent keyword signals ────────────────────────────────────────────────────
_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("intro",      ["introduction", "overview", "background", "executive", "summary",
                    "abstract", "scope", "objective", "purpose", "what is", "about",
                    "preface", "foreword", "prologue"]),
    ("problem",    ["problem", "challenge", "issue", "risk", "barrier", "obstacle",
                    "concern", "failure", "limitation", "gap", "weakness", "threat",
                    "fraud", "attack", "breach", "vulnerability", "crisis", "error",
                    "incident", "anomaly", "loss", "deficiency"]),
    ("analysis",   ["analysis", "data", "metric", "statistic", "trend", "performance",
                    "rate", "percentage", "figure", "table", "test", "stress",
                    "benchmark", "measure", "evaluation", "assessment", "comparison",
                    "study", "research", "survey", "finding", "result", "score"]),
    ("solution",   ["solution", "approach", "method", "step", "process", "implement",
                    "strategy", "framework", "architecture", "design", "system",
                    "mechanism", "technique", "model", "algorithm", "protocol",
                    "mitigation", "prevention", "countermeasure", "remedy", "fix"]),
    ("policy",     ["policy", "regulation", "compliance", "standard", "guideline",
                    "rule", "requirement", "law", "directive", "governance",
                    "mandate", "obligation", "framework", "procedure"]),
    ("results",    ["result", "outcome", "impact", "effect", "benefit",
                    "improvement", "achievement", "success", "gain", "reduction",
                    "increase", "decrease", "roi", "value", "return"]),
    ("conclusion", ["conclusion", "recommendation", "takeaway", "next step",
                    "future", "roadmap", "action", "way forward", "implication",
                    "lesson", "closing", "wrap"]),
]

# Intent → ideal layout
_INTENT_LAYOUT: dict[str, str] = {
    "intro":      "grid-2",
    "problem":    "left-text-right-visual",
    "analysis":   "comparison",
    "solution":   "process",
    "policy":     "grid-2",
    "results":    "comparison",
    "conclusion": "centered",
    "content":    "grid-2",
}

# Story arc sort order (intro first, conclusion last)
_INTENT_ORDER: dict[str, int] = {
    "intro":      0,
    "problem":    1,
    "analysis":   2,
    "solution":   3,
    "policy":     4,
    "results":    5,
    "conclusion": 6,
    "content":    3,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _classify_intent(title: str, content: str) -> str:
    """
    Classify semantic intent from title + first 500 chars of content.
    Returns the intent with the most keyword hits (or 'content' if none).
    """
    text = f"{title} {content[:500]}".lower()
    best_intent = "content"
    best_score  = 0

    for intent, keywords in _INTENT_KEYWORDS:
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score  = score
            best_intent = intent

    return best_intent


def _clean_title(raw: str) -> str:
    """
    Strip numeric prefixes and truncate to 8 words.
    '10.2 Stress Testing Methodology' → 'Stress Testing Methodology'
    """
    title = re.sub(r"^\d+(\.\d+)*\.?\s+", "", raw.strip())
    words = title.split()
    if len(words) > 8:
        title = " ".join(words[:8])
    return title.strip().capitalize() or "Content Slide"


def _content_fingerprint(text: str) -> str:
    """First 120 chars of normalised text — used to detect near-duplicates."""
    return re.sub(r"\s+", " ", text.strip().lower())[:120]


# ── Main node ─────────────────────────────────────────────────────────────────

async def grouper_node(state: dict) -> dict:
    """
    Merge and classify retrieved subsections before slide planning.

    Reads:  state["retrieved"]  → list of subsection dicts from RAG
    Writes: state["grouped"]    → list of coherent slide-group dicts
    """
    retrieved: list[dict] = state.get("retrieved", [])

    if not retrieved:
        logger.warning("[Grouper] Nothing to group — passing empty list")
        return {"grouped": [], "error": None}

    logger.info(f"[Grouper] Grouping {len(retrieved)} retrieved subsections")

    # ── Step 1: cluster by section_id ────────────────────────────────────────
    section_buckets: dict[str, list[dict]] = {}
    for sub in retrieved:
        # Use section_id if present; fall back to the subsection id itself
        sid = str(sub.get("section_id") or sub.get("id") or "unknown")
        section_buckets.setdefault(sid, []).append(sub)

    # ── Step 2: within each bucket, deduplicate and merge ────────────────────
    grouped: list[dict] = []
    seen_fingerprints: set[str] = set()

    for section_id, subs in section_buckets.items():
        # Preserve document order within the bucket
        subs.sort(key=lambda x: int(x.get("subsection_index", 0)))

        # Deduplicate by content fingerprint
        unique_subs: list[dict] = []
        for sub in subs:
            fp = _content_fingerprint(sub.get("content", ""))
            if fp and fp not in seen_fingerprints:
                seen_fingerprints.add(fp)
                unique_subs.append(sub)

        if not unique_subs:
            continue

        # Primary = subsection with most content (richest source)
        primary = max(unique_subs, key=lambda x: len(x.get("content", "")))

        # Merge content
        content_parts = [
            s.get("content", "").strip()
            for s in unique_subs
            if s.get("content", "").strip()
        ]
        combined_content = "\n\n".join(content_parts)

        # Merge keywords
        merged_keywords: list[str] = []
        seen_kw: set[str] = set()
        for sub in unique_subs:
            for kw in (sub.get("keywords") or []):
                if kw not in seen_kw:
                    seen_kw.add(kw)
                    merged_keywords.append(kw)

        # All titles for classification
        all_titles = " ".join(s.get("subsection_title", "") for s in unique_subs)
        intent = _classify_intent(all_titles, combined_content)
        layout = _INTENT_LAYOUT.get(intent, "grid-2")

        # has_table = at least one subsection had non-empty keywords proxy
        # (The real signal is from get_tables_for_subsection, checked later by chart agent)
        has_table = any(bool(s.get("keywords")) for s in unique_subs)

        grouped.append({
            "id":               primary["id"],
            "all_ids":          [s["id"] for s in unique_subs],
            "section_id":       section_id,
            "title":            _clean_title(primary.get("subsection_title", "Section")),
            "raw_title":        primary.get("subsection_title", ""),
            "combined_content": combined_content[:3000],   # cap for LLM context
            "intent":           intent,
            "layout":           layout,
            "has_table":        has_table,
            "keywords":         merged_keywords[:20],
            # Pass through so content agent can use without extra DB fetch
            "subsection_index": int(primary.get("subsection_index", 0)),
        })

    # ── Step 3: trim to MAX_GROUPS ────────────────────────────────────────────
    if len(grouped) > MAX_GROUPS:
        logger.info(f"[Grouper] {len(grouped)} groups → trimming to {MAX_GROUPS}")
        # Prefer content-rich groups; always keep the first (likely intro)
        first = grouped[:1]
        rest  = sorted(grouped[1:], key=lambda x: len(x["combined_content"]), reverse=True)
        grouped = (first + rest)[: MAX_GROUPS]

    # ── Step 4: sort by document order (story arc as secondary) ──────────────
    # Primary key: original document position (subsection_index of primary sub)
    # Secondary key: intent story-arc order (for items with the same position)
    grouped.sort(
        key=lambda x: (x.get("subsection_index", 0), _INTENT_ORDER.get(x["intent"], 3))
    )

    logger.info(
        f"[Grouper] → {len(grouped)} groups | "
        f"intents: {[g['intent'] for g in grouped]} | "
        f"layouts: {[g['layout'] for g in grouped]}"
    )
    return {"grouped": grouped, "error": None}
