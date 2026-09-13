"""F2 · criterios de aceptación (SPEC §14): ingesta de las 5 fuentes con DQ_PASSED/DQ_QUARANTINE
correctos, homologación aplicada, hallazgos en PARTY_DQ_ISSUE, sin campos multivaluados, linaje en
toda fila de hechos, contactos sin duplicar, casos I, O, P y R, y bitácora LOAD_BATCH."""
import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.db import engine

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "data" / "synth" / "manifest.json").read_text(encoding="utf-8"))
CASES = MANIFEST["cases"]


def q(sql, **p):
    with engine.connect() as conn:
        return conn.execute(text(sql), p)


def party_of(system: str, external_id: str) -> int:
    return q("SELECT x.party_sk FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd "
             "WHERE s.source_system_cd=:s AND x.external_id=:e", s=system, e=external_id).scalar_one()


# ------------------------------------------------------------------ bitácora y estados
def test_load_batches_ok_and_counts_match_manifest():
    rows = q("""SELECT s.source_system_cd, b.status, b.extracted, b.dq_passed, b.dq_quarantined, b.loaded, b.unknown_codes
                FROM staging.load_batch b JOIN rdm.source_system s ON s.source_system_sk=b.source_system_cd
                WHERE b.mode='FULL' ORDER BY b.batch_id""").all()
    by = {r[0]: r for r in rows}
    assert all(r[1] == "OK" for r in rows) and len(rows) == 5
    counts = {"SF_EC": "sf_ec", "SAP_ECC_SD": "ecc_sd", "SAP_ECC_MM": "ecc_mm", "SAP_CRM": "crm_bp", "WEB_PORTAL": "web_portal"}
    for sys_, key in counts.items():
        assert by[sys_][2] == MANIFEST["counts"][key]
        assert by[sys_][3] + by[sys_][4] == by[sys_][2] and by[sys_][5] == by[sys_][3]
    assert sum(r[4] for r in rows) == 1                     # solo el registro SD sin documento
    assert by["SAP_CRM"][6] == 2                             # ZPRV (caso P) y DIVIPOLA 99999; nada más


def test_quarantine_is_the_planted_missing_document():
    ref = q("SELECT staging_ref FROM mdm.party_dq_issue i JOIN rdm.reference_value s ON s.value_sk=i.severity_cd WHERE s.value_code='BLOCKING'").scalars().all()
    assert len(ref) == 1
    raw_sk = int(ref[0].split(":")[1])
    row = q("SELECT external_id, raw_status FROM staging.stg_ecc_sd_raw WHERE raw_sk=:k", k=raw_sk).one()
    assert row[0] == CASES["DQ"]["missing_doc"] and row[1] == "DQ_QUARANTINE"
    assert q("SELECT count(*) FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd "
             "WHERE s.source_system_cd='SAP_ECC_SD' AND x.external_id=:e", e=CASES["DQ"]["missing_doc"]).scalar_one() == 0


def test_raw_status_lifecycle():
    statuses = q("SELECT raw_status, count(*) FROM staging.stg_crm_bp_raw GROUP BY 1").all()
    assert dict(statuses) == {"LOADED": MANIFEST["counts"]["crm_bp"]}
    std = q("SELECT standardized FROM staging.stg_crm_bp_raw WHERE external_id=:e", e=CASES["A"]["crm_bp"]).scalar_one()
    assert std["person"]["gender"]["code"] == "M" or std["person"]["gender"]["code"] == "F"   # homologado y persistido


# ------------------------------------------------------------------ homologación y hallazgos
def test_homologation_applied_geschl_to_gender():
    p = party_of("SAP_CRM", CASES["A"]["crm_bp"])
    raw = q("SELECT payload->>'GESCHL' FROM staging.stg_crm_bp_raw WHERE external_id=:e", e=CASES["A"]["crm_bp"]).scalar_one()
    g = q("SELECT v.value_code FROM mdm.party_person pp JOIN rdm.reference_value v ON v.value_sk=pp.gender_cd WHERE pp.party_sk=:p", p=p).scalar_one()
    assert g == {"1": "M", "2": "F"}[raw]


def test_planted_dq_findings():
    fields = dict(q("""SELECT i.field, count(*) FROM mdm.party_dq_issue i WHERE i.field IN ('phone','nit_check_digit','identifier') GROUP BY 1""").all())
    assert fields["phone"] >= 1 and fields["nit_check_digit"] == 1 and fields["identifier"] >= 1
    p = party_of("SAP_CRM", CASES["DQ"]["bad_divipola"])
    div = q("SELECT divipola_cd FROM mdm.party_address WHERE party_sk=:p", p=p).scalar_one()
    assert div == 0    # 99999 no existe en DIVIPOLA → 0 = UNKNOWN + hallazgo VALIDITY
    assert q("SELECT count(*) FROM mdm.party_dq_issue WHERE party_sk=:p AND detail->>'source_value'='99999'", p=p).scalar_one() == 1


def test_no_multivalued_fields_in_facts():
    for table, col in [("party_role", "role_cd::text"), ("party_service_enrollment", "source_reference"),
                       ("contact_point", "contact_value"), ("party_segment", "segment_cd::text")]:
        assert q(f"SELECT count(*) FROM mdm.{table} WHERE {col} LIKE '%;%'").scalar_one() == 0
    # RLTYP 'ZAFI;ZSUB' del caso R → 1 rol AFFILIATE + 1 vínculo CUOTA_MONETARIA (filas con linaje SAP_CRM)
    p = party_of("SAP_CRM", CASES["R"]["crm_bp"])
    crm = "(SELECT source_system_sk FROM rdm.source_system WHERE source_system_cd='SAP_CRM')"
    assert q(f"SELECT count(*) FROM mdm.party_role WHERE party_sk=:p AND source_system_cd={crm}", p=p).scalar_one() == 1
    assert q(f"SELECT v.value_code FROM mdm.party_service_enrollment e JOIN rdm.reference_value v ON v.value_sk=e.service_cd WHERE e.party_sk=:p AND e.source_system_cd={crm}", p=p).scalar_one() == "CUOTA_MONETARIA"


def test_lineage_on_every_fact_row():
    for t in ["party_role", "party_segment", "party_identifier", "party_name", "party_relationship", "party_service_enrollment",
              "party_contact_point", "party_address", "party_consent"]:
        n = q(f"SELECT count(*) FROM mdm.{t}").scalar_one()
        assert n > 0, t
        assert q(f"SELECT count(*) FROM mdm.{t} WHERE source_system_cd IS NULL OR captured_at IS NULL").scalar_one() == 0, t
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO mdm.party_name (party_sk, name_type_cd, name_value) VALUES (1, 0, 'x')"))


# ------------------------------------------------------------------ contactos (caso J) y auditoría
def test_shared_contact_point_not_duplicated_case_J():
    phone = "+57" + CASES["J"]["shared_phone"]
    cps = q("SELECT contact_point_sk FROM mdm.contact_point WHERE contact_value=:v", v=phone).scalars().all()
    assert len(cps) == 1
    links = {r[0]: r[1] for r in q("""SELECT l.party_sk, ur.value_code FROM mdm.party_contact_point l
                                      JOIN rdm.reference_value ur ON ur.value_sk=l.usage_role_cd WHERE l.contact_point_sk=:c""", c=cps[0]).all()}
    mother, child = party_of("SAP_CRM", CASES["J"]["mother"]), party_of("SAP_CRM", CASES["J"]["child"])
    assert links == {mother: "GUARDIAN", child: "OWNER"}
    grp = q("SELECT g.anchor_party_sk, count(m.party_sk) FROM mdm.party_group g JOIN mdm.party_group_member m ON m.group_sk=g.group_sk "
            "WHERE g.source_reference='FAM-0007' GROUP BY 1").one()
    assert grp[0] == mother and grp[1] == 2


def test_audit_rows_carry_batch_and_source():
    p = party_of("SAP_CRM", CASES["A"]["crm_bp"])
    rows = q("""SELECT a.entity, ac.value_code, a.batch_id, s.source_system_cd, a.actor FROM mdm.party_audit_log a
                JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd LEFT JOIN rdm.source_system s ON s.source_system_sk=a.source_system_cd
                WHERE a.party_sk=:p""", p=p).all()
    # MERGE_HISTORY y SURVIVORSHIP son escrituras entre fuentes (F3): sin sistema fuente, con merge_sk
    inserts = [r for r in rows if r[1] == "INSERT" and r[0] not in ("PARTY_MERGE_HISTORY", "PARTY_SURVIVORSHIP")]
    entities = {r[0] for r in inserts}
    assert {"PARTY", "PARTY_PERSON", "XREF_PARTY_SOURCE", "PARTY_IDENTIFIER", "PARTY_CONTACT_POINT"} <= entities
    assert all(r[2] is not None and r[3] in ("SAP_CRM", "SAP_ECC_SD") and r[4] == "pytest" for r in inserts)


# ------------------------------------------------------------------ casos I, O, P, R
def test_case_I_segments_multi_type():
    def segs(sys_, ext):
        p = party_of(sys_, ext)
        return {r[0]: (r[1], r[2]) for r in q("""SELECT st.value_code, sg.value_code, s.source_system_cd FROM mdm.party_segment g
            JOIN rdm.reference_value st ON st.value_sk=g.segment_type_cd JOIN rdm.reference_value sg ON sg.value_sk=g.segment_cd
            JOIN rdm.source_system s ON s.source_system_sk=g.source_system_cd WHERE g.party_sk=:p AND g.valid_to IS NULL""", p=p).all()}
    # tras el matching (F3) las tres fuentes apuntan al mismo golden con un segmento vigente por tipo y su fuente
    golden = {party_of(s, CASES["I"][k]) for s, k in (("SAP_CRM", "crm_bp"), ("SAP_ECC_SD", "ecc_sd"), ("WEB_PORTAL", "web_portal"))}
    assert len(golden) == 1
    got = segs("SAP_CRM", CASES["I"]["crm_bp"])
    assert got["AFFILIATION"][0] == "A" and got["FINANCIAL_RISK"] == ("HIGH", "SAP_ECC_SD") and got["COMMERCIAL"] == ("PREMIUM", "WEB_PORTAL")
    # un solo segmento vigente por tipo: un segundo AFFILIATION vigente viola el índice único parcial
    p = party_of("SAP_CRM", CASES["I"]["crm_bp"])
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("""INSERT INTO mdm.party_segment (party_sk, segment_type_cd, segment_cd, source_system_cd)
                SELECT :p, t.value_sk, v.value_sk, (SELECT source_system_sk FROM rdm.source_system WHERE source_system_cd='SAP_CRM')
                FROM rdm.vw_rdm_lookup t, rdm.vw_rdm_lookup v WHERE t.catalog_code='CAT_SEGMENT_TYPE' AND t.value_code='AFFILIATION'
                  AND v.catalog_code='CAT_SEGMENT_TYPE' AND v.value_code='B'"""), {"p": p})


def test_case_O_relationships_person_org():
    rep, org1, org2 = (party_of("SAP_CRM", CASES["O"][k]) for k in ("rep", "org1", "org2"))
    mother, child = party_of("SAP_CRM", CASES["O"]["mother"]), party_of("SAP_CRM", CASES["O"]["child"])
    rels = {(r[0], r[1], r[2]) for r in q("""SELECT r.from_party_sk, r.to_party_sk, rt.value_code FROM mdm.party_relationship r
                                             JOIN rdm.reference_value rt ON rt.value_sk=r.relationship_type_cd""").all()}
    assert (rep, org1, "LEGAL_REP_OF") in rels and (org2, org1, "SUBSIDIARY_OF") in rels
    assert (mother, child, "PARENT_OF") in rels and (child, mother, "CHILD_OF") in rels    # inversa generada
    assert not any(t == "SPOUSE_OF" for _, _, t in rels)
    rej = q("SELECT detail FROM mdm.party_dq_issue WHERE field='relationship' AND party_sk=:p", p=rep).scalar_one()
    assert rej["relationship"] == "SPOUSE_OF" and rej["to_type"] == "ORGANIZATION"


def test_case_P_rehomologate(client):
    p = party_of("SAP_CRM", CASES["P"]["crm_bp"])
    assert q("SELECT role_cd FROM mdm.party_role WHERE party_sk=:p", p=p).scalar_one() == 0
    issue = q("SELECT dq_issue_sk, detail FROM mdm.party_dq_issue WHERE party_sk=:p AND detail->>'source_value'='ZPRV' AND resolved_at IS NULL", p=p).one()
    assert issue[1]["target_table"] == "party_role" and issue[1]["target_column"] == "role_cd"
    r = client.post("/api/v1/rdm/mappings", json={"system": "SAP_CRM", "field": "RLTYP", "catalog": "CAT_PARTY_ROLE",
                                                   "source_value": "ZPRV", "value_code": "VENDOR"}, headers={"X-Actor": "steward.crm"})
    assert r.status_code == 201
    r = client.post("/api/v1/rdm/rehomologate", params={"catalog": "CAT_PARTY_ROLE"}, headers={"X-Actor": "steward.crm"})
    assert r.status_code == 200 and r.json()["resolved"] == 1, r.text
    assert q("SELECT v.value_code FROM mdm.party_role pr JOIN rdm.reference_value v ON v.value_sk=pr.role_cd WHERE pr.party_sk=:p", p=p).scalar_one() == "VENDOR"
    assert q("SELECT resolved_at IS NOT NULL FROM mdm.party_dq_issue WHERE dq_issue_sk=:k", k=issue[0]).scalar_one() is True
    audit = q("""SELECT ac.value_code, a.actor FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd
                 WHERE a.party_sk=:p AND a.entity='PARTY_ROLE' ORDER BY a.audit_sk DESC LIMIT 1""", p=p).one()
    assert tuple(audit) == ("REHOMOLOGATE", "steward.crm")
    assert q("SELECT count(*) FROM staging.load_batch WHERE mode='REHOMOLOGATE' AND status='OK'").scalar_one() >= 1


def test_case_R_service_enrollments_and_retention():
    sd = party_of("SAP_ECC_SD", CASES["R"]["ecc_sd"])
    rows = {r[0]: (r[1], r[2], r[3]) for r in q("""SELECT e.source_reference, sv.value_code, es.value_code, bu.value_code
        FROM mdm.party_service_enrollment e JOIN rdm.reference_value sv ON sv.value_sk=e.service_cd
        JOIN rdm.reference_value es ON es.value_sk=e.enrollment_status_cd JOIN rdm.reference_value bu ON bu.value_sk=e.business_unit_cd
        WHERE e.party_sk=:p""", p=sd).all()}
    assert {k: rows[k] for k in ("CR-1001", "CR-0990", "EPS-77")} == {"CR-1001": ("CREDITO_SOCIAL", "ACTIVE", "CREDITO"),
                    "CR-0990": ("CREDITO_SOCIAL", "CLOSED", "CREDITO"), "EPS-77": ("SALUD_EPS", "ACTIVE", "SALUD")}
    ret = q("""SELECT rr.value_code, r.purge_after, e.closed_at FROM mdm.party_data_retention r
               JOIN rdm.reference_value rr ON rr.value_sk=r.retention_rule_cd
               JOIN mdm.party_service_enrollment e ON e.enrollment_sk=r.entity_sk WHERE r.party_sk=:p""", p=sd).one()
    assert ret[0] == "FINANCIAL_10Y" and ret[1] == ret[2] + timedelta(days=3650)
    tx = q("SELECT detail->>'service' FROM mdm.party_dq_issue WHERE party_sk=:p AND field='service'", p=sd).scalars().all()
    assert sorted(tx) == ["HOTEL", "SUPERMERCADO"]
    crm = party_of("SAP_CRM", CASES["R"]["crm_bp"])
    assert crm == sd and rows["AF-R00012"][0] == "CUOTA_MONETARIA"   # una sola persona con los 4 vínculos (F3)


# ------------------------------------------------------------------ otros casos con efecto en F2
def test_case_T_contacts_with_purposes_and_confirmation():
    p = party_of("SAP_CRM", CASES["T"]["crm_bp"])
    links = q("""SELECT c.contact_value, ur.value_code, cf.value_code, og.value_code, l.party_contact_sk FROM mdm.party_contact_point l
        JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk JOIN rdm.reference_value ur ON ur.value_sk=l.usage_role_cd
        JOIN rdm.reference_value cf ON cf.value_sk=l.confirmation_status_cd JOIN rdm.reference_value og ON og.value_sk=l.origin_cd
        WHERE l.party_sk=:p AND c.contact_value LIKE '+57%'""", p=p).all()
    assert len(links) == 4
    by_role = {(r[1], r[2], r[3]) for r in links}
    assert ("OWNER", "CONFIRMED_BY_TITULAR", "TITULAR") in by_role and ("REFERENCE", "UNCONFIRMED", "THIRD_PARTY_REFERENCE") in by_role
    assert ("OWNER", "WRONG_PERSON", "COLLECTIONS_MANAGEMENT") in by_role
    cob = [r[4] for r in links if r[3] == "COLLECTIONS_MANAGEMENT"][0]
    prefs = dict(q("SELECT pu.value_code, pr.allowed FROM mdm.party_contact_pref pr JOIN rdm.reference_value pu ON pu.value_sk=pr.purpose_cd "
                   "WHERE pr.party_contact_sk=:c", c=cob).all())
    assert prefs == {"COLLECTIONS": True, "BENEFITS": False, "COMMERCIAL": False}
    email = q("""SELECT pu.value_code, pr.allowed FROM mdm.party_contact_pref pr JOIN rdm.reference_value pu ON pu.value_sk=pr.purpose_cd
                 JOIN mdm.party_contact_point l ON l.party_contact_sk=pr.party_contact_sk JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk
                 WHERE pr.party_sk=:p AND c.contact_value LIKE '%@%'""", p=p).all()
    assert dict(email) == {"BENEFITS": True, "COLLECTIONS": True, "COMMERCIAL": False}


def test_case_Q_deceased_from_sf_ec():
    p = party_of("SF_EC", CASES["Q"]["sf_ec"])
    assert q("SELECT v.value_code FROM mdm.party pa JOIN rdm.reference_value v ON v.value_sk=pa.party_status_cd WHERE pa.party_sk=:p", p=p).scalar_one() == "DECEASED"


def test_case_G_rerun_is_resolved_by_hash_and_xref(client):
    r = client.post("/api/v1/pipeline/ecc_sd/run", params={"mode": "delta"}, headers={"X-Actor": "pytest"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["extracted"] == MANIFEST["counts"]["ecc_sd"]
    assert b["unchanged_hash"] == MANIFEST["counts"]["ecc_sd"] - 1 and b["loaded"] == 0 and b["dq_quarantined"] == 1
    assert q("SELECT count(*) FROM staging.stg_ecc_sd_raw WHERE raw_status='UNCHANGED' AND batch_id=:b", b=b["batch_id"]).scalar_one() == b["unchanged_hash"]


# ------------------------------------------------------------------ API
def test_api_search_golden_sources_stats(client):
    ext = CASES["R"]["ecc_sd"]
    s = client.get("/api/v1/parties", params={"external_id": ext}).json()
    assert len(s["items"]) == 1 and s["items"][0]["golden_status"] == "GOLDEN"
    sk = s["items"][0]["party_sk"]
    g = client.get(f"/api/v1/parties/{sk}/golden").json()
    assert set(g) == {"core", "sources", "identity", "roles_relationships", "contactability", "governance", "golden_record", "consents"}
    assert len(g["roles_relationships"]["services"]) == 4 and {x["source_system_cd"] for x in g["sources"]} == {"SAP_ECC_SD", "SAP_CRM"}
    src = client.get(f"/api/v1/parties/{sk}/sources").json()
    assert {x["source_system_cd"]: x["rows"] for x in src["lineage"]["party_service_enrollment"]} == {"SAP_ECC_SD": 3, "SAP_CRM": 1}
    st = client.get("/api/v1/stats").json()
    assert sum(x["n"] for x in st["parties"]) == q("SELECT count(*) FROM mdm.party").scalar_one()
    assert client.get("/api/v1/parties", params={"service": "CREDITO_SOCIAL", "limit": 5}).json()["items"]
    assert client.get("/api/v1/parties/999999/golden").status_code == 404
