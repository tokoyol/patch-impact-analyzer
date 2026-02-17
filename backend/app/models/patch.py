from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import Date, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Patch(Base):
    __tablename__ = "patches"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    version: Mapped[str] = mapped_column(String, index=True, unique=True)
    release_date: Mapped[date] = mapped_column(Date)
    raw_notes: Mapped[str] = mapped_column(Text)

    changes = relationship("Change", back_populates="patch")
    patch_entity_impacts = relationship("PatchEntityImpact", back_populates="patch")

