from typing import Generator, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Change, Entity, Patch
from app.models.change import ChangeCategory, ChangeDirection
from app.models.entity import EntityType
from app.services.champion_impact_predictor import predict_patch_champion_impacts

router = APIRouter()
EXCLUDED_PATCH_VERSIONS = set()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _compute_patch_intelligence(version: str, db: Session):
    patch = db.query(Patch).filter(Patch.version == version).first()
    if not patch:
        raise HTTPException(status_code=404, detail=f"Patch {version} not found")

    rows = (
        db.query(Change.direction, Change.impact_score, Entity.primary_role)
        .join(Entity, Entity.id == Change.entity_id)
        .filter(
            Change.patch_id == patch.id,
            Entity.entity_type == EntityType.champion,
        )
        .all()
    )

    buff_count = 0
    nerf_count = 0
    adjustment_count = 0
    risk_score = 0.0
    role_distribution = {}

    for direction, impact_score, primary_role in rows:
        role_key = (primary_role or "unknown").strip().lower() or "unknown"
        role_bucket = role_distribution.setdefault(
            role_key,
            {"buffs": 0, "nerfs": 0, "adjustments": 0, "total_changes": 0},
        )

        score_value = float(impact_score or 0.0)
        risk_score += abs(score_value)
        role_bucket["total_changes"] += 1

        if direction == ChangeDirection.buff:
            buff_count += 1
            role_bucket["buffs"] += 1
        elif direction == ChangeDirection.nerf:
            nerf_count += 1
            role_bucket["nerfs"] += 1
        else:
            adjustment_count += 1
            role_bucket["adjustments"] += 1

    return {
        "version": patch.version,
        "buff_count": buff_count,
        "nerf_count": nerf_count,
        "adjustment_count": adjustment_count,
        "risk_score": risk_score,
        "role_distribution": role_distribution,
    }


@router.get("/list")
def list_patches(db: Session = Depends(get_db)):
    patches = (
        db.query(Patch)
        .filter(~Patch.version.in_(EXCLUDED_PATCH_VERSIONS))
        .order_by(Patch.release_date.desc(), Patch.version.desc())
        .all()
    )
    return {
        "patches": [
            {
                "version": patch.version,
                "release_date": patch.release_date.isoformat(),
                "is_test": False,
                "note": None,
            }
            for patch in patches
        ]
    }


@router.get("/compare/intelligence")
def compare_patch_intelligence(
    base_version: str,
    target_version: str,
    db: Session = Depends(get_db),
):
    base = _compute_patch_intelligence(base_version, db)
    target = _compute_patch_intelligence(target_version, db)

    roles = sorted(set(base["role_distribution"].keys()) | set(target["role_distribution"].keys()))
    role_distribution_changes = {}
    for role in roles:
        base_role = base["role_distribution"].get(
            role, {"buffs": 0, "nerfs": 0, "adjustments": 0, "total_changes": 0}
        )
        target_role = target["role_distribution"].get(
            role, {"buffs": 0, "nerfs": 0, "adjustments": 0, "total_changes": 0}
        )
        role_distribution_changes[role] = {
            "delta_total_changes": target_role["total_changes"] - base_role["total_changes"],
            "delta_buffs": target_role["buffs"] - base_role["buffs"],
            "delta_nerfs": target_role["nerfs"] - base_role["nerfs"],
            "delta_adjustments": target_role["adjustments"] - base_role["adjustments"],
        }

    return {
        "base_version": base_version,
        "target_version": target_version,
        "base": base,
        "target": target,
        "delta": {
            "net_buff_count": target["buff_count"] - base["buff_count"],
            "net_nerf_count": target["nerf_count"] - base["nerf_count"],
            "risk_score_delta": target["risk_score"] - base["risk_score"],
            "role_distribution_changes": role_distribution_changes,
        },
    }


@router.get("/{version}")
def get_patch_overview(version: str, db: Session = Depends(get_db)):
    patch = db.query(Patch).filter(Patch.version == version).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    impacts = (
        db.query(
            Entity.name,
            func.sum(
                case(
                    (Change.direction == ChangeDirection.buff, Change.impact_score),
                    (Change.direction == ChangeDirection.nerf, -Change.impact_score),
                    else_=0.0,
                )
            ).label("impact_score"),
            func.sum(case((Change.direction == ChangeDirection.buff, 1), else_=0)).label(
                "buff_count"
            ),
            func.sum(case((Change.direction == ChangeDirection.nerf, 1), else_=0)).label(
                "nerf_count"
            ),
        )
        .join(Entity, Entity.id == Change.entity_id)
        .filter(
            Change.patch_id == patch.id,
            Entity.entity_type == EntityType.champion,
        )
        .group_by(Entity.name)
        .order_by(desc("impact_score"))
        .all()
    )

    total_buffs = sum(i.buff_count for i in impacts)
    total_nerfs = sum(i.nerf_count for i in impacts)

    entities = [
        {
            "name": i.name,
            "impact_score": i.impact_score,
            "buffs": i.buff_count,
            "nerfs": i.nerf_count,
        }
        for i in impacts
    ]

    return {
        "version": patch.version,
        "release_date": patch.release_date.isoformat(),
        "raw_notes": patch.raw_notes,
        "total_buffs": total_buffs,
        "total_nerfs": total_nerfs,
        "entities": entities,
        "top_impacted": [{"name": e["name"], "score": e["impact_score"]} for e in entities],
    }


@router.get("/{version}/summary-report")
def get_patch_summary_report(version: str, db: Session = Depends(get_db)):
    patch = db.query(Patch).filter(Patch.version == version).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    champion_rollup = (
        db.query(
            Entity.name.label("champion"),
            func.sum(
                case(
                    (Change.direction == ChangeDirection.buff, Change.impact_score),
                    (Change.direction == ChangeDirection.nerf, -Change.impact_score),
                    else_=0.0,
                )
            ).label("net_score"),
            func.sum(case((Change.direction == ChangeDirection.buff, 1), else_=0)).label("buffs"),
            func.sum(case((Change.direction == ChangeDirection.nerf, 1), else_=0)).label("nerfs"),
            func.sum(func.abs(Change.impact_score)).label("volatility"),
        )
        .join(Entity, Entity.id == Change.entity_id)
        .filter(
            Change.patch_id == patch.id,
            Entity.entity_type == EntityType.champion,
        )
        .group_by(Entity.name)
        .all()
    )

    top_5_impacted = [
        {"name": champion, "net_impact_score": float(net_score)}
        for champion, net_score, _buffs, _nerfs, _volatility in sorted(
            champion_rollup, key=lambda row: abs(float(row[1] or 0.0)), reverse=True
        )[:5]
    ]

    volatility_rows = (
        db.query(
            Entity.name.label("champion"),
            Change.stat_name,
            Change.direction,
            Change.impact_score,
            Change.delta_value,
            Change.tags,
        )
        .join(Entity, Entity.id == Change.entity_id)
        .filter(
            Change.patch_id == patch.id,
            Entity.entity_type == EntityType.champion,
        )
        .order_by(desc(Change.impact_score))
        .limit(8)
        .all()
    )
    highest_volatility_changes = [
        {
            "champion": champion,
            "stat_name": stat_name,
            "direction": direction.value,
            "impact_score": float(impact_score),
            "delta_value": float(delta_value) if delta_value is not None else None,
            "tags": tags or [],
        }
        for champion, stat_name, direction, impact_score, delta_value, tags in volatility_rows
    ]

    total_buffs = sum(int(row[2] or 0) for row in champion_rollup)
    total_nerfs = sum(int(row[3] or 0) for row in champion_rollup)
    total_risk = sum(float(row[4] or 0.0) for row in champion_rollup)
    volatility_level = "low"
    if total_risk > 700:
        volatility_level = "high"
    elif total_risk > 300:
        volatility_level = "moderate"
    nerf_pressure = total_nerfs - total_buffs
    balance_tilt = (
        "nerf-heavy"
        if nerf_pressure > 0
        else "buff-heavy"
        if nerf_pressure < 0
        else "balanced"
    )
    risk_analysis = (
        f"Patch {patch.version} appears {volatility_level} volatility with aggregate risk score "
        f"{total_risk:.2f}. The change mix is {balance_tilt} "
        f"(buffs={total_buffs}, nerfs={total_nerfs}), suggesting "
        f"{'meta contraction and safer picks' if nerf_pressure > 0 else 'more aggressive experimentation windows' if nerf_pressure < 0 else 'stable adaptation pressure'}."
    )

    suggested_watch_list = []
    watch_candidates = sorted(
        champion_rollup,
        key=lambda row: (abs(float(row[1] or 0.0)), float(row[4] or 0.0)),
        reverse=True,
    )[:5]
    for champion, net_score, buffs, nerfs, volatility in watch_candidates:
        direction_label = "mixed"
        if net_score > 0:
            direction_label = "upward"
        elif net_score < 0:
            direction_label = "downward"
        suggested_watch_list.append(
            {
                "champion": champion,
                "reason": (
                    f"{direction_label} net impact ({float(net_score):.2f}) with "
                    f"high volatility {float(volatility):.2f} "
                    f"(buffs={int(buffs)}, nerfs={int(nerfs)})."
                ),
            }
        )

    return {
        "version": patch.version,
        "top_5_impacted_champions": top_5_impacted,
        "highest_volatility_changes": highest_volatility_changes,
        "risk_analysis_paragraph": risk_analysis,
        "suggested_watch_list": suggested_watch_list,
    }


@router.get("/{version}/changes")
def get_patch_changes(
    version: str,
    entity_type: Optional[str] = "champion",
    category: Optional[str] = None,
    direction: Optional[str] = None,
    tag: Optional[str] = None,
    entity: Optional[str] = None,
    ability: Optional[str] = None,
    db: Session = Depends(get_db),
):
    requested_version = version.strip()
    patch_exists = db.query(Patch.id).filter(Patch.version == requested_version).first()
    if not patch_exists:
        raise HTTPException(status_code=404, detail="Patch not found")

    query = (
        db.query(
            Change,
            Entity.name.label("entity_name"),
            Entity.entity_type.label("entity_type_value"),
        )
        .join(Entity, Entity.id == Change.entity_id)
        .join(Patch, Patch.id == Change.patch_id)
        .filter(Patch.version == requested_version)
    )

    if entity_type:
        normalized_entity_type = entity_type.strip().lower()
        if normalized_entity_type != "all":
            valid_entity_types = {e.value for e in EntityType}
            if normalized_entity_type not in valid_entity_types:
                raise HTTPException(status_code=400, detail="Invalid entity_type")
            query = query.filter(Entity.entity_type == EntityType(normalized_entity_type))

    if category:
        normalized_category = category.strip().lower()
        valid_categories = {c.value for c in ChangeCategory}
        if normalized_category not in valid_categories:
            raise HTTPException(status_code=400, detail="Invalid category")
        query = query.filter(Change.category == ChangeCategory(normalized_category))

    if direction:
        normalized_direction = direction.strip().lower()
        valid_directions = {d.value for d in ChangeDirection}
        if normalized_direction not in valid_directions:
            raise HTTPException(status_code=400, detail="Invalid direction")
        query = query.filter(Change.direction == ChangeDirection(normalized_direction))

    if tag:
        normalized_tag = tag.strip().lower()
        if normalized_tag:
            query = query.filter(Change.tags.isnot(None), Change.tags.contains([normalized_tag]))

    if entity:
        query = query.filter(Entity.name.ilike(f"%{entity.strip()}%"))

    if ability:
        query = query.filter(Change.ability_slot.ilike(f"%{ability.strip()}%"))

    rows = (
        query.order_by(desc(Change.impact_score), Entity.name.asc(), Change.stat_name.asc(), Change.id.asc()).all()
    )

    return {
        "version": requested_version,
        "filters": {
            "entity_type": entity_type,
            "category": category,
            "direction": direction,
            "tag": tag,
            "entity": entity,
            "ability": ability,
        },
        "count": len(rows),
        "items": [
            {
                "entity": entity_name,
                "entity_type": (
                    entity_type_value.value
                    if hasattr(entity_type_value, "value")
                    else str(entity_type_value)
                ),
                "ability_slot": change.ability_slot,
                "category": change.category.value,
                "direction": change.direction.value,
                "stat_name": change.stat_name,
                "old_value": change.old_value,
                "new_value": change.new_value,
                "delta_value": change.delta_value,
                "impact_score": change.impact_score,
                "tags": change.tags or [],
            }
            for change, entity_name, entity_type_value in rows
        ],
    }


@router.get("/{version}/predicted-impact")
def get_patch_predicted_impact(
    version: str,
    top_n: int = 25,
    db: Session = Depends(get_db),
):
    if top_n < 1 or top_n > 200:
        raise HTTPException(status_code=400, detail="top_n must be between 1 and 200")
    return predict_patch_champion_impacts(db=db, version=version, top_n=top_n)


@router.get("/{version}/distribution")
def get_patch_distribution(version: str, db: Session = Depends(get_db)):
    patch = db.query(Patch).filter(Patch.version == version).first()
    if not patch:
        raise HTTPException(status_code=404, detail="Patch not found")

    grouped = (
        db.query(
            Entity.name.label("champion"),
            func.sum(
                case(
                    (Change.direction == ChangeDirection.buff, Change.impact_score),
                    (Change.direction == ChangeDirection.nerf, -Change.impact_score),
                    else_=0.0,
                )
            ).label("value"),
            func.sum(case((Change.direction == ChangeDirection.buff, 1), else_=0)).label(
                "buffs"
            ),
            func.sum(case((Change.direction == ChangeDirection.nerf, 1), else_=0)).label(
                "nerfs"
            ),
        )
        .join(Entity, Entity.id == Change.entity_id)
        .filter(
            Change.patch_id == patch.id,
            Entity.entity_type == EntityType.champion,
        )
        .group_by(Entity.name)
        .order_by(desc("value"))
        .all()
    )

    return {
        "version": patch.version,
        "metric": "net_impact_score",
        "items": [
            {
                "champion": champion,
                "value": value,
                "buffs": buffs,
                "nerfs": nerfs,
            }
            for champion, value, buffs, nerfs in grouped
        ],
    }

