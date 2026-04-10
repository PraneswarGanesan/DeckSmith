"""
Content Transformer Agent — converts slide plan items into executive-quality bullet points.

Improvements over the naive version:
  • Uses combined_content from the planner (merged, deduplicated group content)
  • Falls back to DB fetch only when combined_content is absent
  • Uses a stronger, intent-aware prompt (McKinsey style)
  • Enforces 4-5 bullets, 8-12 words each, no filler language
  • Tracks used bullet fingerprints to prevent cross-slide duplication
"""
from __future__ import annotations

import json
import re

from core.llm import generate
from core.database import get_subsection
from logger import get_logger

logger = get_logger(__name__)

# ── Prompts ───────────────────────────────────────────────────────────────────

_PROMPT = """\
You are a McKinsey-style slide content writer.

Slide intent  : {intent}
Slide title   : {title}
Source content:
{content}

Write EXACTLY 4-5 executive bullet points for this slide.

NON-NEGOTIABLE RULES:
1. Each bullet: 8-12 words maximum
2. Start with a STRONG VERB or KEY NUMBER/STATISTIC
3. ONE insight per bullet — compress ruthlessly
4. Include specific data/numbers from the source when present
5. NO filler words: additionally, furthermore, in summary, various, several, many
6. NO vague phrases: significant, important, notable, considerable
7. NO repeating the same idea twice
8. Language: direct, assertive, specific

GOOD examples:
  "Fraud losses exceed $4.2B annually across digital payment channels"
  "Real-time monitoring reduces false-positive alerts by 62 percent"
  "Three-layer authentication cuts account breach risk by half"
  "Regulatory mandate requires full compliance by Q4 2025"

BAD examples (do NOT write like this):
  "There are various significant improvements that can be made to the system"
  "The data shows there are several important things to consider"
  "Additionally, the system has multiple features that are very useful"

Return ONLY a JSON array of 4-5 bullet strings. No markdown. No explanation.
"""

# Prompt variant for slides with no real source content (intro / Q&A)
_PROMPT_GENERIC = """\
You are a presentation writer.

Slide title: {title}
Topic: {query}

Write 3-4 short bullet points that summarise what this slide communicates.
Each bullet: max 12 words, starts with a strong verb or key fact.

Return ONLY a JSON array of bullet strings.
"""


# ── Bullet helpers ────────────────────────────────────────────────────────────

def _fix_capitalization(text: str) -> str:
    def fix_word(word: str) -> str:
        core = word.strip(".,;:()")
        if len(core) <= 3:
            return word
        upper_count = sum(1 for c in core if c.isupper())
        lower_count = sum(1 for c in core if c.islower())
        if lower_count == 0 and upper_count > 0:
            return word   # all-caps acronym — keep
        if upper_count > 1 and lower_count > 0:
            return word[: len(word) - len(core)] + core.capitalize()
        return word

    words = text.split()
    result = " ".join(fix_word(w) for w in words)
    return result[0].upper() + result[1:] if result and result[0].islower() else result


def _sanitize_bullet(text: str) -> str:
    """Strip JSON/markdown artifacts, enforce 12-word cap, fix capitalisation."""
    if not isinstance(text, str):
        text = str(text)
    text = text.strip()

    # Unwrap JSON objects the LLM accidentally returns
    if text.startswith("{") or text.startswith("["):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                for v in obj.values():
                    if isinstance(v, str) and len(v) > 3:
                        text = v
                        break
                else:
                    return ""
            elif isinstance(obj, list) and obj:
                text = str(obj[0])
            else:
                return ""
        except Exception:
            text = re.sub(r'[{}\[\]"\'\\]', " ", text).strip()

    text = re.sub(r"\*+", "", text)
    text = re.sub(r"^[-•*]\s*", "", text).strip()
    # Strip JSON key-value artifacts: "key": "value"  or  key: [
    text = re.sub(r'^"[\w_\s]+":\s*', "", text).strip()
    text = re.sub(r"^\w[\w\s]{0,20}:\s*", "", text).strip()
    # Strip leftover JSON punctuation at ends
    text = re.sub(r'[,\[\]{}"]+$', "", text).strip()
    text = re.sub(r'^[,\[\]{}"]+', "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()

    words = text.split()
    if len(words) < 2:
        return ""
    if re.match(r"^[\d\s.,]+$", text):
        return ""  # reject lone numbers
    if len(words) > 12:
        text = " ".join(words[:12])

    return _fix_capitalization(text)


def _parse_bullets(raw: str) -> list[str]:
    """Parse LLM output → clean list of bullets. Handles JSON + line fallback."""
    raw = raw.strip()
    start, end = raw.find("["), raw.rfind("]") + 1
    if start != -1 and end > start:
        try:
            parsed = json.loads(raw[start:end])
            if isinstance(parsed, list):
                bullets = []
                for item in parsed:
                    if isinstance(item, str):
                        clean = _sanitize_bullet(item)
                        if clean:
                            bullets.append(clean)
                    elif isinstance(item, dict):
                        for v in item.values():
                            if isinstance(v, str):
                                clean = _sanitize_bullet(v)
                                if clean:
                                    bullets.append(clean)
                                    break
                if bullets:
                    return bullets[:5]
        except json.JSONDecodeError:
            pass

    bullets = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith(("[", "{")):
            continue
        clean = _sanitize_bullet(line)
        if clean:
            bullets.append(clean)
    return bullets[:5]


def _fallback_bullets(content_text: str) -> list[str]:
    """Extract up to 5 sentences from raw content as last-resort bullets."""
    sentences = re.split(r"(?<=[.!?])\s+", content_text.replace("\n", " "))
    bullets = []
    for s in sentences:
        s = s.strip()
        words = s.split()
        if len(words) < 3:
            continue
        if len(words) > 12:
            s = " ".join(words[:12])
        bullets.append(s)
        if len(bullets) >= 5:
            break
    return bullets


def _bullet_fingerprint(text: str) -> str:
    """Normalised first 60 chars — for cross-slide deduplication."""
    return re.sub(r"\s+", " ", text.strip().lower())[:60]


# ── Main node ─────────────────────────────────────────────────────────────────

async def content_node(state: dict) -> dict:
    """
    Transform each planned slide into executive bullet points.

    Reads:
        state["plan"]    — slide plan from planner (may include combined_content)
        state["query"]   — original user query (for generic slides)

    Writes:
        state["slides"]  — slides with title, content, layout, type, intent
    """
    plan: list[dict]  = state.get("plan", [])
    query: str        = state.get("query", "Presentation").strip()

    if not plan:
        logger.warning("[Content] Empty plan — returning no slides")
        return {"slides": [], "error": None}

    logger.info(f"[Content] Transforming {len(plan)} slides")

    slides: list[dict] = []
    used_fingerprints: set[str] = set()   # cross-slide deduplication

    for item in plan:
        if not isinstance(item, dict):
            continue

        title      = str(item.get("title", "Slide")).strip() or "Slide"
        sub_id     = item.get("subsection_id")
        slide_type = str(item.get("type", "content")).lower()
        layout     = item.get("layout", "grid-2")
        intent     = item.get("intent", "content")

        if slide_type not in ("content", "chart"):
            slide_type = "content"

        # ── Source content resolution ──────────────────────────────────────
        # Priority: combined_content (from grouper) > DB fetch > empty
        content_text = item.get("combined_content", "").strip()

        if not content_text and sub_id:
            try:
                sub = get_subsection(sub_id)
                if sub:
                    content_text = str(sub.get("content", "")).strip()
            except Exception as exc:
                logger.warning(f"[Content] DB fetch failed for {sub_id}: {exc}")

        # ── Slides with no source content (agenda, Q&A, highlight, etc.) ────
        if not content_text:
            logger.debug(f"[Content] '{title}' — no source content")

            # Agenda: combined_content holds pipe-separated section titles
            if intent == "intro" and title.lower().startswith("agenda"):
                raw_agenda = item.get("combined_content", "")
                bullets = [t.strip() for t in raw_agenda.split("|") if t.strip()][:6]
                if not bullets:
                    bullets = [query]
            elif intent not in ("qna",):
                try:
                    prompt = _PROMPT_GENERIC.format(title=title, query=query)
                    raw    = await generate(prompt, temperature=0.3, max_tokens=256)
                    bullets = _parse_bullets(raw)[:4]
                except Exception:
                    bullets = []
            else:
                bullets = []

            slides.append({
                "title":          title,
                "content":        bullets,
                "subsection_id":  sub_id,
                "type":           slide_type,
                "layout":         layout,
                "intent":         intent,
            })
            continue

        # ── LLM transformation ────────────────────────────────────────────
        excerpt = content_text[:2500]   # generous context window
        prompt  = _PROMPT.format(title=title, content=excerpt, intent=intent)

        try:
            raw     = await generate(prompt, temperature=0.2, max_tokens=512)
            bullets = _parse_bullets(raw)[:5]
            if not bullets:
                logger.debug(f"[Content] LLM returned empty for '{title}', using fallback")
                bullets = _fallback_bullets(content_text)
        except Exception as exc:
            logger.warning(f"[Content] LLM failed for '{title}': {type(exc).__name__}: {exc}")
            bullets = _fallback_bullets(content_text)

        # ── Cross-slide deduplication ─────────────────────────────────────
        deduped_bullets: list[str] = []
        for bullet in bullets:
            fp = _bullet_fingerprint(bullet)
            if fp not in used_fingerprints:
                used_fingerprints.add(fp)
                deduped_bullets.append(bullet)

        if not deduped_bullets:
            # All bullets were duplicates — keep originals for this slide
            deduped_bullets = bullets

        slides.append({
            "title":          title,
            "content":        deduped_bullets[:5],
            "subsection_id":  sub_id,
            "type":           slide_type,
            "layout":         layout,
            "intent":         intent,
        })
        logger.debug(f"[Content] '{title}' → {len(deduped_bullets)} bullets (intent={intent})")

    logger.info(f"[Content] Generated {len(slides)} slides")
    return {"slides": slides, "error": None}
