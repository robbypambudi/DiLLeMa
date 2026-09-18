"""Store cited sources per conversation turn.

Revision ID: d4e5f6a70311
Revises: c3d4e5f6a702
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a70311"
down_revision = "c3d4e5f6a702"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversation_turns",
        sa.Column(
            "sources",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade():
    op.drop_column("conversation_turns", "sources")
