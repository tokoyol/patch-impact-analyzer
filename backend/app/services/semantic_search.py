from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Change, ChangeEmbedding, Entity, Patch
from app.models.change import ChangeCategory, ChangeDirection
from app.models.entity import EntityType
from app.services.embed_changes import embed_text


def semantic_search_changes(
    db: Session,
    query_text: str,
    k: int = 20,
    patch_version: Optional[str] = None,
    entity_type: Optional[str] = None,
    direction: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    entity: Optional[str] = None,
) -> List[Dict[str, Any]]:
    query_embedding = embed_text(query_text)
    distance = ChangeEmbedding.embedding.cosine_distance(query_embedding).label("distance")

    query = (
        select(
            ChangeEmbedding,
            Change,
            Entity.name.label("entity_name"),
            Entity.entity_type.label("entity_type_value"),
            Patch.version.label("patch_version"),
            distance,
        )
        .join(Change, Change.id == ChangeEmbedding.change_id)
        .join(Entity, Entity.id == Change.entity_id)
        .join(Patch, Patch.id == Change.patch_id)
    )

    if entity_type:
        normalized_entity_type = entity_type.strip().lower()
        if normalized_entity_type != "all":
            valid_entity_types = {e.value for e in EntityType}
            if normalized_entity_type not in valid_entity_types:
                raise ValueError("Invalid entity_type")
            query = query.where(Entity.entity_type == EntityType(normalized_entity_type))

    if patch_version:
        query = query.where(Patch.version == patch_version.strip())

    if direction:
        normalized_direction = direction.strip().lower()
        valid_directions = {d.value for d in ChangeDirection}
        if normalized_direction not in valid_directions:
            raise ValueError("Invalid direction")
        query = query.where(Change.direction == ChangeDirection(normalized_direction))

    if category:
        normalized_category = category.strip().lower()
        valid_categories = {c.value for c in ChangeCategory}
        if normalized_category not in valid_categories:
            raise ValueError("Invalid category")
        query = query.where(Change.category == ChangeCategory(normalized_category))

    if tag:
        normalized_tag = tag.strip().lower()
        if normalized_tag:
            query = query.where(Change.tags.isnot(None), Change.tags.contains([normalized_tag]))

    if entity:
        query = query.where(Entity.name.ilike(f"%{entity.strip()}%"))

    rows = db.execute(query.order_by(distance.asc()).limit(max(1, min(k, 100)))).all()

    results: List[Dict[str, Any]] = []
    for embedding_row, change, entity_name, entity_type_value, version, raw_distance in rows:
        similarity = 1.0 - float(raw_distance)
        results.append(
            {
                "score": similarity,
                "distance": float(raw_distance),
                "patch_version": version,
                "entity": entity_name,
                "entity_type": (
                    entity_type_value.value if hasattr(entity_type_value, "value") else str(entity_type_value)
                ),
                "ability_slot": change.ability_slot,
                "direction": change.direction.value,
                "category": change.category.value,
                "stat_name": change.stat_name,
                "old_value": change.old_value,
                "new_value": change.new_value,
                "delta_value": change.delta_value,
                "impact_score": change.impact_score,
                "tags": change.tags or [],
                "embedding_model": embedding_row.model,
            }
        )
    return results
