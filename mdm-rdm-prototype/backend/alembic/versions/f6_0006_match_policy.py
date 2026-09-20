"""Política de matching versionada (SPEC §8 · v2): grupos de suficiencia, umbrales sobre evidencia
normalizada, cobertura mínima y vetos por identificador. Cada cambio crea una versión nueva (nunca se
edita la publicada, mismo principio que el RDM §3.7); PARTY_MATCH guarda la base de la decisión.

Revision ID: f6_0006
Revises: f5_0005
"""
from alembic import op

revision = "f6_0006"
down_revision = "f5_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE mdm.match_policy (
            policy_sk      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            entity_type_cd BIGINT NOT NULL REFERENCES rdm.reference_value(value_sk),
            version        INT NOT NULL,
            params         JSONB NOT NULL,
            is_active      BOOLEAN NOT NULL DEFAULT TRUE,
            note           TEXT,
            created_by     VARCHAR(120) NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ux_match_policy_version UNIQUE (entity_type_cd, version)
        );
        CREATE UNIQUE INDEX ux_match_policy_active ON mdm.match_policy(entity_type_cd) WHERE is_active;
        CREATE TRIGGER trg_audit_match_policy AFTER INSERT OR UPDATE OR DELETE ON mdm.match_policy
            FOR EACH ROW EXECUTE FUNCTION mdm.fn_audit('policy_sk');
        ALTER TABLE mdm.party_match ADD COLUMN decision_basis JSONB;
        COMMENT ON COLUMN mdm.party_match.decision_basis IS
            'Evidencia normalizada, cobertura, grupos evaluados, vetos y versión de la política que decidió (SPEC §8 v2)';
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE mdm.party_match DROP COLUMN IF EXISTS decision_basis;
        DROP TABLE IF EXISTS mdm.match_policy;
    """)
