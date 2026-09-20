"""F1 · esquema rdm: 5 capas, miembros técnicos, vistas, triggers (SPEC §5.1, §3, §5.4)

Revision ID: f1_0001
Revises: f0_0000
Create Date: 2026-09-13
"""
from alembic import op

revision = "f1_0001"
down_revision = "f0_0000"
branch_labels = None
depends_on = None

DDL = r"""
-- =============================================================== Master Data
CREATE TABLE rdm.domain (
    domain_sk    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain_code  VARCHAR(40)  NOT NULL UNIQUE,
    domain_name  VARCHAR(120) NOT NULL
);

CREATE TABLE rdm.catalog (
    catalog_sk      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    domain_sk       BIGINT NOT NULL REFERENCES rdm.domain(domain_sk),
    catalog_code    VARCHAR(60)  NOT NULL UNIQUE,
    catalog_name    VARCHAR(160) NOT NULL,
    official_source VARCHAR(120),
    is_hierarchical BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE rdm.reference_value (
    value_sk        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    catalog_sk      BIGINT REFERENCES rdm.catalog(catalog_sk),
    value_code      VARCHAR(60)  NOT NULL,
    value_name      VARCHAR(200) NOT NULL,
    parent_value_sk BIGINT REFERENCES rdm.reference_value(value_sk),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from      TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to        TIMESTAMPTZ,
    CONSTRAINT ux_reference_value_catalog_code UNIQUE (catalog_sk, value_code),
    -- Regla dura §3.3: solo los miembros técnicos globales (0, -1) carecen de catálogo
    CONSTRAINT ck_reference_value_technical CHECK ((value_sk <= 0) = (catalog_sk IS NULL))
);
CREATE INDEX ix_reference_value_parent ON rdm.reference_value(parent_value_sk);

CREATE TABLE rdm.reference_field_value (
    field_value_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    value_sk       BIGINT NOT NULL REFERENCES rdm.reference_value(value_sk),
    field_code     VARCHAR(60) NOT NULL,
    field_value    TEXT NOT NULL,
    CONSTRAINT ux_reference_field_value UNIQUE (value_sk, field_code)
);

-- =============================================================== Integration
CREATE TABLE rdm.source_system (
    source_system_sk    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system_cd    VARCHAR(40)  NOT NULL UNIQUE,
    name                VARCHAR(160) NOT NULL,
    is_prototype_active BOOLEAN NOT NULL DEFAULT TRUE,
    data_owner          VARCHAR(160),
    data_steward        VARCHAR(120)
);

CREATE TABLE rdm.catalog_source_integration (
    integration_sk   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    catalog_sk       BIGINT NOT NULL REFERENCES rdm.catalog(catalog_sk),
    source_system_sk BIGINT NOT NULL REFERENCES rdm.source_system(source_system_sk),
    source_field     VARCHAR(60) NOT NULL,
    CONSTRAINT ux_catalog_source_integration UNIQUE (catalog_sk, source_system_sk, source_field)
);

CREATE TABLE rdm.source_value_mapping (
    mapping_sk     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    integration_sk BIGINT NOT NULL REFERENCES rdm.catalog_source_integration(integration_sk),
    source_value   VARCHAR(120) NOT NULL,
    value_sk       BIGINT NOT NULL REFERENCES rdm.reference_value(value_sk),
    valid_from     TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to       TIMESTAMPTZ
);
-- Un solo mapeo vigente por (integración, valor fuente)
CREATE UNIQUE INDEX ux_source_value_mapping_current
    ON rdm.source_value_mapping(integration_sk, source_value) WHERE valid_to IS NULL;

-- =============================================================== Audit
CREATE TABLE rdm.rdm_audit_log (
    audit_sk    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity      VARCHAR(60) NOT NULL,
    entity_sk   BIGINT NOT NULL,
    action      VARCHAR(20) NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    actor       VARCHAR(120) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Miembros técnicos globales (regla dura §3.3): una sola vez, con OVERRIDING SYSTEM VALUE
INSERT INTO rdm.reference_value (value_sk, catalog_sk, value_code, value_name, is_active)
OVERRIDING SYSTEM VALUE VALUES
    (0,  NULL, 'UNKNOWN',        'Desconocido / sin homologar', TRUE),
    (-1, NULL, 'NOT_APPLICABLE', 'No aplica',                   TRUE);

-- =============================================================== Triggers
-- Actor de auditoría: la API ejecuta SET LOCAL app.actor = '<usuario>'
CREATE OR REPLACE FUNCTION rdm.fn_actor() RETURNS TEXT LANGUAGE sql STABLE AS $$
    SELECT COALESCE(NULLIF(current_setting('app.actor', true), ''), current_user)
$$;

-- Regla dura §3.7: publicado un canónico activo, value_code/value_name no cambian.
CREATE OR REPLACE FUNCTION rdm.fn_reference_value_immutable() RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.is_active AND (NEW.value_code IS DISTINCT FROM OLD.value_code
                          OR NEW.value_name IS DISTINCT FROM OLD.value_name
                          OR NEW.catalog_sk IS DISTINCT FROM OLD.catalog_sk) THEN
        RAISE EXCEPTION 'RDM: el valor canónico % (%) es inmutable; deprecar y crear uno nuevo (regla dura 3.7)',
            OLD.value_code, OLD.value_sk USING ERRCODE = 'check_violation';
    END IF;
    IF OLD.is_active AND NOT NEW.is_active AND NEW.valid_to IS NULL THEN
        NEW.valid_to := now();
    END IF;
    IF NOT OLD.is_active AND NEW.is_active THEN
        RAISE EXCEPTION 'RDM: un valor deprecado no se reactiva ni se recicla (regla dura 3.7)'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER trg_reference_value_immutable
    BEFORE UPDATE ON rdm.reference_value
    FOR EACH ROW EXECUTE FUNCTION rdm.fn_reference_value_immutable();

-- Auditoría genérica de referencia (Ley 1581/2012 art. 17; DAMA-DMBOK2 Cap. 10)
CREATE OR REPLACE FUNCTION rdm.fn_audit() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE pk BIGINT;
BEGIN
    pk := CASE TG_TABLE_NAME
            WHEN 'reference_value'      THEN (to_jsonb(COALESCE(NEW, OLD))->>'value_sk')::BIGINT
            WHEN 'catalog'              THEN (to_jsonb(COALESCE(NEW, OLD))->>'catalog_sk')::BIGINT
            WHEN 'source_value_mapping' THEN (to_jsonb(COALESCE(NEW, OLD))->>'mapping_sk')::BIGINT
            WHEN 'reference_field_value' THEN (to_jsonb(COALESCE(NEW, OLD))->>'field_value_sk')::BIGINT
          END;
    INSERT INTO rdm.rdm_audit_log(entity, entity_sk, action, old_value, new_value, actor)
    VALUES (upper(TG_TABLE_NAME), pk, TG_OP,
            CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE to_jsonb(OLD)::text END,
            CASE WHEN TG_OP = 'DELETE' THEN NULL ELSE to_jsonb(NEW)::text END,
            rdm.fn_actor());
    RETURN COALESCE(NEW, OLD);
END $$;
CREATE TRIGGER trg_audit_reference_value AFTER INSERT OR UPDATE OR DELETE ON rdm.reference_value
    FOR EACH ROW EXECUTE FUNCTION rdm.fn_audit();
CREATE TRIGGER trg_audit_catalog AFTER INSERT OR UPDATE OR DELETE ON rdm.catalog
    FOR EACH ROW EXECUTE FUNCTION rdm.fn_audit();
CREATE TRIGGER trg_audit_source_value_mapping AFTER INSERT OR UPDATE OR DELETE ON rdm.source_value_mapping
    FOR EACH ROW EXECUTE FUNCTION rdm.fn_audit();
CREATE TRIGGER trg_audit_reference_field_value AFTER INSERT OR UPDATE OR DELETE ON rdm.reference_field_value
    FOR EACH ROW EXECUTE FUNCTION rdm.fn_audit();

-- =============================================================== Vistas (regla dura §3.10)
-- (a) Motor genérico: el dominio viaja como columna, nunca en el nombre.
CREATE VIEW rdm.vw_rdm_lookup AS
SELECT d.domain_code, c.catalog_code, v.value_sk, v.value_code, v.value_name,
       p.value_code AS parent_value_code, v.is_active, v.valid_from, v.valid_to
FROM rdm.reference_value v
JOIN rdm.catalog c ON c.catalog_sk = v.catalog_sk
JOIN rdm.domain  d ON d.domain_sk  = c.domain_sk
LEFT JOIN rdm.reference_value p ON p.value_sk = v.parent_value_sk;

CREATE VIEW rdm.vw_rdm_source_to_canonical AS
SELECT s.source_system_cd, i.source_field, m.source_value,
       d.domain_code, c.catalog_code, v.value_sk, v.value_code, v.value_name,
       m.mapping_sk, m.valid_from, m.valid_to
FROM rdm.source_value_mapping m
JOIN rdm.catalog_source_integration i ON i.integration_sk = m.integration_sk
JOIN rdm.source_system s ON s.source_system_sk = i.source_system_sk
JOIN rdm.catalog c ON c.catalog_sk = i.catalog_sk
JOIN rdm.domain  d ON d.domain_sk  = c.domain_sk
JOIN rdm.reference_value v ON v.value_sk = m.value_sk
WHERE m.valid_to IS NULL;

-- Fuente A → fuente B: auto-join de la vista fuente→canónico por VALUE_SK (no sobre tablas base)
CREATE VIEW rdm.vw_rdm_crosswalk AS
SELECT a.domain_code, a.catalog_code, a.value_sk, a.value_code,
       a.source_system_cd AS from_system_cd, a.source_field AS from_field, a.source_value AS from_value,
       b.source_system_cd AS to_system_cd,   b.source_field AS to_field,   b.source_value AS to_value
FROM rdm.vw_rdm_source_to_canonical a
JOIN rdm.vw_rdm_source_to_canonical b ON b.value_sk = a.value_sk
WHERE (a.source_system_cd, a.source_field) <> (b.source_system_cd, b.source_field);

-- (b) Vistas tipadas: solo donde hay que pivotar EAV.
CREATE VIEW rdm.vw_rdm_cat_geo_divipola AS
SELECT v.value_sk, v.value_code, v.value_name,
       CASE WHEN v.parent_value_sk IS NULL THEN 'DEPARTAMENTO' ELSE 'MUNICIPIO' END AS level_code,
       COALESCE(p.value_code, v.value_code) AS department_code,
       COALESCE(p.value_name, v.value_name) AS department_name,
       lt.field_value AS locality_type,
       v.is_active
FROM rdm.reference_value v
JOIN rdm.catalog c ON c.catalog_sk = v.catalog_sk AND c.catalog_code = 'CAT_GEO_DIVIPOLA'
LEFT JOIN rdm.reference_value p ON p.value_sk = v.parent_value_sk
LEFT JOIN rdm.reference_field_value lt ON lt.value_sk = v.value_sk AND lt.field_code = 'locality_type';

CREATE VIEW rdm.vw_rdm_cat_id_type AS
SELECT v.value_sk, v.value_code, v.value_name,
       rx.field_value AS validation_regex,
       ap.field_value AS applies_to,
       COALESCE(cd.field_value, 'false')::BOOLEAN AS has_check_digit,
       v.is_active
FROM rdm.reference_value v
JOIN rdm.catalog c ON c.catalog_sk = v.catalog_sk AND c.catalog_code = 'CAT_ID_TYPE'
LEFT JOIN rdm.reference_field_value rx ON rx.value_sk = v.value_sk AND rx.field_code = 'validation_regex'
LEFT JOIN rdm.reference_field_value ap ON ap.value_sk = v.value_sk AND ap.field_code = 'applies_to'
LEFT JOIN rdm.reference_field_value cd ON cd.value_sk = v.value_sk AND cd.field_code = 'has_check_digit';

CREATE VIEW rdm.vw_rdm_cat_relationship_type AS
SELECT v.value_sk, v.value_code, v.value_name,
       f.field_value AS from_party_type,
       t.field_value AS to_party_type,
       i.field_value AS inverse_code,
       v.is_active
FROM rdm.reference_value v
JOIN rdm.catalog c ON c.catalog_sk = v.catalog_sk AND c.catalog_code = 'CAT_RELATIONSHIP_TYPE'
LEFT JOIN rdm.reference_field_value f ON f.value_sk = v.value_sk AND f.field_code = 'from_party_type'
LEFT JOIN rdm.reference_field_value t ON t.value_sk = v.value_sk AND t.field_code = 'to_party_type'
LEFT JOIN rdm.reference_field_value i ON i.value_sk = v.value_sk AND i.field_code = 'inverse_code';
"""

DROP = """
DROP VIEW IF EXISTS rdm.vw_rdm_cat_relationship_type, rdm.vw_rdm_cat_id_type,
    rdm.vw_rdm_cat_geo_divipola, rdm.vw_rdm_crosswalk, rdm.vw_rdm_source_to_canonical, rdm.vw_rdm_lookup;
DROP TABLE IF EXISTS rdm.rdm_audit_log, rdm.source_value_mapping, rdm.catalog_source_integration,
    rdm.source_system, rdm.reference_field_value, rdm.reference_value, rdm.catalog, rdm.domain CASCADE;
DROP FUNCTION IF EXISTS rdm.fn_audit(), rdm.fn_reference_value_immutable(), rdm.fn_actor();
"""


def upgrade() -> None:
    op.execute(DDL)


def downgrade() -> None:
    op.execute(DROP)
