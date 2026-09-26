"""add users table (production authentication)

Revision ID: a7c1d9e2b4f6
Revises: 8124b0c262db
Create Date: 2026-09-26 00:00:00.000000

Phase 8 (product-finishing pass): persistent application-user accounts.

- Passwords are stored ONLY as bcrypt hashes (column password_hash).
- role is resolved server-side on every request (RBAC).
- token_version allows global revocation of previously issued JWTs.
- reset_token_hash stores the SHA-256 of an opaque single-use reset token.

The baseline and Phase 6 migrations are NOT modified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a7c1d9e2b4f6'
down_revision: Union[str, Sequence[str], None] = '8124b0c262db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False, server_default='Viewer'),
        sa.Column('organization', sa.String(length=200), nullable=True),
        sa.Column('site', sa.String(length=100), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('reset_token_hash', sa.String(length=64), nullable=True),
        sa.Column('reset_token_expires_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_users_id', 'users', ['id'])
    op.create_index('ix_users_email', 'users', ['email'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_id', table_name='users')
    op.drop_table('users')
