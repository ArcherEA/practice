"""add usernames bio follows and notifications

Revision ID: bddc69df7d01
Revises: 3bc38c2c4d70
Create Date: 2026-11-23 17:39:39.470260

"""
import re
from collections.abc import Iterator

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'bddc69df7d01'
down_revision = '3bc38c2c4d70'
branch_labels = None
depends_on = None

# --- username backfill -------------------------------------------------------
# A frozen copy of the rules in app/core/usernames.py (a migration must not depend on
# application code that changes later). `backfill_usernames` is pure; tests import it.

USERNAME_MIN = 3
USERNAME_MAX = 30
RESERVED = frozenset({
    "admin", "administrator", "api", "blog", "content", "community", "settings",
    "login", "signup", "logout", "p", "u", "moderation", "notifications", "root",
    "support", "help", "me", "null", "undefined",
})


def _slugify(raw):
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", raw.lower())).strip("_")


def _base(full_name, email):
    base = _slugify(full_name or "") or _slugify(email.split("@", 1)[0]) or "user"
    base = base[:USERNAME_MAX].rstrip("_")
    return base.ljust(USERNAME_MIN, "0")


def _candidates(base) -> Iterator[str]:
    yield base
    n = 2
    while True:
        suffix = f"_{n}"
        yield f"{base[: USERNAME_MAX - len(suffix)].rstrip('_')}{suffix}"
        n += 1


def backfill_usernames(rows):
    """`[(id, full_name, email)]` in creation order -> `{id: username}` (unique, valid)."""
    taken = set()
    result = {}
    for user_id, full_name, email in rows:
        for name in _candidates(_base(full_name, email)):
            if name not in RESERVED and name not in taken:
                break
        taken.add(name)
        result[user_id] = name
    return result


def upgrade():
    op.create_table('user_follow',
    sa.Column('follower_id', sa.Uuid(), nullable=False),
    sa.Column('followee_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.CheckConstraint('follower_id <> followee_id', name='ck_user_follow_not_self'),
    sa.ForeignKeyConstraint(['followee_id'], ['user.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['follower_id'], ['user.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('follower_id', 'followee_id')
    )
    op.create_index(op.f('ix_user_follow_followee_id'), 'user_follow', ['followee_id'], unique=False)
    op.create_table('notification',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('recipient_id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.String(length=30), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('comment_id', sa.Uuid(), nullable=True),
    sa.Column('post_id', sa.Uuid(), nullable=True),
    sa.Column('page_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=False),
    sa.Column('read_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True),
    sa.ForeignKeyConstraint(['actor_id'], ['user.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['comment_id'], ['comment.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['page_id'], ['page.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['post_id'], ['post.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['recipient_id'], ['user.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_created_at'), 'notification', ['created_at'], unique=False)
    op.create_index('ix_notification_recipient_created', 'notification', ['recipient_id', 'created_at'], unique=False)
    # username: add as nullable, fill existing users, then make it NOT NULL + unique.
    op.add_column('user', sa.Column('username', sqlmodel.sql.sqltypes.AutoString(length=30), nullable=True))
    op.add_column('user', sa.Column('username_changed_at', sqlmodel.sql.sqltypes.UTCDateTime(), nullable=True))
    op.add_column('user', sa.Column('bio', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True))
    user = sa.table(
        'user',
        sa.column('id', sa.Uuid()),
        sa.column('email', sa.String()),
        sa.column('full_name', sa.String()),
        sa.column('created_at', sa.DateTime()),
        sa.column('username', sa.String()),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(user.c.id, user.c.full_name, user.c.email).order_by(
            user.c.created_at.asc().nulls_last(), user.c.id
        )
    ).all()
    names = backfill_usernames([(row.id, row.full_name, row.email) for row in rows])
    for user_id, name in names.items():
        connection.execute(
            user.update().where(user.c.id == user_id).values(username=name)
        )
    op.alter_column('user', 'username', existing_type=sqlmodel.sql.sqltypes.AutoString(length=30), nullable=False)
    op.create_index(op.f('ix_user_username'), 'user', ['username'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_user_username'), table_name='user')
    op.drop_column('user', 'bio')
    op.drop_column('user', 'username_changed_at')
    op.drop_column('user', 'username')
    op.drop_index('ix_notification_recipient_created', table_name='notification')
    op.drop_index(op.f('ix_notification_created_at'), table_name='notification')
    op.drop_table('notification')
    op.drop_index(op.f('ix_user_follow_followee_id'), table_name='user_follow')
    op.drop_table('user_follow')
