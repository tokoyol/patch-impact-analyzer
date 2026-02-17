"""add system entity type

Revision ID: 7c31f85f1e2a
Revises: 2b1c4d5e6f70
Create Date: 2026-02-16 10:20:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c31f85f1e2a"
down_revision: Union[str, Sequence[str], None] = "2b1c4d5e6f70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE entitytype ADD VALUE IF NOT EXISTS 'system'")


def downgrade() -> None:
    # PostgreSQL enum value removal is destructive and not safely reversible.
    # Keep downgrade as a no-op.
    pass
