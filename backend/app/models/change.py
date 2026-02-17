import enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

from sqlalchemy import Enum, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ChangeCategory(enum.Enum):
    damage = "damage"
    cooldown = "cooldown"
    base_stat = "base_stat"
    scaling = "scaling"
    cost = "cost"
    mechanic = "mechanic"


class ChangeDirection(enum.Enum):
    buff = "buff"
    nerf = "nerf"
    adjustment = "adjustment"


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    patch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patches.id"))
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("entities.id"))

    category: Mapped[ChangeCategory] = mapped_column(Enum(ChangeCategory))
    stat_name: Mapped[str] = mapped_column(String)
    ability_slot: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    old_value: Mapped[Union[Dict[str, Any], float]] = mapped_column(JSONB)
    new_value: Mapped[Union[Dict[str, Any], float]] = mapped_column(JSONB)

    delta_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delta_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    direction: Mapped[ChangeDirection] = mapped_column(Enum(ChangeDirection))

    impact_weight: Mapped[float] = mapped_column(Float)
    impact_score: Mapped[float] = mapped_column(Float)

    tags: Mapped[Optional[List[str]]] = mapped_column(JSONB, nullable=True)

    patch = relationship("Patch", back_populates="changes")
    entity = relationship("Entity", back_populates="changes")
    embedding = relationship("ChangeEmbedding", back_populates="change", uselist=False)

