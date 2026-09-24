"""widen_sif_potential_to_varchar_10

Revision ID: 8124b0c262db
Revises: e5d4d8238ea9
Create Date: 2026-09-25 03:18:26.329733

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8124b0c262db'
down_revision: Union[str, Sequence[str], None] = 'e5d4d8238ea9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: widen reports.sif_potential from VARCHAR(3) to VARCHAR(10)."""
    with op.batch_alter_table('reports') as batch_op:
        batch_op.alter_column(
            'sif_potential',
            existing_type=sa.String(length=3),
            type_=sa.String(length=10),
            existing_nullable=False,
        )


def downgrade() -> None:
    """
    Downgrade schema: restore reports.sif_potential to VARCHAR(3).

    Safety guard: checks whether any records have values longer than 3 characters
    (such as 'UNKNOWN'). Refuses to downgrade if data would be truncated or lost.
    """
    bind = op.get_bind()
    count = bind.execute(
        sa.text("SELECT count(*) FROM reports WHERE length(sif_potential) > 3")
    ).scalar()
    if count and count > 0:
        raise ValueError(
            f"Cannot downgrade reports.sif_potential to VARCHAR(3): {count} rows contain "
            f"values longer than 3 characters (e.g. 'UNKNOWN'). Data would be truncated."
        )
    with op.batch_alter_table('reports') as batch_op:
        batch_op.alter_column(
            'sif_potential',
            existing_type=sa.String(length=10),
            type_=sa.String(length=3),
            existing_nullable=False,
        )
