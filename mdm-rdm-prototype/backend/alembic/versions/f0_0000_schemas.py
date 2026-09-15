"""F0 · esquemas rdm, mdm, staging y extensión pg_trgm (SPEC §4, §5.4)

Revision ID: f0_0000
Revises:
Create Date: 2026-09-13
"""
from alembic import op

revision = "f0_0000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS rdm")
    op.execute("CREATE SCHEMA IF NOT EXISTS mdm")
    op.execute("CREATE SCHEMA IF NOT EXISTS staging")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS staging CASCADE")
    op.execute("DROP SCHEMA IF EXISTS mdm CASCADE")
    op.execute("DROP SCHEMA IF EXISTS rdm CASCADE")
