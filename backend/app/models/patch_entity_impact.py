from uuid import UUID, uuid4

from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class PatchEntityImpact(Base):
    __tablename__ = "patch_entity_impacts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    patch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("patches.id"))
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("entities.id"))

    total_impact_score: Mapped[float] = mapped_column(Float)
    buff_count: Mapped[int] = mapped_column(Integer)
    nerf_count: Mapped[int] = mapped_column(Integer)
    adjustment_count: Mapped[int] = mapped_column(Integer)

    patch = relationship("Patch", back_populates="patch_entity_impacts")
    entity = relationship("Entity", back_populates="patch_entity_impacts")

