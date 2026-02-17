from typing import Generator, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.rag_generate import rag_explain

router = APIRouter()


class RagExplainRequest(BaseModel):
    query: str = Field(min_length=2)
    k: int = Field(default=12, ge=1, le=50)
    patch_version: Optional[str] = None
    entity_type: Optional[str] = None
    direction: Optional[str] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    entity: Optional[str] = None


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/explain")
def explain_with_rag(request: RagExplainRequest, db: Session = Depends(get_db)):
    try:
        return rag_explain(
            db=db,
            query=request.query,
            k=request.k,
            patch_version=request.patch_version,
            entity_type=request.entity_type,
            direction=request.direction,
            category=request.category,
            tag=request.tag,
            entity=request.entity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"RAG generation unavailable: {exc}") from exc
