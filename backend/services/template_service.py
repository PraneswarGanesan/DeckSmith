"""
Template Service — uploads a .pptx template to raw-assets storage
and stores metadata in presentation_templates.
"""
from __future__ import annotations

import uuid

from config import settings
from core.database import insert_template, list_templates, get_template
from services.storage_service import upload_file
from logger import get_logger

logger = get_logger(__name__)

_PPTX_MIME = (
    "application/vnd.openxmlformats-officedocument"
    ".presentationml.presentation"
)


def store_template(name: str, file_bytes: bytes) -> dict:
    """
    Upload template to Supabase Storage and persist metadata.

    Returns:
        {"template_id": str, "name": str, "storage_path": str}
    """
    storage_path = f"templates/{uuid.uuid4()}.pptx"
    upload_file(settings.STORAGE_BUCKET_RAW, storage_path, file_bytes, _PPTX_MIME)
    template_id = insert_template(name, storage_path)
    logger.info(f"[TemplateService] Stored id={template_id} path={storage_path}")
    return {"template_id": template_id, "name": name, "storage_path": storage_path}


def fetch_all_templates() -> list[dict]:
    return list_templates()


def fetch_template(template_id: str) -> dict:
    return get_template(template_id)
