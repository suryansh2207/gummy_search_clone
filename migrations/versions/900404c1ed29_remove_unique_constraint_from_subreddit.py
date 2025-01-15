"""Remove unique constraint from subreddit

Revision ID: 900404c1ed29
Revises: 27cfdb9ea971
Create Date: 2025-01-15 12:56:27.244120

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '900404c1ed29'
down_revision = '27cfdb9ea971'
branch_labels = None
depends_on = None

def upgrade():
    # SQLite requires table recreation for constraint removal
    with op.batch_alter_table('audience') as batch_op:
        # Create new table without constraint
        batch_op.drop_constraint('uq_audience_subreddit', type_='unique')

def downgrade():
    with op.batch_alter_table('audience') as batch_op:
        batch_op.create_unique_constraint('uq_audience_subreddit', ['subreddit'])

    # ### end Alembic commands ###
