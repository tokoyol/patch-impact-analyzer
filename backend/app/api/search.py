from typing import Generator, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.services.semantic_search import semantic_search_changes

router = APIRouter()


class SemanticSearchRequest(BaseModel):
    query: str = Field(min_length=2)
    k: int = Field(default=20, ge=1, le=100)
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


@router.post("/semantic")
def semantic_search(request: SemanticSearchRequest, db: Session = Depends(get_db)):
    try:
        items = semantic_search_changes(
            db=db,
            query_text=request.query,
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
        raise HTTPException(status_code=503, detail=f"Semantic search unavailable: {exc}") from exc

    return {
        "query": request.query,
        "count": len(items),
        "filters": {
            "patch_version": request.patch_version,
            "entity_type": request.entity_type,
            "direction": request.direction,
            "category": request.category,
            "tag": request.tag,
            "entity": request.entity,
        },
        "items": items,
    }
