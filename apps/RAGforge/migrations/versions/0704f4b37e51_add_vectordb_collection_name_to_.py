"""add vectordb_collection_name to collections

Revision ID: 0704f4b37e51
Revises: 9cb41eb836ac
Create Date: 2025-10-03 09:27:10.187007

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0704f4b37e51'
down_revision: Union[str, None] = '9cb41eb836ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'collections',
        sa.Column('vectordb_collection_name', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('collections', 'vectordb_collection_name')

