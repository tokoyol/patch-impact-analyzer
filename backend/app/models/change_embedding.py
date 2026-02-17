from datetime import datetime
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ChangeEmbedding(Base):
    __tablename__ = "change_embeddings"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    change_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("changes.id", ondelete="CASCADE"), unique=True, index=True
    )

    embedding: Mapped[list[float]] = mapped_column(Vector(768))
    search_text: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String, default="ollama")
    model: Mapped[str] = mapped_column(String)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    change = relationship("Change", back_populates="embedding")
