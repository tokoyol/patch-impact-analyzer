import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Change, Entity, Patch, PatchEntityImpact
from app.models.change import ChangeCategory, ChangeDirection
from app.schemas.ingest import PatchIngestPayload


@dataclass
class IngestSummary:
    version: str
    entities: int
    changes: int


def _compute_impact(category: ChangeCategory, delta_value: float) -> Tuple[float, float]:
    weights = {
        ChangeCategory.damage: 2.0,
        ChangeCategory.cooldown: 3.0,
        ChangeCategory.base_stat: 1.5,
        ChangeCategory.scaling: 2.5,
        ChangeCategory.cost: 1.5,
        ChangeCategory.mechanic: 4.0,
    }
    impact_weight = weights.get(category, 1.0)
    impact_score = impact_weight * abs(delta_value)
    return impact_weight, impact_score


def load_payload_from_file(file_path: Path) -> PatchIngestPayload:
    with file_path.open("r", encoding="utf-8") as f:
        content = json.load(f)
    return PatchIngestPayload.model_validate(content)


def _normalize_tags(tags: Any) -> Optional[List[str]]:
    if tags is None:
        return None

    if isinstance(tags, dict):
        # Backward compatibility for old {"tag": true} payloads.
        tags = [key for key, enabled in tags.items() if enabled]

    if not isinstance(tags, list):
        tags = [tags]

    normalized: List[str] = []
    seen = set()
    for tag in tags:
        cleaned = str(tag).strip().lower()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    return normalized or None


def _canonical_entity_key(name: str) -> str:
    lowered = name.strip().lower()
    lowered = lowered.replace("&", " and ")
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def ingest_patch_payload(db: Session, payload: PatchIngestPayload) -> IngestSummary:
    patch = db.execute(select(Patch).where(Patch.version == payload.version)).scalar_one_or_none()
    if patch is None:
        patch = Patch(
            version=payload.version,
            release_date=payload.release_date,
            raw_notes=payload.raw_notes,
        )
        db.add(patch)
        db.flush()
    else:
        patch.release_date = payload.release_date
        patch.raw_notes = payload.raw_notes

    existing_entities = db.execute(select(Entity)).scalars().all()
    canonical_existing: Dict[str, Entity] = {}
    for existing in existing_entities:
        canonical_existing.setdefault(_canonical_entity_key(existing.name), existing)

    entity_map: Dict[str, Entity] = {}
    for entity_in in payload.entities:
        canonical_key = _canonical_entity_key(entity_in.name)
        entity = canonical_existing.get(canonical_key)
        if entity is None:
            entity = Entity(
                name=entity_in.name,
                entity_type=entity_in.entity_type,
                primary_role=entity_in.primary_role,
            )
            db.add(entity)
            db.flush()
            canonical_existing[canonical_key] = entity
        else:
            entity.entity_type = entity_in.entity_type
            entity.primary_role = entity_in.primary_role
        entity_map[entity_in.name] = entity

    # Deterministic reruns: replace all rows for this patch.
    db.execute(delete(Change).where(Change.patch_id == patch.id))
    db.execute(delete(PatchEntityImpact).where(PatchEntityImpact.patch_id == patch.id))

    total_changes = 0
    merged_payload_entities: Dict[str, Tuple[Any, List[Any]]] = {}
    for entity_in in payload.entities:
        canonical_key = _canonical_entity_key(entity_in.name)
        if canonical_key not in merged_payload_entities:
            merged_payload_entities[canonical_key] = (entity_in, list(entity_in.changes))
        else:
            primary, existing_changes = merged_payload_entities[canonical_key]
            existing_changes.extend(entity_in.changes)
            merged_payload_entities[canonical_key] = (primary, existing_changes)

    for entity_in, merged_changes in merged_payload_entities.values():
        entity = entity_map[entity_in.name]
        entity_total_score = 0.0
        buff_count = 0
        nerf_count = 0
        adjustment_count = 0

        for change_in in merged_changes:
            delta_value = change_in.delta_value or 0.0
            impact_weight, impact_score = _compute_impact(change_in.category, delta_value)

            change = Change(
                patch_id=patch.id,
                entity_id=entity.id,
                category=change_in.category,
                stat_name=change_in.stat_name,
                ability_slot=change_in.ability_slot,
                old_value=change_in.old_value,
                new_value=change_in.new_value,
                delta_value=change_in.delta_value,
                delta_percent=change_in.delta_percent,
                direction=change_in.direction,
                impact_weight=change_in.impact_weight if change_in.impact_weight is not None else impact_weight,
                impact_score=change_in.impact_score if change_in.impact_score is not None else impact_score,
                tags=_normalize_tags(change_in.tags),
            )
            db.add(change)
            total_changes += 1

            resolved_score = change_in.impact_score if change_in.impact_score is not None else impact_score
            entity_total_score += resolved_score
            if change_in.direction == ChangeDirection.buff:
                buff_count += 1
            elif change_in.direction == ChangeDirection.nerf:
                nerf_count += 1
            else:
                adjustment_count += 1

        db.add(
            PatchEntityImpact(
                patch_id=patch.id,
                entity_id=entity.id,
                total_impact_score=entity_total_score,
                buff_count=buff_count,
                nerf_count=nerf_count,
                adjustment_count=adjustment_count,
            )
        )

    return IngestSummary(
        version=patch.version,
        entities=len(merged_payload_entities),
        changes=total_changes,
    )

