"""create relation files to collection

Revision ID: 7edaee427a22
Revises: 6c0ae0d0b44d
Create Date: 2025-05-06 04:13:21.861115

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7edaee427a22'
down_revision: Union[str, None] = '6c0ae0d0b44d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_foreign_key(
        'fk_files_collections',
        'files',
        'collections',
        ['collection_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_files_collections', 'files', type_='foreignkey')
