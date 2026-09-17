"""create_questions_table

Revision ID: 33d80ab3d051
Revises: 7edaee427a22
Create Date: 2025-05-12 13:03:16.422248

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '33d80ab3d051'
down_revision: Union[str, None] = '7edaee427a22'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'questions',
        sa.Column('id', sa.UUID, primary_key=True),
        sa.Column('question_id', sa.String(255), nullable=False),
        sa.Column('question_text', sa.Text(), nullable=False),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('collection_id', sa.UUID, nullable=False),
        sa.ForeignKeyConstraint(['collection_id'], ['collections.id'], ondelete='CASCADE'),
    )
    op.create_index(op.f('ix_questions_question_id'), 'questions', ['question_id'], unique=False)
    op.create_index(op.f('ix_questions_collection_id'), 'questions', ['collection_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_questions_collection_id'), table_name='questions')
    op.drop_index(op.f('ix_questions_question_id'), table_name='questions')
    op.drop_table('questions')
