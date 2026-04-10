"""
DeckSmith — Multi-Agent AI Presentation Builder
FastAPI application entry point.

Endpoints:
  POST /upload-template          → upload .pptx template
  GET  /templates                → list all templates
  POST /upload-markdown          → parse & store markdown document
  POST /generate-presentation    → start async generation pipeline
  GET  /output/{output_id}       → poll status / get download URL
  GET  /health                   → health check
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import settings
from logger import get_logger
from core.database import insert_output, get_output, get_document
from services.document_service import parse_and_store_markdown
from services.template_service import store_template, fetch_all_templates
from services.presentation_service import run_pipeline
from services.storage_service import get_public_url

logger = get_logger(__name__)


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("DeckSmith API starting …")
    # Pre-warm the LangGraph pipeline (avoids cold-start on first request)
    try:
        from core.graph import get_pipeline
        get_pipeline()
        logger.info("LangGraph pipeline pre-warmed")
    except Exception as exc:
        logger.warning(f"Pipeline pre-warm failed (non-fatal): {exc}")
    yield
    logger.info("DeckSmith API shutting down")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="DeckSmith AI",
    description=(
        "Multi-agent AI presentation builder. "
        "Converts Markdown documents into polished PPTX files using "
        "RAG + LangGraph + Ollama + Unsplash."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "ollama_model": settings.OLLAMA_LLM_MODEL,
        "embed_model": settings.OLLAMA_EMBED_MODEL,
    }


# ── Templates ─────────────────────────────────────────────────────────────────

@app.post("/upload-template", tags=["templates"])
async def upload_template(
    file: UploadFile = File(..., description="PowerPoint template (.pptx)"),
    name: str = Form(..., description="Display name for this template"),
):
    """
    Upload a .pptx file as a reusable slide template.
    Returns the template_id needed for /generate-presentation.
    """
    if not (file.filename or "").lower().endswith(".pptx"):
        raise HTTPException(status_code=400, detail="Only .pptx files are accepted")

    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 50 MB limit")
    if len(data) < 100:
        raise HTTPException(status_code=400, detail="File appears to be empty or corrupt")

    try:
        result = store_template(name.strip(), data)
        logger.info(f"Template uploaded: id={result['template_id']} name='{name}'")
        return result
    except Exception as exc:
        logger.error(f"Template upload error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/templates", tags=["templates"])
async def list_templates():
    """List all uploaded templates."""
    try:
        return fetch_all_templates()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Markdown / Documents ──────────────────────────────────────────────────────

@app.post("/upload-markdown", tags=["documents"])
async def upload_markdown(
    file: UploadFile = File(..., description="Markdown source document (.md or .txt)"),
):
    """
    Parse a Markdown file, generate embeddings via Ollama, and store the
    structured content (sections, subsections, tables) in Supabase.
    Returns the doc_id required for /generate-presentation.
    """
    filename = (file.filename or "").lower()
    if not (filename.endswith(".md") or filename.endswith(".txt")):
        raise HTTPException(status_code=400, detail="Only .md or .txt files are accepted")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit")

    text = data.decode("utf-8", errors="replace")
    if not text.strip():
        raise HTTPException(status_code=400, detail="File is empty")

    try:
        result = await parse_and_store_markdown(text)
        logger.info(
            f"Markdown stored: doc_id={result['doc_id']} "
            f"sections={result['sections']} subsections={result['subsections']}"
        )
        return result
    except Exception as exc:
        logger.error(f"Markdown upload error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


# ── Presentation generation ───────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    doc_id: str       = Field(..., description="UUID returned by /upload-markdown")
    template_id: str  = Field(..., description="UUID returned by /upload-template")
    query: str        = Field(..., min_length=3, description="Topic or question for the presentation")
    user_id: str      = Field("anonymous", description="Optional user identifier")


@app.post("/generate-presentation", tags=["generation"])
async def generate_presentation(req: GenerateRequest, background_tasks: BackgroundTasks):
    """
    Start the multi-agent pipeline in the background.
    Returns immediately with an output_id — poll GET /output/{output_id} for status.

    Pipeline:  retrieve → plan → content → chart → image → critic → template
    """
    # Validate document exists
    try:
        get_document(req.doc_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Document '{req.doc_id}' not found")

    # Pre-create output record so the caller gets an ID immediately
    output_id = insert_output(req.user_id, req.template_id, "queued")
    logger.info(f"Generation queued: output_id={output_id} query='{req.query[:60]}'")

    background_tasks.add_task(
        run_pipeline,
        output_id=output_id,
        doc_id=req.doc_id,
        template_id=req.template_id,
        query=req.query,
        user_id=req.user_id,
    )

    return {
        "output_id": output_id,
        "status": "queued",
        "message": "Pipeline started. Poll GET /output/{output_id} for progress.",
    }


# ── Output polling ────────────────────────────────────────────────────────────

@app.get("/output/{output_id}", tags=["generation"])
async def get_output_status(output_id: str):
    """
    Poll the status of a generation job.

    Possible statuses: queued | processing | complete | failed

    When status == "complete", the response includes a public download URL.
    """
    try:
        record = get_output(output_id)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Output '{output_id}' not found")

    response: dict = {
        "output_id": output_id,
        "status": record.get("status", "unknown"),
        "template_id": record.get("template_id"),
    }

    if record.get("status") == "complete" and record.get("output_path"):
        try:
            url = get_public_url(settings.STORAGE_BUCKET_OUTPUT, record["output_path"])
            response["download_url"] = url
        except Exception as exc:
            logger.warning(f"Could not build public URL: {exc}")

    return response


# ── Dev runner ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug" if settings.DEBUG else "info",
    )
