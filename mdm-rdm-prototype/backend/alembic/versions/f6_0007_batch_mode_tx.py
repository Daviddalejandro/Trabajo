"""Vitrina/cargas · LOAD_BATCH.mode admite TX (carga transaccional de un registro por API).

Revision ID: f6_0007
Revises: f6_0006
"""
from alembic import op

revision = "f6_0007"
down_revision = "f6_0006"
branch_labels = None
depends_on = None

MODES_NEW = "('FULL','DELTA','TX','RNE_SYNC','REHOMOLOGATE','MATCH')"
MODES_OLD = "('FULL','DELTA','RNE_SYNC','REHOMOLOGATE','MATCH')"


def _swap_check(modes: str) -> None:
    op.execute("""
        DO $$
        DECLARE c text;
        BEGIN
          SELECT conname INTO c FROM pg_constraint
           WHERE conrelid = 'staging.load_batch'::regclass AND contype = 'c' AND pg_get_constraintdef(oid) ILIKE '%mode%';
          IF c IS NOT NULL THEN EXECUTE format('ALTER TABLE staging.load_batch DROP CONSTRAINT %I', c); END IF;
        END $$;""")
    op.execute(f"ALTER TABLE staging.load_batch ADD CONSTRAINT load_batch_mode_check CHECK (mode IN {modes})")


def upgrade() -> None:
    _swap_check(MODES_NEW)


def downgrade() -> None:
    _swap_check(MODES_OLD)
