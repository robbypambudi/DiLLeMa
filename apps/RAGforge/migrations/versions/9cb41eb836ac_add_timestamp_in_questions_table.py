"""add timestamp in questions table

Revision ID: 9cb41eb836ac
Revises: 33d80ab3d051
Create Date: 2025-05-13 10:11:33.376971

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9cb41eb836ac'
down_revision: Union[str, None] = '33d80ab3d051'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))
        batch_op.alter_column("created_at", existing_type=sa.DateTime(), nullable=False)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_column("created_at")
        batch_op.drop_column("updated_at")
