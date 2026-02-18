import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import Change, ChangeEmbedding, Entity, Patch
from app.models.change import ChangeCategory, ChangeDirection
from app.models.entity import EntityType
from app.services.embed_changes import embed_text


def _normalize_text_key(value: str) -> str:
    lowered = value.strip().lower()
    lowered = lowered.replace("&", " and ")
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _infer_entity_from_query(
    db: Session,
    query_text: str,
    patch_version: Optional[str],
    explicit_entity_type: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    normalized_query = f" {_normalize_text_key(query_text)} "
    if len(normalized_query.strip()) < 2:
        return None, None

    query = db.query(Entity.name, Entity.entity_type).distinct()
    if explicit_entity_type and explicit_entity_type != "all":
        query = query.filter(Entity.entity_type == EntityType(explicit_entity_type))
    else:
        query = query.filter(Entity.entity_type.in_([EntityType.item, EntityType.system]))

    if patch_version:
        query = (
            query.join(Change, Change.entity_id == Entity.id)
            .join(Patch, Patch.id == Change.patch_id)
            .filter(Patch.version == patch_version.strip())
        )

    best_name: Optional[str] = None
    best_type: Optional[str] = None
    best_len = -1
    for name, entity_type in query.all():
        normalized_name = _normalize_text_key(name)
        if not normalized_name:
            continue
        if f" {normalized_name} " in normalized_query and len(normalized_name) > best_len:
            best_name = name
            best_type = entity_type.value if hasattr(entity_type, "value") else str(entity_type)
            best_len = len(normalized_name)
    return best_name, best_type


def _fallback_sql_search(
    db: Session,
    query_text: str,
    k: int,
    patch_version: Optional[str],
    entity_type: Optional[str],
    direction: Optional[str],
    category: Optional[str],
    tag: Optional[str],
    entity: Optional[str],
) -> List[Dict[str, Any]]:
    query = (
        db.query(Change, Entity.name.label("entity_name"), Entity.entity_type.label("entity_type_value"), Patch.version)
        .join(Entity, Entity.id == Change.entity_id)
        .join(Patch, Patch.id == Change.patch_id)
    )

    if entity_type and entity_type != "all":
        query = query.filter(Entity.entity_type == EntityType(entity_type))
    if patch_version:
        query = query.filter(Patch.version == patch_version.strip())
    if direction:
        query = query.filter(Change.direction == ChangeDirection(direction))
    if category:
        query = query.filter(Change.category == ChangeCategory(category))
    if tag:
        normalized_tag = tag.strip().lower()
        if normalized_tag:
            query = query.filter(Change.tags.isnot(None), Change.tags.contains([normalized_tag]))
    if entity:
        query = query.filter(Entity.name.ilike(f"%{entity.strip()}%"))

    normalized_query = _normalize_text_key(query_text)
    tokens = [token for token in normalized_query.split() if len(token) >= 2]

    # Lightweight query intent extraction for non-embedding fallback mode.
    if not direction:
        if any(token in {"buff", "buffs", "buffed", "increase", "increased"} for token in tokens):
            query = query.filter(Change.direction == ChangeDirection.buff)
        elif any(token in {"nerf", "nerfs", "nerfed", "reduce", "reduced"} for token in tokens):
            query = query.filter(Change.direction == ChangeDirection.nerf)
        elif any(token in {"adjust", "adjustment", "adjustments"} for token in tokens):
            query = query.filter(Change.direction == ChangeDirection.adjustment)

    if not category:
        category_by_token = {
            "cooldown": ChangeCategory.cooldown,
            "cd": ChangeCategory.cooldown,
            "damage": ChangeCategory.damage,
            "dmg": ChangeCategory.damage,
            "cost": ChangeCategory.cost,
            "gold": ChangeCategory.cost,
            "mana": ChangeCategory.cost,
            "scaling": ChangeCategory.scaling,
            "ratio": ChangeCategory.scaling,
            "base": ChangeCategory.base_stat,
            "stats": ChangeCategory.base_stat,
            "stat": ChangeCategory.base_stat,
            "mechanic": ChangeCategory.mechanic,
        }
        inferred_category = next(
            (category_by_token[token] for token in tokens if token in category_by_token),
            None,
        )
        if inferred_category is not None:
            query = query.filter(Change.category == inferred_category)

    rows = (
        query.order_by(desc(Change.impact_score), Patch.version.desc(), Entity.name.asc(), Change.id.asc())
        .limit(500)
        .all()
    )

    def lexical_score(change: Change, entity_name: str, row_patch_version: str) -> int:
        if not tokens:
            return 0
        haystack = " ".join(
            [
                entity_name or "",
                change.stat_name or "",
                change.ability_slot or "",
                " ".join(change.tags or []),
                change.direction.value,
                change.category.value,
                row_patch_version or "",
            ]
        ).lower()
        return sum(1 for token in tokens if token in haystack)

    if tokens:
        scored_rows = []
        for change, entity_name, entity_type_value, version in rows:
            score = lexical_score(change, entity_name, version)
            if score > 0:
                scored_rows.append((score, change, entity_name, entity_type_value, version))
        scored_rows.sort(key=lambda item: (item[0], float(item[1].impact_score or 0.0)), reverse=True)
        rows = [(change, entity_name, entity_type_value, version) for _, change, entity_name, entity_type_value, version in scored_rows]

    rows = rows[: max(1, min(k, 100))]

    results: List[Dict[str, Any]] = []
    for change, entity_name, entity_type_value, version in rows:
        results.append(
            {
                "score": 0.0,
                "distance": 1.0,
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
                "embedding_model": "fallback-sql",
            }
        )
    return results


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
    normalized_entity_type = entity_type.strip().lower() if entity_type else None
    if normalized_entity_type and normalized_entity_type != "all":
        valid_entity_types = {e.value for e in EntityType}
        if normalized_entity_type not in valid_entity_types:
            raise ValueError("Invalid entity_type")

    normalized_direction = direction.strip().lower() if direction else None
    if normalized_direction:
        valid_directions = {d.value for d in ChangeDirection}
        if normalized_direction not in valid_directions:
            raise ValueError("Invalid direction")

    normalized_category = category.strip().lower() if category else None
    if normalized_category:
        valid_categories = {c.value for c in ChangeCategory}
        if normalized_category not in valid_categories:
            raise ValueError("Invalid category")

    normalized_entity = entity.strip() if entity else None
    if not normalized_entity:
        inferred_name, inferred_type = _infer_entity_from_query(
            db=db,
            query_text=query_text,
            patch_version=patch_version,
            explicit_entity_type=normalized_entity_type,
        )
        if inferred_name:
            normalized_entity = inferred_name
            if not normalized_entity_type and inferred_type in {EntityType.item.value, EntityType.system.value}:
                normalized_entity_type = inferred_type

    try:
        query_embedding = embed_text(query_text)
    except Exception:
        # In production, embedding infra (e.g. Ollama) may be unavailable.
        # Fall back to deterministic SQL ranking instead of failing the endpoint.
        return _fallback_sql_search(
            db=db,
            query_text=query_text,
            k=k,
            patch_version=patch_version,
            entity_type=normalized_entity_type,
            direction=normalized_direction,
            category=normalized_category,
            tag=tag,
            entity=normalized_entity,
        )
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

    if normalized_entity_type:
        if normalized_entity_type != "all":
            query = query.where(Entity.entity_type == EntityType(normalized_entity_type))

    if patch_version:
        query = query.where(Patch.version == patch_version.strip())

    if normalized_direction:
        query = query.where(Change.direction == ChangeDirection(normalized_direction))

    if normalized_category:
        query = query.where(Change.category == ChangeCategory(normalized_category))

    if tag:
        normalized_tag = tag.strip().lower()
        if normalized_tag:
            query = query.where(Change.tags.isnot(None), Change.tags.contains([normalized_tag]))

    if normalized_entity:
        query = query.where(Entity.name.ilike(f"%{normalized_entity}%"))

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
    if results:
        return results

    return _fallback_sql_search(
        db=db,
        query_text=query_text,
        k=k,
        patch_version=patch_version,
        entity_type=normalized_entity_type,
        direction=normalized_direction,
        category=normalized_category,
        tag=tag,
        entity=normalized_entity,
    )
