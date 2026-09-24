"""add report_embeddings (pgvector-ready)

Revision ID: e5d4d8238ea9
Revises: 52f4c7b68fb8
Create Date: 2026-09-25 00:00:00.000000

Phase 6 Batch 2: vector-ready persistence for report description embeddings.

Dialect handling:
- PostgreSQL: enables the pgvector extension and creates a real vector(dim)
  column plus an HNSW cosine index, when pgvector is available on the server.
  If the extension cannot be enabled (pgvector not installed server-side), the
  migration degrades to a portable non-vector column so schema deployment still
  succeeds; similarity search then falls back to the application layer.
- SQLite (local/demo): creates the same table with a TEXT embedding column.
  No pgvector extension, no PostgreSQL-specific DDL. SQLite mode continues to
  work without pgvector installed.

SAFETY BOUNDARY: this table intentionally contains NO safety fields. Vector
similarity is advisory metadata for retrieval/search/pattern discovery only;
all safety decisions remain exclusively deterministic.

The Batch 1 baseline migration (52f4c7b68fb8) is NOT modified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector  # available: pgvector is a project dependency
except ImportError:  # pragma: no cover
    Vector = None

# revision identifiers, used by Alembic.
revision: str = 'e5d4d8238ea9'
down_revision: Union[str, Sequence[str], None] = '52f4c7b68fb8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Canonical infrastructure dimension (model-agnostic; the embedding model
# itself is intentionally deferred — no model ships in this batch).
EMBEDDING_DIM = 768


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _pgvector_available(conn) -> bool:
    """Check whether the pgvector extension is installable on this server."""
    try:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        conn.exec_driver_sql("SELECT '[0,1]'::vector")
        return True
    except Exception:
        return False


def upgrade() -> None:
    conn = op.get_bind()
    is_pg = _is_postgresql()

    use_vector_type = False
    if is_pg:
        use_vector_type = _pgvector_available(conn)

    if is_pg and use_vector_type:
        # Real pgvector column with dimension guard + HNSW cosine index.
        embedding_type = Vector(EMBEDDING_DIM) if Vector is not None else sa.Text()
        op.create_table(
            'report_embeddings',
            sa.Column('report_id', sa.String(length=64), primary_key=True),
            sa.Column('model_id', sa.String(length=128), primary_key=True),
            sa.Column('embedding', embedding_type, nullable=True),
            sa.Column('dim', sa.Integer(), nullable=False, server_default=str(EMBEDDING_DIM)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['report_id'], ['reports.report_id'], ondelete='CASCADE'),
        )
        op.create_index(
            'uq_report_embeddings_report_model',
            'report_embeddings',
            ['report_id', 'model_id'],
            unique=True,
        )
        op.create_index(
            'ix_report_embeddings_hnsw_cosine',
            'report_embeddings',
            ['embedding'],
            postgresql_using='hnsw',
            postgresql_ops={'embedding': 'vector_cosine_ops'},
        )
        op.create_index('ix_report_embeddings_model_id', 'report_embeddings', ['model_id'])
    else:
        # Portable variant: SQLite local/demo mode, or PostgreSQL without the
        # pgvector extension available. Same relational shape; embedding stored
        # as TEXT (e.g. JSON array) until pgvector is enabled, after which a
        # follow-up migration can convert the column type in place.
        op.create_table(
            'report_embeddings',
            sa.Column('report_id', sa.String(length=64), primary_key=True),
            sa.Column('model_id', sa.String(length=128), primary_key=True),
            sa.Column('embedding', sa.Text(), nullable=True),
            sa.Column('dim', sa.Integer(), nullable=False, server_default=str(EMBEDDING_DIM)),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['report_id'], ['reports.report_id'], ondelete='CASCADE'),
        )
        op.create_index(
            'uq_report_embeddings_report_model',
            'report_embeddings',
            ['report_id', 'model_id'],
            unique=True,
        )
        op.create_index('ix_report_embeddings_model_id', 'report_embeddings', ['model_id'])


def downgrade() -> None:
    op.drop_index('ix_report_embeddings_model_id', table_name='report_embeddings')
    op.drop_index('uq_report_embeddings_report_model', table_name='report_embeddings')
    op.drop_table('report_embeddings')
    if _is_postgresql():
        # Best-effort extension cleanup is intentionally skipped: dropping the
        # extension could affect other databases/objects sharing it.
        pass
