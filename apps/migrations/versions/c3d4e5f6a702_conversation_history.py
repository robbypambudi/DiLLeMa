"""Add private conversations and durable question/answer turns.

Revision ID: c3d4e5f6a702
Revises: b2d3e4f5a601
"""

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a702"
down_revision = "b2d3e4f5a601"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("collection_name", sa.String(255), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_conversations_user_updated", "conversations", ["user_id", "updated_at"]
    )
    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("question_id", sa.String(255), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "conversation_id", "question_id", name="uq_conversation_request"
        ),
        sa.UniqueConstraint(
            "conversation_id", "sequence", name="uq_conversation_sequence"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed', 'interrupted')",
            name="ck_conversation_turn_status",
        ),
    )


def downgrade():
    op.drop_table("conversation_turns")
    op.drop_index("ix_conversations_user_updated", table_name="conversations")
    op.drop_table("conversations")
