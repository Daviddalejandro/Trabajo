"""Conjunto de validación completo (`make test-validation`): dos fuentes nuevas —un extracto SAP ECC
(KNA1, adaptador `ecc_sd`) y un sistema de crédito / core de cartera (`credito_core`)— con 25 casos
plantados V1–V28 que recorren todas las funcionalidades del prototipo: RDM y homologación, pipeline
(landing, estandarización, DQ, 1NF, XREF, delta), matching y survivorship, stewardship (owners,
unmerge, NO_MATCH vinculante), elegibilidad de contacto, consentimientos, ARCO, RNE, audiencias,
retención y purga, feed de cambios, Vista 360, match-preview y export a Drive.

La suite vacía staging y mdm (el RDM se conserva), genera los datasets con seed fija y los ingiere."""
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import engine
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
VAL = ROOT / "data" / "validation"
ECC_FILE, CREDIT_FILE, DELTA_FILE, RNE_FILE = "data/validation/ecc_kna1_validacion.csv", "data/validation/credito_core.csv", "data/validation/credito_core_delta.csv", "data/validation/rne_validacion.csv"
E, K = "CREDITO_CORE", "SAP_ECC_SD"


def run(*args: str) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, "cli.py", *args], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


@pytest.fixture(scope="module", autouse=True)
def validation_dataset():
    run("validation-generate")
    run("reset-mdm", "--yes")
    run("ingest", "--source", "ecc_sd", "--file", ECC_FILE, "--actor", "validation")
    run("ingest", "--source", "credito_core", "--file", CREDIT_FILE, "--actor", "validation")
    yield


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def M() -> dict:
    return json.loads((VAL / "manifest_validacion.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def C(M) -> dict:
    return M["cases"]


def q(sql, **p):
    with engine.connect() as conn:
        return conn.execute(text(sql), p)


def pof(system: str, external_id: str) -> int:
    return q("SELECT x.party_sk FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd "
             "WHERE s.source_system_cd=:s AND x.external_id=:e", s=system, e=external_id).scalar_one()


def status_of(party_sk: int) -> tuple[str, str]:
    return q("SELECT g.value_code, st.value_code FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd "
             "JOIN rdm.reference_value st ON st.value_sk=p.party_status_cd WHERE p.party_sk=:p", p=party_sk).one()


def decision(a: int, b: int):
    return q("SELECT m.match_sk, d.value_code, m.match_status, m.total_score FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd "
             "WHERE (party_a_sk, party_b_sk) IN ((:a,:b),(:b,:a))", a=a, b=b).first()


def reasons(client, party_sk: int) -> dict:
    return {(c["contact_value"], p["purpose"]): p["reason"] for c in client.get(f"/api/v1/parties/{party_sk}/contactability").json() for p in c["purposes"]}


def credit_row(ext_id: str) -> dict:
    with (VAL / "credito_core.csv").open(encoding="utf-8") as f:
        return next(r for r in csv.DictReader(f) if r["ID_CLIENTE"] == ext_id)


# ================================================================== 1 · RDM
def test_rdm_credit_source_registered_with_owner_and_steward(client):
    s = next(x for x in client.get("/api/v1/rdm/source-systems").json() if x["source_system_cd"] == E)
    assert s["is_prototype_active"] and s["data_owner"] == "Gerencia de Crédito Social" and s["data_steward"] == "steward.credito"


def test_rdm_all_credit_codes_resolve_except_planted_unknown(client, M):
    used = set()
    with (VAL / "credito_core.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            used.add(("TIPO_ID", r["TIPO_ID"])); used.add(("SEXO", r["SEXO"])); used.add(("CALIFICACION", r["CALIFICACION"]))
            for o in filter(None, r["OBLIGACIONES"].split(";")):
                num, prod, st, *_ = o.split(":"); used.add(("PRODUCTO", prod)); used.add(("ESTADO_OBLIG", st))
            for t in filter(None, r["TEL_ALTERNOS"].split(";")):
                _, tipo, est = t.split(":"); used.add(("TIPO_TEL", tipo)); used.add(("ESTADO_TEL", est))
    unresolved = {(f, v) for f, v in used if v and client.get("/api/v1/rdm/homologate", params={"system": E, "field": f, "value": v}).status_code == 404}
    assert unresolved == {("PRODUCTO", "LB")}                                  # V12: único código sin homologar, plantado


def test_rdm_crosswalk_credit_gender_to_crm_and_sf(client):
    rows = client.get("/api/v1/rdm/crosswalk", params={"from_system": E, "field": "SEXO", "value": "H"}).json()
    assert {(r["to_system_cd"], r["to_field"], r["to_value"]) for r in rows} >= {("SAP_CRM", "GESCHL", "1"), ("SF_EC", "gender", "M")}   # V24


# ================================================================== 2 · Pipeline
def test_load_batches_and_counts(M):
    rows = {r[0]: r for r in q("""SELECT s.source_system_cd, b.status, b.extracted, b.dq_passed, b.dq_quarantined, b.loaded, b.unknown_codes, b.auto_merged, b.probable
        FROM staging.load_batch b JOIN rdm.source_system s ON s.source_system_sk=b.source_system_cd WHERE b.actor='validation' ORDER BY b.batch_id""").all()}
    assert rows[K][1] == "OK" and rows[K][2] == M["counts"]["ecc_kna1_validacion"] and rows[K][4] == 0
    assert rows[E][1] == "OK" and rows[E][2] == M["counts"]["credito_core"] and rows[E][4] == 1 and rows[E][6] == 1     # V12
    assert rows[E][7] >= 150 and rows[E][3] + rows[E][4] == rows[E][2]


def test_V12_quality_quarantine_warning_and_unknown_code(C):
    assert q("SELECT raw_status FROM staging.stg_credito_core_raw WHERE external_id=:e", e=C["V12"]["credit_missing_doc"]).scalar_one() == "DQ_QUARANTINE"
    assert q("SELECT count(*) FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd WHERE s.source_system_cd=:s AND x.external_id=:e",
             s=E, e=C["V12"]["credit_missing_doc"]).scalar_one() == 0
    bad = pof(K, C["V12"]["ecc_bad_phone"])
    issues = q("SELECT c.value_code, sv.value_code FROM mdm.party_dq_issue i JOIN rdm.reference_value c ON c.value_sk=i.dq_category_cd JOIN rdm.reference_value sv ON sv.value_sk=i.severity_cd WHERE i.party_sk=:p", p=bad).all()
    assert any(cat == "VALIDITY" and sev == "WARNING" for cat, sev in issues) and status_of(bad)[0] == "GOLDEN"
    assert q("SELECT count(*) FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd WHERE l.party_sk=:p AND ch.value_code='PHONE'", p=bad).scalar_one() == 0
    unk = q("SELECT detail FROM mdm.party_dq_issue WHERE resolved_at IS NULL AND detail->>'catalog'='CAT_SERVICE'").all()
    assert len(unk) == 1 and unk[0][0]["source_value"] == "LB" and unk[0][0]["target_table"] == "party_service_enrollment"


def test_standardization_e164_lowercase_email_and_dates(client, C):
    p = pof(K, C["V19"]["ecc"])
    g = client.get(f"/api/v1/parties/{p}/golden").json()
    phones = [c["contact_value"] for c in g["contactability"]["contacts"] if c["channel"] == "PHONE"]
    emails = [c["contact_value"] for c in g["contactability"]["contacts"] if c["channel"] == "EMAIL"]
    assert phones and all(v.startswith("+57") and len(v) == 13 for v in phones)
    assert emails and all(v == v.lower() for v in emails)
    row = credit_row(C["V19"]["credit"]); d, m, y = row["FECHA_NAC"].split("/")
    assert g["core"]["birth_date"] == f"{y}-{m}-{d}"                          # dd/mm/yyyy del core → ISO


def test_1nf_obligations_roles_and_retention(client, C):
    p = pof(K, C["V22"]["ecc"])
    srv = client.get(f"/api/v1/parties/{p}/services").json()
    assert len(srv) == 3 and {s["source_system_cd"] for s in srv} == {K, E}
    credit = [s for s in srv if s["source_system_cd"] == E]
    assert {s["business_unit"] for s in credit} == {"CREDITO"} and {s["status"] for s in credit} == {"ACTIVE", "CLOSED"}
    closed = next(s for s in credit if s["status"] == "CLOSED")
    ret = q("SELECT rr.value_code, r.purge_after FROM mdm.party_data_retention r JOIN rdm.reference_value rr ON rr.value_sk=r.retention_rule_cd WHERE r.entity='PARTY_SERVICE_ENROLLMENT' AND r.entity_sk=:k", k=closed["enrollment_sk"]).one()
    assert ret[0] == "FINANCIAL_10Y" and ret[1].year in (2032, 2033)          # cierre 2023 + 10 años
    g = client.get(f"/api/v1/parties/{p}/golden").json()
    roles = {(r["role"], r["business_unit"], r["source_system_cd"]) for r in g["roles_relationships"]["roles"]}
    # el cliente es de crédito (CREDITO_CORE); SAP ECC SD aporta el rol del interlocutor comercial (BPROL)
    assert ("CUSTOMER", "CREDITO", E) in roles and ("AFFILIATE", "SUBSIDIO", K) in roles
    assert not any(r["role"] == "CUSTOMER" and r["source_system_cd"] == K for r in g["roles_relationships"]["roles"])


def test_V22_segment_authoritative_source_kept(C):
    p = pof(K, C["V22"]["ecc"])
    segs = q("SELECT v.value_code, s.valid_to IS NULL AS current, ss.source_system_cd FROM mdm.party_segment s JOIN rdm.reference_value t ON t.value_sk=s.segment_type_cd "
             "JOIN rdm.reference_value v ON v.value_sk=s.segment_cd JOIN rdm.source_system ss ON ss.source_system_sk=s.source_system_cd WHERE s.party_sk=:p AND t.value_code='FINANCIAL_RISK'", p=p).all()
    current = [r for r in segs if r[1]]
    assert len(current) == 1 and current[0][0] == "LOW" and current[0][2] == K        # SAP_ECC_SD es la fuente autoritativa del tipo
    assert any(r[0] == "HIGH" and not r[1] and r[2] == E for r in segs)


def test_V14_guarantor_relationship_with_inverse(client, C):
    d, g = pof(E, C["V14"]["deudor"]), pof(E, C["V14"]["codeudor"])
    rels = client.get(f"/api/v1/parties/{d}/relationships").json()
    assert {(r["relationship_type"], r["direction"], r["other_party_sk"]) for r in rels} >= {("GUARANTEED_BY", "OUT", g), ("GUARANTOR_OF", "IN", g)}
    inv = client.get(f"/api/v1/parties/{g}/relationships", params={"direction": "out"}).json()
    assert any(r["relationship_type"] == "GUARANTOR_OF" and r["other_party_sk"] == d for r in inv)


# ================================================================== 3 · Matching y survivorship
def test_V1_auto_merge_same_document_typo(C):
    a, b = pof(K, C["V1"]["ecc"]), pof(E, C["V1"]["credit"])
    assert a == b and status_of(a) == ("GOLDEN", "ACTIVE")
    h = q("SELECT mt.value_code, h.decided_by FROM mdm.party_merge_history h JOIN rdm.reference_value mt ON mt.value_sk=h.merge_type_cd WHERE h.surviving_party_sk=:p", p=a).first()
    assert h[0] == "AUTO" and h[1].startswith("engine.v1.p")
    assert q("SELECT count(*) FROM mdm.party_identifier WHERE party_sk=:p AND is_golden", p=a).scalar_one() == 1


def test_V1_same_address_from_both_sources_kept_once(C):
    p = pof(K, C["V1"]["ecc"])
    rows = q("SELECT address_line, is_primary FROM mdm.party_address WHERE party_sk=:p", p=p).all()
    assert rows and len(rows) == len({r[0] for r in rows}) and sum(1 for r in rows if r[1]) == 1


def test_V4_duplicates_inside_credit_source_collapse(C):
    assert pof(E, C["V4"]["credit_1"]) == pof(E, C["V4"]["credit_2"]) == pof(K, C["V4"]["ecc"])
    p = pof(K, C["V4"]["ecc"])
    assert q("SELECT count(*) FROM mdm.xref_party_source WHERE party_sk=:p", p=p).scalar_one() == 3
    assert q("SELECT count(*) FROM mdm.party_service_enrollment WHERE party_sk=:p", p=p).scalar_one() == 3


def test_V5_organization_same_nit(C):
    a, b = pof(K, C["V5"]["ecc"]), pof(E, C["V5"]["credit"])
    assert a == b and q("SELECT t.value_code FROM mdm.party p JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd WHERE p.party_sk=:p", p=a).scalar_one() == "ORGANIZATION"
    assert q("SELECT id_number FROM mdm.party_identifier WHERE party_sk=:p AND is_golden", p=a).scalar_one() == C["V5"]["nit"]


def test_V2_V3_V18_probable_and_possible_never_merge_alone(C):
    # V2 por el grupo G3 (sin celular común), V3 por G2 con documento contradictorio (veto en modo REVIEW: nunca auto),
    # V18 por G4 bajado a revisión por el veto del documento (dígito transpuesto)
    for case, expected in (("V2", "PROBABLE"), ("V3", "PROBABLE"), ("V18", "PROBABLE")):
        a, b = pof(K, C[case]["ecc"]), pof(E, C[case]["credit"])
        assert a != b, case
        d = decision(a, b)
        assert d and d[1] == expected and d[2] == "PENDING", (case, d)
    assert q("SELECT count(*) FROM mdm.party_match m JOIN mdm.party a ON a.party_sk=m.party_a_sk JOIN mdm.party b ON b.party_sk=m.party_b_sk WHERE a.party_type_cd<>b.party_type_cd").scalar_one() == 0


def test_V19_survivorship_priority_and_most_recent(C):
    p = pof(K, C["V19"]["ecc"])
    win = {r[0]: (r[1], r[2]) for r in q("SELECT sv.field_name, s.source_system_cd, sv.winning_value FROM mdm.party_survivorship sv LEFT JOIN rdm.source_system s ON s.source_system_sk=sv.winning_source_cd WHERE sv.party_sk=:p", p=p).all()}
    assert win["first_name"][0] == K and win["first_name"][1] == win["first_name"][1].title()
    assert win["email"][0] == E and win["email"][1].startswith("reciente.")
    assert q("SELECT golden_version FROM mdm.party WHERE party_sk=:p", p=p).scalar_one() >= 2


# ================================================================== 4 · Stewardship
def test_V2_owner_consensus_then_unmerge_and_binding_no_match(client, C):
    a, b = pof(K, C["V2"]["ecc"]), pof(E, C["V2"]["credit"])
    m = decision(a, b)
    r = client.post(f"/api/v1/matches/{m[0]}/decision", json={"action": "MERGE", "justification": "Tarjeta de identidad antigua: misma persona confirmada por fecha, correo y celular"},
                    headers={"X-Actor": "steward.mdm"}).json()
    assert r["result"] == "IN_REVIEW" and set(r["sources"]) == {K, E}
    tasks = [t for t in client.get("/api/v1/review-tasks", params={"status": "RECEIVED"}).json() if t["match_sk"] == m[0]]
    assert {t["assignee"] for t in tasks} == {"steward.sd", "steward.credito"}
    for t in tasks:
        out = client.post(f"/api/v1/review-tasks/{t['task_sk']}/decision", json={"decision": "MERGE", "justification": "Cliente verificado en cartera"}, headers={"X-Actor": t["assignee"]}).json()
    assert out["result"] == "MERGED" and out["merge_type"] == "OWNER_CONSENSUS"
    assert pof(K, C["V2"]["ecc"]) == pof(E, C["V2"]["credit"])
    surv = pof(K, C["V2"]["ecc"])
    assert q("SELECT count(*) FROM mdm.party_address WHERE party_sk=:p AND is_primary", p=surv).scalar_one() == 1
    u = client.post(f"/api/v1/parties/{surv}/unmerge", json={"merge_sk": out["merge_sk"], "reason": "El owner de cartera corrige: eran dos personas"}, headers={"X-Actor": "steward.mdm"}).json()
    assert u["restored_rows"] > 0 and pof(K, C["V2"]["ecc"]) != pof(E, C["V2"]["credit"])
    for party in (pof(K, C["V2"]["ecc"]), pof(E, C["V2"]["credit"])):   # cada uno recupera su dirección principal
        assert q("SELECT count(*) FROM mdm.party_address WHERE party_sk=:p AND is_primary", p=party).scalar_one() == 1
    again = client.post("/api/v1/matching/run", headers={"X-Actor": "validation"}).json()
    assert pof(K, C["V2"]["ecc"]) != pof(E, C["V2"]["credit"]) and again["auto_merged"] == 0


def test_V18_steward_no_match_is_final(client, C):
    a, b = pof(K, C["V18"]["ecc"]), pof(E, C["V18"]["credit"])
    m = decision(a, b)
    assert client.post(f"/api/v1/matches/{m[0]}/decision", json={"action": "NO_MATCH", "justification": ""}).status_code == 422
    r = client.post(f"/api/v1/matches/{m[0]}/decision", json={"action": "NO_MATCH", "justification": "Documento distinto verificado contra la Registraduría"}, headers={"X-Actor": "steward.mdm"}).json()
    assert r["result"] == "NO_MATCH"
    client.post("/api/v1/matching/run", headers={"X-Actor": "validation"})
    assert decision(a, b)[2] == "RESOLVED" and pof(K, C["V18"]["ecc"]) != pof(E, C["V18"]["credit"])


# ================================================================== 5 · Cumplimiento
def test_V6_deceased_blocks_everything(client, C):
    p = pof(E, C["V6"]["credit"])
    assert status_of(p)[1] == "DECEASED" and set(reasons(client, p).values()) == {"DECEASED"}


def test_V7_commercial_consent_denied_collections_ok(client, C):
    r = reasons(client, pof(E, C["V7"]["credit"]))
    assert {v for (_, pu), v in r.items() if pu == "COMMERCIAL"} == {"CONSENT_REVOKED"}
    assert {v for (_, pu), v in r.items() if pu == "COLLECTIONS"} == {"ELIGIBLE"}


def test_V8_closed_only_obligations(client, C):
    r = reasons(client, pof(E, C["V8"]["credit"]))
    assert {v for (_, pu), v in r.items() if pu == "COLLECTIONS"} == {"NO_ACTIVE_SERVICE"}
    assert {v for (_, pu), v in r.items() if pu == "BENEFITS"} == {"ELIGIBLE"}


def test_V9_suspended_obligation_still_collectable(client, C):
    p = pof(E, C["V9"]["credit"])
    assert {v for (_, pu), v in reasons(client, p).items() if pu == "COLLECTIONS"} == {"ELIGIBLE"}
    assert q("SELECT es.value_code FROM mdm.party_service_enrollment e JOIN rdm.reference_value es ON es.value_sk=e.enrollment_status_cd JOIN rdm.source_system s ON s.source_system_sk=e.source_system_cd WHERE e.party_sk=:p AND s.source_system_cd=:s", p=p, s=E).scalar_one() == "SUSPENDED"


def test_V10_collection_phones_purposes(client, C):
    p = pof(E, C["V10"]["credit"]); r = reasons(client, p); own, tit, ref, err = [f"+57{x}" for x in C["V10"]["phones"]]
    assert r[(own, "COMMERCIAL")] == "ELIGIBLE" and r[(own, "COLLECTIONS")] == "ELIGIBLE"
    assert r[(tit, "COLLECTIONS")] == "ELIGIBLE" and r[(tit, "COMMERCIAL")] == "CONTACT_PURPOSE_DENIED"
    assert r[(ref, "COLLECTIONS")] == "ELIGIBLE" and r[(ref, "COMMERCIAL")] == "THIRD_PARTY_CONTACT"
    assert r[(err, "COLLECTIONS")] == "INVALID_CONTACT"
    work = client.get(f"/api/v1/parties/{p}/contacts", params={"purpose": "COLLECTIONS"}).json()
    assert {w["contact_value"] for w in work if w["channel"] == "PHONE"} == {own, tit, ref}     # el errado queda fuera de la lista de cobranza
    origins = {w["contact_value"]: w["origin"] for w in client.get(f"/api/v1/parties/{p}/contacts").json()}
    assert origins[tit] == "COLLECTIONS_MANAGEMENT" and origins[ref] == "THIRD_PARTY_REFERENCE"


def test_V11_rne_sync_only_commercial(client, C):
    p = pof(E, C["V11"]["credit"]); phone = f"+57{C['V11']['phone']}"
    r = client.post("/api/v1/rne/sync", json={"file": RNE_FILE}, headers={"X-Actor": "validation"}).json()
    assert r["marked"] >= 1
    rr = reasons(client, p)
    assert rr[(phone, "COMMERCIAL")] == "RNE_EXCLUSION" and rr[(phone, "COLLECTIONS")] == "ELIGIBLE" and rr[(phone, "BENEFITS")] == "ELIGIBLE"


def test_V16_collections_audience_by_service(client, C):
    a = client.get("/api/v1/audiences", params={"purpose": "COLLECTIONS", "channel": "PHONE", "service": "CREDITO_SOCIAL", "enrollment_status": "ACTIVE", "limit": 5000},
                   headers={"X-Actor": "cobranza"}).json()
    sks = {x["party_sk"] for x in a["items"]}
    assert pof(E, C["V16"]["credit"]) in sks and pof(K, C["V1"]["ecc"]) in sks
    assert pof(E, C["V8"]["credit"]) not in sks and pof(E, C["V6"]["credit"]) not in sks
    assert a["audited"] and all(x["reason"] == "ELIGIBLE" for x in a["items"])
    com = client.get("/api/v1/audiences", params={"purpose": "COMMERCIAL", "channel": "PHONE", "limit": 5000}, headers={"X-Actor": "campanas"}).json()
    assert pof(E, C["V11"]["credit"]) not in {x["party_sk"] for x in com["items"] if x["contact_value"] == f"+57{C['V11']['phone']}"}


def test_V15_arco_cancellation_and_V8_purge_candidates(client, C):
    p = pof(E, C["V15"]["credit"])
    r = client.post(f"/api/v1/parties/{p}/arco", json={"arco_type": "CANCELLATION", "channel_received": "OFICINA"}, headers={"X-Actor": "oficial.datos"}).json()
    assert r["sla_business_days"] == 15 and "3 consentimientos revocados" in r["actions"]
    assert all(v in ("CONSENT_REVOKED", "NO_CONSENT") for v in reasons(client, p).values())
    purge = client.get("/api/v1/retention/purge-candidates", headers={"X-Actor": "retention"}).json()
    sks = {x["party_sk"] for x in purge["items"]}
    assert pof(E, C["V8"]["credit"]) in sks                                     # retención FINANCIAL_10Y vencida, sin obligación vigente
    assert p not in sks                                                          # obligación vigente: no es candidato aunque tenga la marca
    assert q("SELECT count(*) FROM mdm.party").scalar_one() > 0
    lst = client.get("/api/v1/arco/requests", params={"party_sk": p}).json()
    assert lst[0]["sla_status"] == "ON_TRACK" and lst[0]["status"] == "IN_PROGRESS"


def test_V12_rehomologate_new_product_recomputes_eligibility(client, C):
    r = client.post("/api/v1/rdm/catalogs/CAT_SERVICE/values", json={"value_code": "LIBRANZA", "value_name": "Crédito por libranza", "parent_value_code": "CREDITO",
                                                                        "attributes": {"service_kind": "PERSISTENT", "collections_applies": "true"}}, headers={"X-Actor": "rdm-admin"})
    assert r.status_code in (201, 409)
    r = client.post("/api/v1/rdm/mappings", json={"system": E, "field": "PRODUCTO", "catalog": "CAT_SERVICE", "source_value": "LB", "value_code": "LIBRANZA"}, headers={"X-Actor": "rdm-admin"})
    assert r.status_code == 201
    prev = client.get("/api/v1/rdm/rehomologate/preview", params={"catalog": "CAT_SERVICE"}).json()
    assert prev["resolvable"] == 1
    out = client.post("/api/v1/rdm/rehomologate", params={"catalog": "CAT_SERVICE"}, headers={"X-Actor": "rdm-admin"}).json()
    assert out["resolved"] == 1 and out.get("eligibility_recomputed") == 1
    p = pof(E, C["V12"]["credit_unknown_product"])
    assert q("SELECT v.value_code FROM mdm.party_service_enrollment e JOIN rdm.reference_value v ON v.value_sk=e.service_cd JOIN rdm.source_system s ON s.source_system_sk=e.source_system_cd "
             "WHERE e.party_sk=:p AND s.source_system_cd=:s", p=p, s=E).scalar_one() == "LIBRANZA"
    assert {v for (_, pu), v in reasons(client, p).items() if pu == "COLLECTIONS"} == {"ELIGIBLE"}


# ================================================================== 6 · Delta, idempotencia, feed, vista 360, preview, export, auditoría
def test_V13_delta_updates_golden_without_rematch(client, C):
    p = pof(K, C["V13"]["ecc"])
    before = q("SELECT golden_version FROM mdm.party WHERE party_sk=:p", p=p).scalar_one()
    r = client.post("/api/v1/pipeline/credito_core/run", params={"mode": "delta", "file": DELTA_FILE}, headers={"X-Actor": "validation"}).json()
    assert r["extracted"] == 1 and r["xref_hits"] == 1 and r["loaded"] == 1 and r["matched"] == 0
    win = q("SELECT winning_value FROM mdm.party_survivorship WHERE party_sk=:p AND field_name='email'", p=p).scalar_one()
    assert win == C["V13"]["new_email"] and q("SELECT golden_version FROM mdm.party WHERE party_sk=:p", p=p).scalar_one() > before
    assert pof(E, C["V13"]["credit"]) == p


def test_V23_full_rerun_is_idempotent(client):
    for src, f in ((K, ECC_FILE), (E, CREDIT_FILE)):
        r = client.post(f"/api/v1/pipeline/{'ecc_sd' if src == K else 'credito_core'}/run", params={"mode": "full", "file": f}, headers={"X-Actor": "validation"}).json()
        assert r["unchanged_hash"] + r["dq_quarantined"] + r["loaded"] == r["extracted"] and r["matched"] == 0, r
        assert r["loaded"] <= 1                                                  # solo la fila con correo nuevo del delta vuelve a cargarse (V13)


def test_V20_changes_feed_shows_credit_enrollments(client):
    since = q("SELECT min(started_at) FROM staging.load_batch WHERE actor='validation'").scalar_one()
    r = client.get("/api/v1/changes", params={"since": since.isoformat(), "entity": "PARTY_SERVICE_ENROLLMENT", "limit": 2000}).json()
    assert r["items"] and any(x["source_system_cd"] == E and x["action"] == "INSERT" for x in r["items"])


def test_V22_golden_360_of_merged_party(client, C):
    p = pof(K, C["V22"]["ecc"])
    g = client.get(f"/api/v1/parties/{p}/golden").json()
    assert {s["source_system_cd"] for s in g["sources"]} == {K, E}
    assert len(g["roles_relationships"]["services"]) == 3 and len(g["contactability"]["contacts"]) >= 2
    assert {s["field_name"] for s in g["golden_record"]["survivorship"]} >= {"first_name", "first_surname", "document", "email", "phone"}
    assert any(m["merge_type"] == "AUTO" for m in g["golden_record"]["merges"])
    src = client.get(f"/api/v1/parties/{p}/sources").json()
    assert {r["source_system_cd"] for r in src["lineage"]["party_service_enrollment"]} == {K, E}
    assert all(e["purpose"] in ("COLLECTIONS", "BENEFITS", "COMMERCIAL") for e in g["contactability"]["eligibility"])


def test_V26_beneficiary_role_and_party_to_party_relationship(client, C):
    """BPROL=ZBEN: rol AFFILIATE con sub-rol AFFILIATE_BENEFICIARY y relación BENEFICIARY_OF con el titular."""
    ben, tit = pof(K, C["V26"]["beneficiario_ecc"]), pof(K, C["V26"]["titular_ecc"])
    g = client.get(f"/api/v1/parties/{ben}/golden").json()
    rol = next(r for r in g["roles_relationships"]["roles"] if r["source_system_cd"] == K)
    assert (rol["role"], rol["sub_role"], rol["business_unit"]) == ("AFFILIATE", "AFFILIATE_BENEFICIARY", "SUBSIDIO")
    rels = {(r["direction"], r["relationship_type"], r["other_party_sk"]) for r in g["roles_relationships"]["relationships"]}
    assert ("OUT", "BENEFICIARY_OF", tit) in rels
    assert any(r["other_party_sk"] == ben for r in client.get(f"/api/v1/parties/{tit}/golden").json()["roles_relationships"]["relationships"])


def test_V27_two_roles_from_one_source_record(client, C):
    """BPROL multivalor (BUT100): un mismo KUNNR es afiliado y proveedor de servicios."""
    p = pof(K, C["V27"]["ecc"])
    roles = {(r["role"], r["sub_role"], r["business_unit"]) for r in client.get(f"/api/v1/parties/{p}/golden").json()["roles_relationships"]["roles"] if r["source_system_cd"] == K}
    assert ("AFFILIATE", "AFFILIATE_WORKER", "SUBSIDIO") in roles
    assert ("VENDOR", "VENDOR_SERVICES", "NOT_APPLICABLE") in roles   # el proveedor no se ejerce en una UES


def test_V28_unmapped_bprol_leaves_unknown_role_and_dq_issue(C):
    p = pof(K, C["V28"]["ecc"])
    assert q("SELECT role_cd FROM mdm.party_role WHERE party_sk=:p", p=p).scalar_one() == 0
    issue = q("""SELECT detail FROM mdm.party_dq_issue WHERE party_sk=:p AND detail->>'source_value'=:v
                 AND detail->>'target_column'='role_cd' AND resolved_at IS NULL""", p=p, v=C["V28"]["source_value"]).scalar_one()
    assert issue["target_table"] == "party_role"


def test_affiliation_segment_comes_from_ecc_category(client, C):
    """El extracto de SD trae la categoría de afiliación: la Vista 360 muestra dos tipos de segmento."""
    p = pof(K, C["V26"]["titular_ecc"])
    segs = {(s["segment_type"], s["segment"], s["source_system_cd"]) for s in client.get(f"/api/v1/parties/{p}/golden").json()["roles_relationships"]["segments"]}
    assert ("AFFILIATION", "A", K) in segs
    tipos = q("SELECT count(DISTINCT t.value_code) FROM mdm.party_segment g JOIN rdm.reference_value t ON t.value_sk=g.segment_type_cd").scalar_one()
    assert tipos >= 2   # AFFILIATION (ECC) y FINANCIAL_RISK (ECC/crédito)


def test_V17_match_preview_finds_existing_golden_without_persisting(client, C):
    row = credit_row(C["V1"]["credit"])
    before = q("SELECT count(*) FROM mdm.party_match").scalar_one()
    names = row["NOMBRES"].split(); surs = row["APELLIDOS"].split()
    d, m, y = row["FECHA_NAC"].split("/")
    r = client.post("/api/v1/parties/match-preview", json={"party_type": "PERSON", "first_name": names[0], "first_surname": surs[0], "second_surname": surs[1] if len(surs) > 1 else None,
                                                             "birth_date": f"{y}-{m}-{d}", "identifiers": [{"id_type": "CC", "id_number": row["NUM_ID"]}], "emails": [row["EMAIL"]], "phones": [row["CELULAR"]]}).json()
    assert r["persisted"] is False and r["candidates"] and r["candidates"][0]["party_sk"] == pof(K, C["V1"]["ecc"]) and r["candidates"][0]["decision"] == "AUTO_MERGE"
    assert q("SELECT count(*) FROM mdm.party_match").scalar_one() == before


def test_V25_audit_rows_of_credit_only_party(C):
    p = pof(E, C["V8"]["credit"])
    rows = q("""SELECT a.entity, ac.value_code, a.batch_id, s.source_system_cd, a.actor FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd
                LEFT JOIN rdm.source_system s ON s.source_system_sk=a.source_system_cd WHERE a.party_sk=:p AND ac.value_code='INSERT'""", p=p).all()
    core = [r for r in rows if r[0] not in ("PARTY_SURVIVORSHIP", "PARTY_MERGE_HISTORY")]
    assert {r[0] for r in core} >= {"PARTY", "PARTY_PERSON", "XREF_PARTY_SOURCE", "PARTY_IDENTIFIER", "PARTY_SERVICE_ENROLLMENT", "PARTY_CONSENT", "PARTY_DATA_RETENTION"}
    assert all(r[2] is not None and r[3] == E and r[4] == "validation" for r in core)


def test_V21_export_drive_includes_credit_source(tmp_path):
    from openpyxl import load_workbook

    from app.core.db import SessionLocal
    from app.export.drive import export_all

    with SessionLocal() as session:
        files = export_all(session, tmp_path / "drive")
    assert any("catalogos_rdm" in f for f in files)
    ws = load_workbook(next((tmp_path / "drive" / "02_RDM").iterdir()))["Sistemas fuente"]
    assert any(row[0] == E for row in ws.iter_rows(min_row=2, values_only=True))
