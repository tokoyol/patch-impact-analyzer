from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Change, Entity, Patch, PatchEntityImpact
from app.models.change import ChangeCategory, ChangeDirection
from app.models.entity import EntityType


def compute_impact(category: ChangeCategory, delta: float) -> float:
    weights = {
        ChangeCategory.damage: 2.0,
        ChangeCategory.cooldown: 3.0,
        ChangeCategory.base_stat: 1.5,
        ChangeCategory.scaling: 2.5,
        ChangeCategory.cost: 1.5,
        ChangeCategory.mechanic: 4.0,
    }

    weight = weights.get(category, 1.0)
    magnitude = abs(delta)
    return weight * magnitude


def seed() -> None:
    db: Session = SessionLocal()
    try:
        patch = db.execute(select(Patch).where(Patch.version == "14.1")).scalar_one_or_none()
        if patch is None:
            patch = Patch(
                version="14.1",
                release_date=date(2025, 1, 10),
                raw_notes="Ahri Q damage increased. Cooldown reduced.",
            )
            db.add(patch)
            db.flush()
        else:
            patch.release_date = date(2025, 1, 10)
            patch.raw_notes = "Ahri Q damage increased. Cooldown reduced."

        ahri = db.execute(select(Entity).where(Entity.name == "Ahri")).scalar_one_or_none()
        if ahri is None:
            ahri = Entity(
                name="Ahri",
                entity_type=EntityType.champion,
                primary_role="mid",
            )
            db.add(ahri)
            db.flush()
        else:
            ahri.entity_type = EntityType.champion
            ahri.primary_role = "mid"

        # Make the script deterministic by replacing prior rows for this pair.
        db.execute(
            delete(Change).where(
                Change.patch_id == patch.id,
                Change.entity_id == ahri.id,
            )
        )
        db.execute(
            delete(PatchEntityImpact).where(
                PatchEntityImpact.patch_id == patch.id,
                PatchEntityImpact.entity_id == ahri.id,
            )
        )

        damage_delta = 10.0
        damage_impact = compute_impact(ChangeCategory.damage, damage_delta)
        change1 = Change(
            patch_id=patch.id,
            entity_id=ahri.id,
            category=ChangeCategory.damage,
            stat_name="Q Damage",
            ability_slot="Q",
            old_value=40,
            new_value=50,
            delta_value=damage_delta,
            delta_percent=25.0,
            direction=ChangeDirection.buff,
            impact_weight=2.0,
            impact_score=damage_impact,
            tags={"phase": "early_game"},
        )

        cooldown_delta = -2.0
        cooldown_impact = compute_impact(ChangeCategory.cooldown, cooldown_delta)
        change2 = Change(
            patch_id=patch.id,
            entity_id=ahri.id,
            category=ChangeCategory.cooldown,
            stat_name="Q Cooldown",
            ability_slot="Q",
            old_value=9,
            new_value=7,
            delta_value=cooldown_delta,
            delta_percent=-22.0,
            direction=ChangeDirection.buff,
            impact_weight=3.0,
            impact_score=cooldown_impact,
            tags={"phase": "tempo"},
        )

        db.add_all([change1, change2])
        db.flush()

        patch_impact = PatchEntityImpact(
            patch_id=patch.id,
            entity_id=ahri.id,
            total_impact_score=damage_impact + cooldown_impact,
            buff_count=2,
            nerf_count=0,
            adjustment_count=0,
        )
        db.add(patch_impact)

        db.commit()
        print("Seed completed successfully.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()

