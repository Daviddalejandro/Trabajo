"""Consola RDM · campos personalizados por catálogo y auditoría completa de las cinco capas.

CATALOG_ATTRIBUTE define qué atributos (campos personalizados) lleva cada valor de un catálogo: código, nombre,
tipo de dato y obligatoriedad. Los valores los guarda REFERENCE_FIELD_VALUE (EAV, SPEC §5.1); esta tabla es su
diccionario. Se poblan desde el EAV existente para que los catálogos ya sembrados (tipo de documento, tipo de
relación, DIVIPOLA…) muestren sus campos. Además, DOMAIN, SOURCE_SYSTEM, CATALOG_SOURCE_INTEGRATION y
CATALOG_ATTRIBUTE pasan a auditarse con el mismo trigger genérico (Ley 1581/2012 art. 17; DAMA-DMBOK2 Cap. 10).

Revision ID: f7_0008
Revises: f6_0007
"""
from alembic import op

revision = "f7_0008"
down_revision = "f6_0007"
branch_labels = None
depends_on = None

DDL = r"""
CREATE TABLE rdm.catalog_attribute (
    attribute_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    catalog_sk   BIGINT NOT NULL REFERENCES rdm.catalog(catalog_sk),
    field_code   VARCHAR(60)  NOT NULL,
    field_name   VARCHAR(160) NOT NULL,
    data_type    VARCHAR(20)  NOT NULL DEFAULT 'TEXT',
    is_required  BOOLEAN NOT NULL DEFAULT FALSE,
    description  VARCHAR(300),
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from   TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to     TIMESTAMPTZ,
    CONSTRAINT ux_catalog_attribute UNIQUE (catalog_sk, field_code),
    CONSTRAINT ck_catalog_attribute_type CHECK (data_type IN ('TEXT', 'NUMBER', 'BOOLEAN', 'DATE', 'REGEX', 'CODE'))
);

-- Diccionario inicial a partir del EAV ya sembrado: un campo por (catálogo, field_code), con el tipo inferido.
INSERT INTO rdm.catalog_attribute (catalog_sk, field_code, field_name, data_type)
SELECT c.catalog_sk, f.field_code, f.field_code,
       CASE WHEN bool_and(f.field_value IN ('true', 'false')) THEN 'BOOLEAN'
            WHEN bool_and(f.field_value ~ '^-?[0-9]+(\.[0-9]+)?$') THEN 'NUMBER'
            WHEN f.field_code ILIKE '%regex%' THEN 'REGEX'
            WHEN bool_and(f.field_value ~ '^[A-Z][A-Z0-9_]*$') THEN 'CODE'
            ELSE 'TEXT' END
FROM rdm.reference_field_value f
JOIN rdm.reference_value v ON v.value_sk = f.value_sk
JOIN rdm.catalog c ON c.catalog_sk = v.catalog_sk
GROUP BY c.catalog_sk, f.field_code;

-- Auditoría genérica ampliada a las cinco capas del RDM
CREATE OR REPLACE FUNCTION rdm.fn_audit() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE pk BIGINT;
BEGIN
    pk := CASE TG_TABLE_NAME
            WHEN 'reference_value'            THEN (to_jsonb(COALESCE(NEW, OLD))->>'value_sk')::BIGINT
            WHEN 'catalog'                    THEN (to_jsonb(COALESCE(NEW, OLD))->>'catalog_sk')::BIGINT
            WHEN 'source_value_mapping'       THEN (to_jsonb(COALESCE(NEW, OLD))->>'mapping_sk')::BIGINT
            WHEN 'reference_field_value'      THEN (to_jsonb(COALESCE(NEW, OLD))->>'field_value_sk')::BIGINT
            WHEN 'domain'                     THEN (to_jsonb(COALESCE(NEW, OLD))->>'domain_sk')::BIGINT
            WHEN 'source_system'              THEN (to_jsonb(COALESCE(NEW, OLD))->>'source_system_sk')::BIGINT
            WHEN 'catalog_source_integration' THEN (to_jsonb(COALESCE(NEW, OLD))->>'integration_sk')::BIGINT
            WHEN 'catalog_attribute'          THEN (to_jsonb(COALESCE(NEW, OLD))->>'attribute_sk')::BIGINT
          END;
    INSERT INTO rdm.rdm_audit_log(entity, entity_sk, action, old_value, new_value, actor)
    VALUES (upper(TG_TABLE_NAME), pk, TG_OP,
            CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD)::text END,
            CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW)::text END,
            rdm.fn_actor());
    RETURN COALESCE(NEW, OLD);
END $$;
CREATE TRIGGER trg_audit_domain AFTER INSERT OR UPDATE OR DELETE ON rdm.domain
    FOR EACH ROW EXECUTE FUNCTION rdm.fn_audit();
CREATE TRIGGER trg_audit_source_system AFTER INSERT OR UPDATE OR DELETE ON rdm.source_system
    FOR EACH ROW EXECUTE FUNCTION rdm.fn_audit();
CREATE TRIGGER trg_audit_catalog_source_integration AFTER INSERT OR UPDATE OR DELETE ON rdm.catalog_source_integration
    FOR EACH ROW EXECUTE FUNCTION rdm.fn_audit();
CREATE TRIGGER trg_audit_catalog_attribute AFTER INSERT OR UPDATE OR DELETE ON rdm.catalog_attribute
    FOR EACH ROW EXECUTE FUNCTION rdm.fn_audit();
"""

DROP = """
DROP TRIGGER IF EXISTS trg_audit_catalog_attribute ON rdm.catalog_attribute;
DROP TRIGGER IF EXISTS trg_audit_catalog_source_integration ON rdm.catalog_source_integration;
DROP TRIGGER IF EXISTS trg_audit_source_system ON rdm.source_system;
DROP TRIGGER IF EXISTS trg_audit_domain ON rdm.domain;
DROP TABLE IF EXISTS rdm.catalog_attribute;
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute(DROP)
