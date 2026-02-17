from collections import defaultdict
from typing import Any, Dict, List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Change, Entity, Patch
from app.models.change import ChangeDirection
from app.models.entity import EntityType


def _signed_score(direction: ChangeDirection, impact_score: float) -> float:
    value = float(impact_score or 0.0)
    if direction == ChangeDirection.nerf:
        return -value
    if direction == ChangeDirection.adjustment:
        return 0.0
    return value


def _top_tag_contributions(
    champion_profile: Dict[str, float],
    patch_pressure: Dict[str, float],
    limit: int = 3,
) -> List[Dict[str, Any]]:
    contributions: List[Dict[str, Any]] = []
    for tag, champion_weight in champion_profile.items():
        pressure = patch_pressure.get(tag, 0.0)
        if pressure == 0.0:
            continue
        contributions.append(
            {
                "tag": tag,
                "champion_weight": champion_weight,
                "patch_pressure": pressure,
                "contribution": champion_weight * pressure,
            }
        )
    contributions.sort(key=lambda item: abs(float(item["contribution"])), reverse=True)
    return contributions[:limit]


def predict_patch_champion_impacts(db: Session, version: str, top_n: int = 25) -> Dict[str, Any]:
    patch = db.query(Patch).filter(Patch.version == version).first()
    if not patch:
        raise HTTPException(status_code=404, detail=f"Patch {version} not found")

    direct_rows = (
        db.query(Entity.name, Change.direction, Change.impact_score, Change.tags)
        .join(Entity, Entity.id == Change.entity_id)
        .filter(
            Change.patch_id == patch.id,
            Entity.entity_type == EntityType.champion,
        )
        .all()
    )
    direct_net_by_champion: Dict[str, float] = defaultdict(float)
    direct_count_by_champion: Dict[str, int] = defaultdict(int)
    for champion_name, direction, impact_score, _tags in direct_rows:
        direct_net_by_champion[str(champion_name)] += _signed_score(direction, float(impact_score or 0.0))
        direct_count_by_champion[str(champion_name)] += 1

    indirect_rows = (
        db.query(Entity.name, Entity.entity_type, Change.direction, Change.impact_score, Change.tags)
        .join(Entity, Entity.id == Change.entity_id)
        .filter(
            Change.patch_id == patch.id,
            Entity.entity_type.in_([EntityType.item, EntityType.system]),
        )
        .all()
    )
    patch_pressure_by_tag: Dict[str, float] = defaultdict(float)
    indirect_source_breakdown = {"item_changes": 0, "system_changes": 0}
    for _name, entity_type, direction, impact_score, tags in indirect_rows:
        signed = _signed_score(direction, float(impact_score or 0.0))
        if entity_type == EntityType.item:
            indirect_source_breakdown["item_changes"] += 1
        else:
            indirect_source_breakdown["system_changes"] += 1
        for tag in tags or []:
            normalized = str(tag).strip().lower()
            if normalized:
                patch_pressure_by_tag[normalized] += signed

    profile_rows = (
        db.query(Entity.name, Change.direction, Change.impact_score, Change.tags)
        .join(Entity, Entity.id == Change.entity_id)
        .filter(Entity.entity_type == EntityType.champion)
        .all()
    )
    profile_abs_sum_by_champion: Dict[str, float] = defaultdict(float)
    profile_signed_by_champion_tag: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for champion_name, direction, impact_score, tags in profile_rows:
        signed = _signed_score(direction, float(impact_score or 0.0))
        normalized_tags = [str(tag).strip().lower() for tag in (tags or []) if str(tag).strip()]
        if not normalized_tags:
            continue
        champion_key = str(champion_name)
        for tag in normalized_tags:
            profile_signed_by_champion_tag[champion_key][tag] += signed
            profile_abs_sum_by_champion[champion_key] += abs(signed)

    champions = sorted(
        set(direct_net_by_champion.keys()) | set(profile_signed_by_champion_tag.keys())
    )
    predicted_items: List[Dict[str, Any]] = []
    for champion_name in champions:
        raw_profile = profile_signed_by_champion_tag.get(champion_name, {})
        profile_total_abs = profile_abs_sum_by_champion.get(champion_name, 0.0)
        normalized_profile = (
            {tag: score / profile_total_abs for tag, score in raw_profile.items()}
            if profile_total_abs > 0
            else {}
        )

        indirect_score = 0.0
        overlap_count = 0
        for tag, champion_weight in normalized_profile.items():
            pressure = patch_pressure_by_tag.get(tag, 0.0)
            if pressure == 0.0:
                continue
            overlap_count += 1
            indirect_score += champion_weight * pressure

        direct_score = direct_net_by_champion.get(champion_name, 0.0)
        combined_score = direct_score + indirect_score
        confidence = min(
            1.0,
            (0.15 if direct_count_by_champion.get(champion_name, 0) > 0 else 0.0)
            + min(0.6, overlap_count * 0.12)
            + min(0.25, abs(indirect_score) / 30.0),
        )

        predicted_items.append(
            {
                "champion": champion_name,
                "direct_score": round(direct_score, 4),
                "indirect_score": round(indirect_score, 4),
                "predicted_net_score": round(combined_score, 4),
                "direct_change_count": direct_count_by_champion.get(champion_name, 0),
                "confidence": round(confidence, 3),
                "top_tag_drivers": _top_tag_contributions(normalized_profile, patch_pressure_by_tag),
            }
        )

    predicted_items.sort(key=lambda item: abs(float(item["predicted_net_score"])), reverse=True)
    return {
        "version": version,
        "indirect_change_sources": indirect_source_breakdown,
        "patch_tag_pressure": dict(sorted(patch_pressure_by_tag.items())),
        "count": min(len(predicted_items), top_n),
        "items": predicted_items[:top_n],
    }
