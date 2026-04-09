from pydantic import BaseModel
from typing import List, Dict, Any


class Chunk(BaseModel):
    id: str
    content: str
    metadata: Dict[str, Any]


class TemplateElement(BaseModel):
    type: str
    x: float
    y: float
    width: float
    height: float


class IngestResult(BaseModel):
    total_chunks: int
    layout_elements: int
    status: str