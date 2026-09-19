"""F2 · esquema staging (5 RAW + LOAD_BATCH) y esquema mdm (29 tablas, 8 capas)

Revision ID: f2_0002
Revises: f1_0001
Create Date: 2026-09-13

Patrones (SPEC §5.4): SK IDENTITY; todo *_cd BIGINT NOT NULL DEFAULT 0 FK rdm.reference_value
(excepción §3.5(a): source_system_cd / winning_source_cd → rdm.source_system); linaje por fila
(§3.14); unicidad de documento entre goldens (§3.16) con columna is_golden mantenida por trigger;
FKs cruzadas entre capas al final vía ALTER TABLE; auditoría genérica en PARTY_AUDIT_LOG por
trigger (Ley 1581/2012 art. 17; ISO/IEC 27001:2022 A.8.15).
"""
from alembic import op

revision = "f2_0002"
down_revision = "f1_0001"
branch_labels = None
depends_on = None

CD = "BIGINT NOT NULL DEFAULT 0 REFERENCES rdm.reference_value(value_sk)"
CD_NULL = "BIGINT REFERENCES rdm.reference_value(value_sk)"
SRC = "BIGINT NOT NULL REFERENCES rdm.source_system(source_system_sk)"
SRC_NULL = "BIGINT REFERENCES rdm.source_system(source_system_sk)"
LINEAGE = f"source_system_cd {SRC}, captured_at TIMESTAMPTZ NOT NULL DEFAULT now()"

RAW_SOURCES = ["sf_ec", "ecc_sd", "ecc_mm", "crm_bp", "web_portal"]


def raw_table(name: str) -> str:
    return f"""
CREATE TABLE staging.stg_{name}_raw (
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
CREATE INDEX ix_stg_{name}_ext ON staging.stg_{name}_raw(external_id, source_hash);
CREATE INDEX ix_stg_{name}_batch ON staging.stg_{name}_raw(batch_id, raw_status);
"""


DDL_STAGING = """
CREATE TABLE staging.load_batch (
    batch_id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system_cd BIGINT NOT NULL REFERENCES rdm.source_system(source_system_sk),
    mode             VARCHAR(16) NOT NULL CHECK (mode IN ('FULL','DELTA','RNE_SYNC','REHOMOLOGATE','MATCH')),
    status           VARCHAR(10) NOT NULL DEFAULT 'RUNNING' CHECK (status IN ('RUNNING','OK','FAILED')),
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at      TIMESTAMPTZ,
    extracted        INT NOT NULL DEFAULT 0,
    unchanged_hash   INT NOT NULL DEFAULT 0,
    standardized     INT NOT NULL DEFAULT 0,
    homologated      INT NOT NULL DEFAULT 0,
    unknown_codes    INT NOT NULL DEFAULT 0,
    dq_passed        INT NOT NULL DEFAULT 0,
    dq_quarantined   INT NOT NULL DEFAULT 0,
    xref_hits        INT NOT NULL DEFAULT 0,
    matched          INT NOT NULL DEFAULT 0,
    auto_merged      INT NOT NULL DEFAULT 0,
    probable         INT NOT NULL DEFAULT 0,
    loaded           INT NOT NULL DEFAULT 0,
    actor            VARCHAR(120) NOT NULL DEFAULT current_user,
    detail           JSONB
);
""" + "".join(raw_table(s) for s in RAW_SOURCES)


DDL_MDM = f"""
-- ===================================================================== Capa 2 · Core
CREATE TABLE mdm.party (
    party_sk           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_type_cd      {CD},
    golden_status_cd   {CD},
    party_status_cd    {CD},
    golden_version     INT NOT NULL DEFAULT 1,
    completeness_score NUMERIC(5,2) NOT NULL DEFAULT 0,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE mdm.party_person (
    party_sk             BIGINT PRIMARY KEY REFERENCES mdm.party(party_sk),
    first_name           VARCHAR(80),
    middle_name          VARCHAR(80),
    first_surname        VARCHAR(80),
    second_surname       VARCHAR(80),
    birth_date           DATE,
    death_date           DATE,
    gender_cd            {CD},
    full_name_normalized VARCHAR(320)
);
CREATE TABLE mdm.party_org (
    party_sk              BIGINT PRIMARY KEY REFERENCES mdm.party(party_sk),
    legal_name            VARCHAR(200),
    trade_name            VARCHAR(200),
    legal_name_normalized VARCHAR(200),
    ciiu_cd               {CD},
    org_type_cd           {CD}
);
CREATE TABLE mdm.party_role (
    party_role_sk    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk         BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    role_cd          {CD},
    sub_role_cd      {CD},
    business_unit_cd {CD},
    valid_from       DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to         DATE,
    {LINEAGE},
    CONSTRAINT ux_party_role UNIQUE (party_sk, role_cd, business_unit_cd, source_system_cd, valid_from)
);
CREATE TABLE mdm.party_segment (
    party_segment_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk         BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    segment_type_cd  {CD},
    segment_cd       {CD},
    valid_from       DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to         DATE,
    {LINEAGE}
);
-- un segmento vigente por tipo (regla §5.2): índice único parcial sobre los vigentes
CREATE UNIQUE INDEX ux_party_segment_current ON mdm.party_segment(party_sk, segment_type_cd) WHERE valid_to IS NULL;
CREATE TABLE mdm.xref_party_source (
    xref_sk          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk         BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    source_system_cd {SRC},
    external_id      VARCHAR(80) NOT NULL,
    source_hash      CHAR(64),
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_xref UNIQUE (source_system_cd, external_id)
);
CREATE INDEX ix_xref_party ON mdm.xref_party_source(party_sk);

-- ===================================================================== Capa 3 · Identity
CREATE TABLE mdm.party_identifier (
    identifier_sk          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk               BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    id_type_cd             {CD},
    id_number              VARCHAR(40) NOT NULL,
    verification_source_cd {CD},
    is_verified            BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at            TIMESTAMPTZ,
    is_golden              BOOLEAN NOT NULL DEFAULT FALSE,   -- mantenida por trigger (regla §3.16)
    {LINEAGE},
    CONSTRAINT ux_party_identifier UNIQUE (party_sk, id_type_cd, id_number)
);
CREATE INDEX ix_party_identifier_number ON mdm.party_identifier(id_type_cd, id_number);
CREATE UNIQUE INDEX ux_identifier_golden ON mdm.party_identifier(id_type_cd, id_number) WHERE is_golden;
CREATE TABLE mdm.party_name (
    party_name_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk      BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    name_type_cd  {CD},
    name_value    VARCHAR(320) NOT NULL,
    valid_from    DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to      DATE,
    {LINEAGE}
);
CREATE INDEX ix_party_name_party ON mdm.party_name(party_sk);

-- ===================================================================== Capa 4 · Roles & Relationships
CREATE TABLE mdm.party_relationship (
    relationship_sk      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_party_sk        BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    to_party_sk          BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    relationship_type_cd {CD},
    valid_from           DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to             DATE,
    {LINEAGE},
    CONSTRAINT ux_party_relationship UNIQUE (from_party_sk, to_party_sk, relationship_type_cd, valid_from),
    CONSTRAINT ck_relationship_not_self CHECK (from_party_sk <> to_party_sk)
);
CREATE INDEX ix_relationship_to ON mdm.party_relationship(to_party_sk);
CREATE TABLE mdm.party_group (
    group_sk        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_type_cd   {CD},
    group_name      VARCHAR(160),
    anchor_party_sk BIGINT REFERENCES mdm.party(party_sk),
    source_system_cd {SRC_NULL},
    source_reference VARCHAR(80),
    CONSTRAINT ux_party_group_source UNIQUE (source_system_cd, source_reference)
);
CREATE TABLE mdm.party_group_member (
    group_member_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_sk        BIGINT NOT NULL REFERENCES mdm.party_group(group_sk),
    party_sk        BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    member_role_cd  {CD},
    valid_from      DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to        DATE,
    CONSTRAINT ux_group_member UNIQUE (group_sk, party_sk, valid_from)
);
CREATE TABLE mdm.party_service_enrollment (
    enrollment_sk        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk             BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    party_role_sk        BIGINT,              -- FK al final (capa 2)
    business_unit_cd     {CD},
    service_cd           {CD},
    enrollment_status_cd {CD},
    enrolled_at          DATE,
    closed_at            DATE,
    source_reference     VARCHAR(80) NOT NULL,
    valid_from           DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to             DATE,
    {LINEAGE},
    CONSTRAINT ux_enrollment UNIQUE (party_sk, service_cd, source_reference)
);

-- ===================================================================== Capa 5 · Contactability
CREATE TABLE mdm.contact_point (
    contact_point_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel_cd       {CD},
    contact_value    VARCHAR(320) NOT NULL,
    address_sk       BIGINT,                  -- FK al final (PARTY_ADDRESS, solo PHYSICAL_MAIL)
    contact_hash     CHAR(64) NOT NULL,
    rne_excluded     BOOLEAN NOT NULL DEFAULT FALSE,
    rne_synced_at    TIMESTAMPTZ,
    is_verified      BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_contact_point UNIQUE (channel_cd, contact_hash)
);
CREATE TABLE mdm.party_contact_point (
    party_contact_sk       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk               BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    contact_point_sk       BIGINT NOT NULL REFERENCES mdm.contact_point(contact_point_sk),
    usage_role_cd          {CD},
    confirmation_status_cd {CD},
    origin_cd              {CD},
    is_primary             BOOLEAN NOT NULL DEFAULT FALSE,
    valid_from             DATE NOT NULL DEFAULT CURRENT_DATE,
    valid_to               DATE,
    {LINEAGE},
    CONSTRAINT ux_party_contact UNIQUE (party_sk, contact_point_sk, valid_from)
);
CREATE INDEX ix_party_contact_cp ON mdm.party_contact_point(contact_point_sk);
CREATE TABLE mdm.party_address (
    address_sk          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk            BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    address_line        VARCHAR(240),
    country_cd          {CD},
    divipola_cd         {CD},
    geocoding_status_cd {CD},
    is_primary          BOOLEAN NOT NULL DEFAULT FALSE,
    {LINEAGE}
);
CREATE INDEX ix_party_address_party ON mdm.party_address(party_sk);
CREATE TABLE mdm.party_contact_pref (
    pref_sk          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk         BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    channel_cd       {CD},
    party_contact_sk BIGINT REFERENCES mdm.party_contact_point(party_contact_sk),
    purpose_cd       {CD},
    allowed          BOOLEAN NOT NULL,
    frequency_cd     {CD},
    origin_cd        {CD},
    declared_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_from       TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to         TIMESTAMPTZ
);
-- una preferencia vigente por (party, canal, contacto|NULL, finalidad); NULLS NOT DISTINCT para el nivel de canal
CREATE UNIQUE INDEX ux_contact_pref_current ON mdm.party_contact_pref(party_sk, channel_cd, party_contact_sk, purpose_cd)
    NULLS NOT DISTINCT WHERE valid_to IS NULL;
CREATE TABLE mdm.party_contact_eligibility_cache (
    party_contact_sk BIGINT NOT NULL REFERENCES mdm.party_contact_point(party_contact_sk),
    purpose_cd       {CD},
    party_sk         BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    is_eligible      BOOLEAN NOT NULL,
    reason_cd        {CD},
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (party_contact_sk, purpose_cd)
);
CREATE INDEX ix_eligibility_audience ON mdm.party_contact_eligibility_cache(purpose_cd, is_eligible, party_sk);

-- ===================================================================== Capa 6 · Governance
CREATE TABLE mdm.match_rule (
    rule_sk        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_type_cd {CD},
    attribute      VARCHAR(60) NOT NULL,
    weight         NUMERIC(5,2) NOT NULL,
    algorithm      VARCHAR(40) NOT NULL,
    params         JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    version        INT NOT NULL DEFAULT 1,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT ux_match_rule UNIQUE (entity_type_cd, attribute, version)
);
CREATE TABLE mdm.party_dq_issue (
    dq_issue_sk    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staging_ref    VARCHAR(120),
    party_sk       BIGINT REFERENCES mdm.party(party_sk),
    dq_category_cd {CD},
    field          VARCHAR(80) NOT NULL,
    detail         JSONB,
    severity_cd    {CD},
    source_system_cd {SRC_NULL},
    batch_id       BIGINT,
    detected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at    TIMESTAMPTZ
);
CREATE INDEX ix_dq_issue_open ON mdm.party_dq_issue(dq_category_cd, field) WHERE resolved_at IS NULL;
CREATE TABLE mdm.party_audit_log (
    audit_sk         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk         BIGINT,
    entity           VARCHAR(60) NOT NULL,
    entity_sk        BIGINT,
    action_cd        {CD},
    old_value        JSONB,
    new_value        JSONB,
    actor            VARCHAR(120) NOT NULL,
    source_system_cd {SRC_NULL},
    batch_id         BIGINT,
    arco_request_id  BIGINT,                 -- FK al final (capa 8)
    merge_sk         BIGINT,                 -- FK al final (capa 7)
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_party_audit_party ON mdm.party_audit_log(party_sk, occurred_at);
CREATE INDEX ix_party_audit_time ON mdm.party_audit_log(occurred_at);
CREATE TABLE mdm.party_data_retention (
    retention_sk      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk          BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    entity            VARCHAR(60) NOT NULL,
    entity_sk         BIGINT,
    retention_rule_cd {CD},
    purge_after       DATE,
    legal_basis       VARCHAR(200),
    purge_status      VARCHAR(10) NOT NULL DEFAULT 'SCHEDULED' CHECK (purge_status IN ('SCHEDULED','HOLD','PURGED')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ===================================================================== Capa 7 · Golden Record
CREATE TABLE mdm.party_bucket (
    bucket_sk            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    blocking_key         VARCHAR(160) NOT NULL,
    blocking_strategy_cd {CD},
    party_type_cd        {CD},
    batch_id             BIGINT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_party_bucket_key ON mdm.party_bucket(blocking_strategy_cd, blocking_key);
CREATE TABLE mdm.bucket_candidate (
    candidate_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    bucket_sk    BIGINT NOT NULL REFERENCES mdm.party_bucket(bucket_sk),
    staging_ref  VARCHAR(120),
    party_sk     BIGINT REFERENCES mdm.party(party_sk)
);
CREATE TABLE mdm.party_match (
    match_sk     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_a_sk   BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    party_b_sk   BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    total_score  NUMERIC(6,2) NOT NULL,
    score_detail JSONB NOT NULL,
    decision_cd  {CD},
    match_status VARCHAR(12) NOT NULL DEFAULT 'PENDING' CHECK (match_status IN ('PENDING','IN_REVIEW','RESOLVED')),
    rule_version INT NOT NULL DEFAULT 1,
    batch_id     BIGINT,
    matched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_match_pair CHECK (party_a_sk < party_b_sk)
);
CREATE UNIQUE INDEX ux_party_match_pair_open ON mdm.party_match(party_a_sk, party_b_sk) WHERE match_status <> 'RESOLVED';
CREATE TABLE mdm.match_review_task (
    task_sk          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    match_sk         BIGINT NOT NULL REFERENCES mdm.party_match(match_sk),
    source_system_cd {SRC},
    assignee         VARCHAR(120),
    task_status_cd   {CD},
    decision_cd      {CD_NULL},
    justification    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    due_at           TIMESTAMPTZ,
    decided_at       TIMESTAMPTZ,
    decided_by       VARCHAR(120)
);
CREATE TABLE mdm.party_merge_history (
    merge_sk           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    surviving_party_sk BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    merged_party_sk    BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    merge_type_cd      {CD},
    match_sk           BIGINT,               -- FK al final
    justification      TEXT,
    decided_by         VARCHAR(120) NOT NULL,
    merged_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    pre_merge_snapshot JSONB NOT NULL,
    unmerged           BOOLEAN NOT NULL DEFAULT FALSE,
    unmerged_by        VARCHAR(120),
    unmerged_at        TIMESTAMPTZ,
    unmerge_reason     TEXT
);
CREATE TABLE mdm.party_survivorship (
    survivorship_sk   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk          BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    field_name        VARCHAR(60) NOT NULL,
    strategy_cd       {CD},
    winning_source_cd {SRC_NULL},
    winning_value     TEXT,
    decided_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_survivorship UNIQUE (party_sk, field_name)
);

-- ===================================================================== Capa 8 · Consents
CREATE TABLE mdm.party_consent (
    consent_sk           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk             BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    consent_type_cd      {CD},
    consent_status_cd    {CD},
    granted_at           TIMESTAMPTZ,
    revoked_at           TIMESTAMPTZ,
    expires_at           TIMESTAMPTZ,
    evidence_ref         VARCHAR(200),
    granted_by_party_sk  BIGINT REFERENCES mdm.party(party_sk),
    valid_from           TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to             TIMESTAMPTZ,
    {LINEAGE}
);
CREATE UNIQUE INDEX ux_consent_current ON mdm.party_consent(party_sk, consent_type_cd) WHERE valid_to IS NULL;
CREATE TABLE mdm.data_subject_request (
    request_sk        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    party_sk          BIGINT NOT NULL REFERENCES mdm.party(party_sk),
    arco_type_cd      {CD},
    request_status_cd {CD},
    requested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    due_at            TIMESTAMPTZ,
    resolved_at       TIMESTAMPTZ,
    resolution_note   TEXT,
    channel_received  VARCHAR(40)
);

-- ===================================================================== FKs cruzadas entre capas (al final)
ALTER TABLE mdm.party_service_enrollment ADD CONSTRAINT fk_enrollment_role FOREIGN KEY (party_role_sk) REFERENCES mdm.party_role(party_role_sk);
ALTER TABLE mdm.contact_point ADD CONSTRAINT fk_contact_point_address FOREIGN KEY (address_sk) REFERENCES mdm.party_address(address_sk);
ALTER TABLE mdm.party_audit_log ADD CONSTRAINT fk_audit_arco FOREIGN KEY (arco_request_id) REFERENCES mdm.data_subject_request(request_sk);
ALTER TABLE mdm.party_audit_log ADD CONSTRAINT fk_audit_merge FOREIGN KEY (merge_sk) REFERENCES mdm.party_merge_history(merge_sk);
ALTER TABLE mdm.party_merge_history ADD CONSTRAINT fk_merge_match FOREIGN KEY (match_sk) REFERENCES mdm.party_match(match_sk);

-- ===================================================================== Índices de rendimiento (§5.4)
CREATE INDEX ix_party_person_name_trgm ON mdm.party_person USING gin (full_name_normalized gin_trgm_ops);
CREATE INDEX ix_party_org_name_trgm ON mdm.party_org USING gin (legal_name_normalized gin_trgm_ops);
CREATE INDEX ix_party_status ON mdm.party(golden_status_cd, party_type_cd);

-- ===================================================================== Triggers
-- is_golden en PARTY_IDENTIFIER sigue al estado del party (regla §3.16)
CREATE OR REPLACE FUNCTION mdm.fn_identifier_is_golden() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE golden_sk BIGINT;
BEGIN
    SELECT value_sk INTO golden_sk FROM rdm.reference_value v JOIN rdm.catalog c ON c.catalog_sk=v.catalog_sk
     WHERE c.catalog_code='CAT_GOLDEN_STATUS' AND v.value_code='GOLDEN';
    IF TG_TABLE_NAME = 'party' THEN
        UPDATE mdm.party_identifier SET is_golden = (NEW.golden_status_cd = golden_sk) WHERE party_sk = NEW.party_sk;
        RETURN NEW;
    ELSE
        SELECT (p.golden_status_cd = golden_sk) INTO NEW.is_golden FROM mdm.party p WHERE p.party_sk = NEW.party_sk;
        RETURN NEW;
    END IF;
END $$;
CREATE TRIGGER trg_party_golden_flag AFTER UPDATE OF golden_status_cd ON mdm.party
    FOR EACH ROW EXECUTE FUNCTION mdm.fn_identifier_is_golden();
CREATE TRIGGER trg_identifier_golden_flag BEFORE INSERT OR UPDATE OF party_sk ON mdm.party_identifier
    FOR EACH ROW EXECUTE FUNCTION mdm.fn_identifier_is_golden();

-- Auditoría genérica (Ley 1581/2012 art. 17). Contexto de sesión: app.actor, app.batch_id,
-- app.source_system_sk, app.arco_request_id, app.merge_sk, app.audit_action (override: MERGE, UNMERGE, ...)
CREATE OR REPLACE FUNCTION mdm.fn_setting_bigint(name TEXT) RETURNS BIGINT LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting(name, true), '')::BIGINT
$$;
CREATE OR REPLACE FUNCTION mdm.fn_audit() RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    rec JSONB := to_jsonb(COALESCE(NEW, OLD));
    pk_col TEXT;
    action_code TEXT;
    action_sk BIGINT;
BEGIN
    pk_col := TG_ARGV[0];
    action_code := COALESCE(NULLIF(current_setting('app.audit_action', true), ''), TG_OP);
    SELECT v.value_sk INTO action_sk FROM rdm.reference_value v JOIN rdm.catalog c ON c.catalog_sk=v.catalog_sk
     WHERE c.catalog_code='CAT_AUDIT_ACTION' AND v.value_code=action_code;
    INSERT INTO mdm.party_audit_log(party_sk, entity, entity_sk, action_cd, old_value, new_value, actor,
                                    source_system_cd, batch_id, arco_request_id, merge_sk)
    VALUES (COALESCE((rec->>'party_sk')::BIGINT, (rec->>'from_party_sk')::BIGINT, (rec->>'surviving_party_sk')::BIGINT),
            upper(TG_TABLE_NAME), (rec->>pk_col)::BIGINT, COALESCE(action_sk, 0),
            CASE WHEN TG_OP='INSERT' THEN NULL ELSE to_jsonb(OLD) END,
            CASE WHEN TG_OP='DELETE' THEN NULL ELSE to_jsonb(NEW) END,
            rdm.fn_actor(),
            COALESCE((rec->>'source_system_cd')::BIGINT, mdm.fn_setting_bigint('app.source_system_sk')),
            mdm.fn_setting_bigint('app.batch_id'),
            mdm.fn_setting_bigint('app.arco_request_id'),
            mdm.fn_setting_bigint('app.merge_sk'));
    RETURN COALESCE(NEW, OLD);
END $$;
"""

AUDITED = {
    "party": "party_sk", "party_person": "party_sk", "party_org": "party_sk", "party_role": "party_role_sk",
    "party_segment": "party_segment_sk", "xref_party_source": "xref_sk", "party_identifier": "identifier_sk",
    "party_name": "party_name_sk", "party_relationship": "relationship_sk", "party_group": "group_sk",
    "party_group_member": "group_member_sk", "party_service_enrollment": "enrollment_sk",
    "contact_point": "contact_point_sk", "party_contact_point": "party_contact_sk", "party_address": "address_sk",
    "party_contact_pref": "pref_sk", "party_data_retention": "retention_sk", "party_merge_history": "merge_sk",
    "party_survivorship": "survivorship_sk", "party_consent": "consent_sk", "data_subject_request": "request_sk",
    "match_review_task": "task_sk",
}

DDL_TRIGGERS = "".join(
    f"CREATE TRIGGER trg_audit_{t} AFTER INSERT OR UPDATE OR DELETE ON mdm.{t} "
    f"FOR EACH ROW EXECUTE FUNCTION mdm.fn_audit('{pk}');\n" for t, pk in AUDITED.items()
)


def upgrade() -> None:
    op.execute(DDL_STAGING)
    op.execute(DDL_MDM)
    op.execute(DDL_TRIGGERS)


def downgrade() -> None:
    op.execute("DROP SCHEMA mdm CASCADE; CREATE SCHEMA mdm; DROP SCHEMA staging CASCADE; CREATE SCHEMA staging;")
