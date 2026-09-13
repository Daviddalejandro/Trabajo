"""F3 · ajustes para matching: LOAD_BATCH admite lotes sin fuente (modo MATCH)

Revision ID: f3_0003
Revises: f2_0002
Create Date: 2026-09-13
"""
from alembic import op

revision = "f3_0003"
down_revision = "f2_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE staging.load_batch ALTER COLUMN source_system_cd DROP NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS ix_party_match_status ON mdm.party_match(match_status, decision_cd)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS mdm.ix_party_match_status")
    op.execute("ALTER TABLE staging.load_batch ALTER COLUMN source_system_cd SET NOT NULL")
