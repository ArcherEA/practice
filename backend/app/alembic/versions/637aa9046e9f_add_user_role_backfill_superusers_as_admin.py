"""add user.role (member default), backfill superusers as admin

Revision ID: 637aa9046e9f
Revises: fe56fa70289e
Create Date: 2026-11-22 20:00:23.672777

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '637aa9046e9f'
down_revision = 'fe56fa70289e'
branch_labels = None
depends_on = None


def upgrade():
    # Plain VARCHAR, not a Postgres ENUM: adding roles later needs no enum migration.
    op.add_column('user', sa.Column('role', sa.String(length=20), server_default='member', nullable=False))
    # Existing superusers (owners) become admins; everyone else stays member.
    op.execute('UPDATE "user" SET role = \'admin\' WHERE is_superuser')


def downgrade():
    op.drop_column('user', 'role')
