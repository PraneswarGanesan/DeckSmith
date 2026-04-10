"""
Supabase Storage helpers.
All bucket names are taken from config settings.
"""
from __future__ import annotations

from core.database import get_db
from logger import get_logger

logger = get_logger(__name__)

_PPTX_MIME = (
    "application/vnd.openxmlformats-officedocument"
    ".presentationml.presentation"
)


def upload_file(
    bucket: str,
    path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
) -> None:
    get_db().storage.from_(bucket).upload(
        path,
        data,
        file_options={"content-type": content_type, "upsert": "true"},
    )
    logger.info(f"[Storage] Uploaded gs://{bucket}/{path}")


def upload_pptx(bucket: str, path: str, data: bytes) -> None:
    upload_file(bucket, path, data, _PPTX_MIME)


def download_file(bucket: str, path: str) -> bytes:
    data = get_db().storage.from_(bucket).download(path)
    logger.debug(f"[Storage] Downloaded gs://{bucket}/{path} ({len(data)} bytes)")
    return data


def get_public_url(bucket: str, path: str) -> str:
    url = get_db().storage.from_(bucket).get_public_url(path)
    return url
