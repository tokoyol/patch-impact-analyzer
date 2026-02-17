import enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class EntityType(enum.Enum):
    champion = "champion"
    item = "item"
    system = "system"


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, index=True, unique=True)
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType))
    primary_role: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    changes = relationship("Change", back_populates="entity")
    patch_entity_impacts = relationship("PatchEntityImpact", back_populates="entity")

