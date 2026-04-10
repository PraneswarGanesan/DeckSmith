"""
Supabase client and all table CRUD operations.
Uses the service-role key so it bypasses RLS.
"""
from __future__ import annotations

import uuid
from supabase import create_client, Client
from config import settings
from logger import get_logger

logger = get_logger(__name__)

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)
        logger.info("Supabase client initialised")
    return _client


# ── document_structure ───────────────────────────────────────────────────────

def insert_document(doc_title: str, executive_summary: str) -> str:
    doc_id = str(uuid.uuid4())
    get_db().table("document_structure").insert(
        {"id": doc_id, "doc_title": doc_title, "executive_summary": executive_summary}
    ).execute()
    logger.debug(f"Inserted document id={doc_id}")
    return doc_id


def get_document(doc_id: str) -> dict:
    res = get_db().table("document_structure").select("*").eq("id", doc_id).single().execute()
    return res.data


# ── sections ─────────────────────────────────────────────────────────────────

def insert_section(doc_id: str, section_index: int, section_title: str) -> str:
    sec_id = str(uuid.uuid4())
    get_db().table("sections").insert(
        {"id": sec_id, "doc_id": doc_id, "section_index": section_index, "section_title": section_title}
    ).execute()
    return sec_id


def get_sections(doc_id: str) -> list[dict]:
    res = (
        get_db().table("sections")
        .select("*")
        .eq("doc_id", doc_id)
        .order("section_index")
        .execute()
    )
    return res.data or []


# ── subsections ──────────────────────────────────────────────────────────────

def insert_subsection(
    section_id: str,
    subsection_index: int,
    subsection_title: str,
    content: str,
    summary: str,
    keywords: list[str],
    embedding: list[float] | None = None,
) -> str:
    sub_id = str(uuid.uuid4())
    payload: dict = {
        "id": sub_id,
        "section_id": section_id,
        "subsection_index": subsection_index,
        "subsection_title": subsection_title,
        "content": content,
        "summary": summary,
        "keywords": keywords,
    }
    if embedding is not None:
        payload["embedding"] = embedding
    get_db().table("subsections").insert(payload).execute()
    return sub_id


def get_subsection(subsection_id: str) -> dict | None:
    res = get_db().table("subsections").select("*").eq("id", subsection_id).single().execute()
    return res.data


def get_subsections_by_section(section_ids: list[str]) -> list[dict]:
    if not section_ids:
        return []
    res = get_db().table("subsections").select("*").in_("section_id", section_ids).execute()
    return res.data or []


def get_all_subsections_for_doc(doc_id: str) -> list[dict]:
    sections = get_sections(doc_id)
    if not sections:
        return []
    sec_ids = [s["id"] for s in sections]
    return get_subsections_by_section(sec_ids)


# ── tables_data ───────────────────────────────────────────────────────────────

def insert_table(subsection_id: str, table_title: str, headers: list, rows: list) -> str:
    import json as _json
    t_id = str(uuid.uuid4())
    get_db().table("tables_data").insert({
        "id": t_id,
        "subsection_id": subsection_id,
        "table_title": table_title,
        "headers": headers,        # text[] — list of strings, supabase-py handles it
        "rows": rows,              # jsonb  — list of dicts
    }).execute()
    return t_id


def get_tables_for_subsection(subsection_id: str) -> list[dict]:
    res = get_db().table("tables_data").select("*").eq("subsection_id", subsection_id).execute()
    return res.data or []


# ── presentation_templates ────────────────────────────────────────────────────

def insert_template(name: str, storage_path: str, user_id: str | None = None) -> str:
    t_id = str(uuid.uuid4())
    payload: dict = {
        "id": t_id,
        "template_name": name,
        "storage_path": storage_path,
    }
    if user_id:
        payload["user_id"] = user_id
    get_db().table("presentation_templates").insert(payload).execute()
    return t_id


def get_template(template_id: str) -> dict:
    res = get_db().table("presentation_templates").select("*").eq("id", template_id).single().execute()
    return res.data


def list_templates() -> list[dict]:
    res = get_db().table("presentation_templates").select("*").execute()
    return res.data or []


# ── generated_outputs ─────────────────────────────────────────────────────────

def insert_output(user_id: str | None, template_id: str, status: str = "pending") -> str:
    out_id = str(uuid.uuid4())
    payload: dict = {"id": out_id, "template_id": template_id, "status": status, "output_path": ""}
    # user_id must be a valid UUID — skip it if it's a plain string label
    if user_id:
        try:
            uuid.UUID(user_id)   # validate
            payload["user_id"] = user_id
        except ValueError:
            pass  # not a UUID, leave it null
    get_db().table("generated_outputs").insert(payload).execute()
    return out_id


def update_output(output_id: str, status: str, output_path: str = "") -> None:
    payload: dict = {"status": status}
    if output_path:
        payload["output_path"] = output_path
    get_db().table("generated_outputs").update(payload).eq("id", output_id).execute()


def get_output(output_id: str) -> dict:
    res = get_db().table("generated_outputs").select("*").eq("id", output_id).single().execute()
    return res.data
