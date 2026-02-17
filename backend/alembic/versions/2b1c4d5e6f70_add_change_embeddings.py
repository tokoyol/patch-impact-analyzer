"""add change embeddings

Revision ID: 2b1c4d5e6f70
Revises: f974a8d18adb
Create Date: 2026-02-13 20:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2b1c4d5e6f70"
down_revision: Union[str, Sequence[str], None] = "f974a8d18adb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "change_embeddings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("change_id", sa.UUID(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column("search_text", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["change_id"], ["changes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_change_embeddings_change_id"), "change_embeddings", ["change_id"], unique=True)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_change_embeddings_embedding ON change_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_change_embeddings_embedding")
    op.drop_index(op.f("ix_change_embeddings_change_id"), table_name="change_embeddings")
    op.drop_table("change_embeddings")
