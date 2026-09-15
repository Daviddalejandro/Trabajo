"""F5 · validación con fuentes adicionales: landing zone del sistema de crédito (CREDITO_CORE).

Revision ID: f5_0004
Revises: f3_0003
"""
from alembic import op

revision = "f5_0004"
down_revision = "f3_0003"
branch_labels = None
depends_on = None

DDL = """
CREATE TABLE staging.stg_credito_core_raw (
    raw_sk        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id      BIGINT NOT NULL REFERENCES staging.load_batch(batch_id),
    external_id   VARCHAR(80) NOT NULL,
    payload       JSONB NOT NULL,
    source_hash   CHAR(64) NOT NULL,
    raw_status    VARCHAR(16) NOT NULL DEFAULT 'PENDING'
                  CHECK (raw_status IN ('PENDING','STANDARDIZED','HOMOLOGATED','DQ_PASSED','DQ_QUARANTINE','LOADED','UNCHANGED')),
    standardized  JSONB,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ
);
CREATE INDEX ix_stg_credito_core_ext ON staging.stg_credito_core_raw(external_id, source_hash);
CREATE INDEX ix_stg_credito_core_batch ON staging.stg_credito_core_raw(batch_id, raw_status);
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS staging.stg_credito_core_raw")
