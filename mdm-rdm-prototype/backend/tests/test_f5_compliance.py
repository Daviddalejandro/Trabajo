"""F5 · Cumplimiento embebido (SPEC §10, §11, §14): casos E, F, H, J, M, Q, S y T, RNE, ARCO con SLA en
días hábiles, audiencias auditadas, purga simulada, feed de cambios y export a Drive. Corre sobre la base
que deja conftest (ingesta con matching) tras las fases anteriores."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.compliance.service import add_business_days, subtract_business_days
from app.core.db import engine
from app.main import app

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "data" / "synth" / "manifest.json").read_text(encoding="utf-8"))
CASES = MANIFEST["cases"]


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def q(sql, **p):
    with engine.connect() as conn:
        return conn.execute(text(sql), p)


def party_of(system: str, external_id: str) -> int:
    return q("SELECT x.party_sk FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd "
             "WHERE s.source_system_cd=:s AND x.external_id=:e", s=system, e=external_id).scalar_one()


def reasons(client, party_sk: int) -> dict:
    out = {}
    for c in client.get(f"/api/v1/parties/{party_sk}/contactability").json():
        for p in c["purposes"]:
            out[(c["contact_value"], p["purpose"])] = p["reason"]
    return out


def cache(party_sk: int) -> dict:
    return {(r[0], r[1]): r[2] for r in q("""SELECT c.contact_value, pu.value_code, rs.value_code FROM mdm.party_contact_eligibility_cache e
        JOIN mdm.party_contact_point l ON l.party_contact_sk=e.party_contact_sk JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk
        JOIN rdm.reference_value pu ON pu.value_sk=e.purpose_cd JOIN rdm.reference_value rs ON rs.value_sk=e.reason_cd WHERE e.party_sk=:p""", p=party_sk).all()}


# ------------------------------------------------------------------ elegibilidad
def test_eligibility_cache_populated_for_all_contacts():
    links = q("SELECT count(*) FROM mdm.party_contact_point WHERE valid_to IS NULL").scalar_one()
    purposes = q("SELECT count(*) FROM rdm.vw_rdm_lookup WHERE catalog_code='CAT_CONTACT_PURPOSE' AND value_sk>0 AND is_active").scalar_one()
    assert q("SELECT count(*) FROM mdm.party_contact_eligibility_cache").scalar_one() == links * purposes


def test_case_E_consent_revoked(client):
    e = party_of("SAP_CRM", CASES["E"]["crm_bp"])
    r = reasons(client, e)
    assert {v for (_, pu), v in r.items() if pu == "COMMERCIAL"} == {"CONSENT_REVOKED"}
    assert cache(e) == r                                             # la caché coincide con la evaluación en vivo
    live = client.get(f"/api/v1/parties/{e}/contactability", params={"purpose": "COMMERCIAL"}).json()
    assert all(len(c["purposes"]) == 1 and c["purposes"][0]["is_eligible"] is False for c in live)


def test_case_H_rne_only_affects_commercial(client):
    h = party_of("SAP_CRM", CASES["H"]["crm_bp"]); phone = f"+57{CASES['H']['phone']}"
    r = client.post("/api/v1/rne/sync", json={"file": "data/synth/rne_sample.csv"}, headers={"X-Actor": "pytest"}).json()
    assert r["numbers_in_registry"] == 21 and r["marked"] + r["cleared"] >= 0
    assert q("SELECT rne_excluded FROM mdm.contact_point WHERE contact_value=:v", v=phone).scalar_one() is True
    rr = reasons(client, h)
    assert rr[(phone, "COMMERCIAL")] == "RNE_EXCLUSION" and rr[(phone, "COLLECTIONS")] == "ELIGIBLE" and rr[(phone, "BENEFITS")] == "ELIGIBLE"
    assert q("SELECT count(*) FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd WHERE ac.value_code='RNE_SYNC'").scalar_one() >= 1
    # un registro sin el número lo retira de la exclusión (sincronización, no acumulación)
    empty = ROOT / "data" / "synth" / "rne_empty_test.csv"; empty.write_text("numero\n+573000000000\n", encoding="utf-8")
    r2 = client.post("/api/v1/rne/sync", json={"file": str(empty)}, headers={"X-Actor": "pytest"}).json()
    assert r2["cleared"] >= 1 and reasons(client, h)[(phone, "COMMERCIAL")] == "ELIGIBLE"
    client.post("/api/v1/rne/sync", json={"file": "data/synth/rne_sample.csv"}, headers={"X-Actor": "pytest"})
    empty.unlink()


def test_case_J_shared_phone_minor(client):
    mother, child = party_of("SAP_CRM", CASES["J"]["mother"]), party_of("SAP_CRM", CASES["J"]["child"]); shared = f"+57{CASES['J']['shared_phone']}"
    m, c = reasons(client, mother), reasons(client, child)
    assert m[(shared, "BENEFITS")] == "ELIGIBLE" and m[(shared, "COMMERCIAL")] == "SHARED_CONTACT_RESTRICTED"
    assert c[(shared, "COMMERCIAL")] == "MINOR" and c[(shared, "BENEFITS")] == "ELIGIBLE"
    assert q("SELECT count(*) FROM mdm.contact_point WHERE contact_value=:v", v=shared).scalar_one() == 1


def test_case_T_purposes_per_contact_and_management_flow(client):
    t = party_of("SAP_CRM", CASES["T"]["crm_bp"]); ph = [f"+57{x}" for x in CASES["T"]["phones"]]
    r = reasons(client, t)
    email = next(k[0] for k in r if "@" in k[0])
    assert r[(email, "BENEFITS")] == "ELIGIBLE" and r[(email, "COLLECTIONS")] == "ELIGIBLE" and r[(email, "COMMERCIAL")] == "CONTACT_PURPOSE_DENIED"
    assert r[(ph[0], "COLLECTIONS")] == "ELIGIBLE" and r[(ph[0], "COMMERCIAL")] == "ELIGIBLE"
    assert r[(ph[1], "COLLECTIONS")] == "ELIGIBLE" and r[(ph[1], "COMMERCIAL")] == "CONTACT_PURPOSE_DENIED"
    assert r[(ph[2], "COLLECTIONS")] == "ELIGIBLE" and r[(ph[2], "COMMERCIAL")] == "THIRD_PARTY_CONTACT"
    assert r[(ph[3], "COLLECTIONS")] == "INVALID_CONTACT" and r[(ph[3], "COMMERCIAL")] in ("INVALID_CONTACT", "CONTACT_PURPOSE_DENIED")   # (6) precede a (7)
    # audiencias: un único número comercial y ningún email
    a = client.get("/api/v1/audiences", params={"purpose": "COMMERCIAL", "channel": "PHONE"}, headers={"X-Actor": "pytest"}).json()
    assert [x["contact_value"] for x in a["items"] if x["party_sk"] == t] == [ph[0]]
    a = client.get("/api/v1/audiences", params={"purpose": "COMMERCIAL", "channel": "EMAIL"}, headers={"X-Actor": "pytest"}).json()
    assert not [x for x in a["items"] if x["party_sk"] == t]
    # lista de trabajo de cobranza y gestión: confirmar el de cobranza y habilitar COMMERCIAL
    work = client.get(f"/api/v1/parties/{t}/contacts", params={"purpose": "COLLECTIONS"}).json()
    assert {w["contact_value"] for w in work} >= {ph[0], ph[1], ph[2]} and ph[3] not in {w["contact_value"] for w in work}
    cob = next(w for w in work if w["contact_value"] == ph[1])
    r1 = client.post(f"/api/v1/parties/{t}/contacts/{cob['party_contact_sk']}/confirmation", json={"status": "CONFIRMED_BY_TITULAR", "evidence": "Llamada 2026-09-13 · titular confirma"},
                     headers={"X-Actor": "gestor.cobranza"}).json()
    assert r1["confirmation_status"] == "CONFIRMED_BY_TITULAR"
    r2 = client.put(f"/api/v1/parties/{t}/contacts/{cob['party_contact_sk']}/purposes", json=[{"purpose": "COMMERCIAL", "allowed": True}], headers={"X-Actor": "gestor.cobranza"}).json()
    assert r2["written"] == 1 and reasons(client, t)[(ph[1], "COMMERCIAL")] == "ELIGIBLE"
    hist = q("SELECT count(*) FROM mdm.party_contact_pref WHERE party_contact_sk=:k AND purpose_cd=(SELECT value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code='CAT_CONTACT_PURPOSE' AND value_code='COMMERCIAL')", k=cob["party_contact_sk"]).scalar_one()
    assert hist == 2                                                  # fila cerrada + fila nueva: nunca se borra el histórico
    acts = q("SELECT count(*) FROM mdm.party_audit_log WHERE party_sk=:p AND actor='gestor.cobranza'", p=t).scalar_one()
    assert acts >= 3


def test_case_S_collections_requires_active_service_then_delta(client):
    s = party_of("SAP_CRM", CASES["S"]["crm_bp"])
    r = reasons(client, s)
    assert {v for (_, pu), v in r.items() if pu == "COLLECTIONS"} == {"NO_ACTIVE_SERVICE"}
    benefits_before = {k: v for k, v in r.items() if k[1] == "BENEFITS"}
    run = client.post("/api/v1/pipeline/ecc_sd/run", params={"mode": "delta", "file": "data/synth/ecc_sd_delta.csv"}, headers={"X-Actor": "pytest"}).json()
    assert run["loaded"] == 1 and run["auto_merged"] == 1
    assert party_of("SAP_ECC_SD", CASES["S"]["delta_kunnr"]) == s
    r2 = reasons(client, s)
    assert {v for (_, pu), v in r2.items() if pu == "COLLECTIONS"} == {"ELIGIBLE"}
    assert {k: v for k, v in r2.items() if k[1] == "BENEFITS"} == benefits_before   # BENEFITS no cambia


# ------------------------------------------------------------------ ARCO, retención, audiencias, feed
def test_business_days_sla():
    start = datetime(2026, 9, 11, 15, 0, tzinfo=timezone.utc)          # viernes
    assert add_business_days(start, 1).date().isoformat() == "2026-09-14"      # lunes
    assert add_business_days(start, 10).date().isoformat() == "2026-09-25"
    assert subtract_business_days(add_business_days(start, 12), 12) == start


def test_case_F_arco_cancellation_on_merged_party(client):
    a = party_of("SAP_ECC_SD", CASES["A"]["ecc_sd"])
    granted = q("SELECT count(*) FROM mdm.party_consent c JOIN rdm.reference_value s ON s.value_sk=c.consent_status_cd WHERE c.party_sk=:p AND c.valid_to IS NULL AND s.value_code='GRANTED'", p=a).scalar_one()
    assert granted >= 1
    r = client.post(f"/api/v1/parties/{a}/arco", json={"arco_type": "CANCELLATION", "channel_received": "OFICINA", "note": "Titular solicita supresión"}, headers={"X-Actor": "oficial.datos"})
    assert r.status_code == 201, r.text
    out = r.json(); sk = out["request_sk"]
    assert out["sla_business_days"] == 15 and datetime.fromisoformat(out["due_at"]) >= datetime.fromisoformat(out["requested_at"]) + timedelta(days=19)   # 15 hábiles ≥ 19 calendario
    assert q("SELECT count(*) FROM mdm.party_consent c JOIN rdm.reference_value s ON s.value_sk=c.consent_status_cd WHERE c.party_sk=:p AND c.valid_to IS NULL AND s.value_code='GRANTED'", p=a).scalar_one() == 0
    assert q("SELECT count(*) FROM mdm.party_consent c JOIN rdm.reference_value s ON s.value_sk=c.consent_status_cd WHERE c.party_sk=:p AND c.valid_to IS NULL AND s.value_code='REVOKED'", p=a).scalar_one() == granted
    assert q("SELECT count(*) FROM mdm.party_data_retention r JOIN rdm.reference_value rr ON rr.value_sk=r.retention_rule_cd WHERE r.party_sk=:p AND rr.value_code='PURGE_ELIGIBLE'", p=a).scalar_one() == 1
    assert q("SELECT count(*) FROM mdm.party_audit_log WHERE party_sk=:p AND arco_request_id=:k", p=a, k=sk).scalar_one() >= 3
    assert all(v in ("CONSENT_REVOKED", "NO_CONSENT") for v in reasons(client, a).values())
    audit = client.get(f"/api/v1/parties/{a}/audit", params={"arco_request_id": sk}).json()
    assert audit and all(x["arco_request_id"] == sk for x in audit)
    lst = client.get("/api/v1/arco/requests", params={"party_sk": a}).json()
    assert lst[0]["request_sk"] == sk and lst[0]["status"] == "IN_PROGRESS" and lst[0]["sla_status"] == "ON_TRACK"
    done = client.patch(f"/api/v1/arco/requests/{sk}", json={"status": "RESOLVED", "note": "Consentimientos revocados y retención marcada"}, headers={"X-Actor": "oficial.datos"}).json()
    assert done["status"] == "RESOLVED"


def test_purge_dry_run_lists_case_F_and_never_deletes(client):
    a = party_of("SAP_ECC_SD", CASES["A"]["ecc_sd"])
    e = party_of("SAP_CRM", CASES["E"]["crm_bp"])                      # sin vínculo de servicio activo
    client.post(f"/api/v1/parties/{e}/arco", json={"arco_type": "CANCELLATION", "channel_received": "OFICINA"}, headers={"X-Actor": "oficial.datos"})
    before = q("SELECT count(*) FROM mdm.party").scalar_one()
    r = client.get("/api/v1/retention/purge-candidates", headers={"X-Actor": "retention"}).json()
    assert r["dry_run"] is True and any(x["party_sk"] == e and x["rule"] == "PURGE_ELIGIBLE" for x in r["items"])
    assert not any(x["party_sk"] == a for x in r["items"])            # el caso A conserva un crédito ACTIVE: no es candidato
    assert q("SELECT count(*) FROM mdm.party").scalar_one() == before
    assert q("SELECT count(*) FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd WHERE ac.value_code='PURGE_SIMULATED' AND a.party_sk=:p", p=e).scalar_one() >= 1


def test_case_Q_deceased_and_overdue_sla(client):
    qp = party_of("SF_EC", CASES["Q"]["sf_ec"])
    assert all(v == "DECEASED" for v in reasons(client, qp).values())
    r = client.post(f"/api/v1/parties/{qp}/arco", json={"arco_type": "ACCESS", "channel_received": "PORTAL",
                                                          "requested_at": subtract_business_days(datetime.now(timezone.utc), 12).isoformat()}, headers={"X-Actor": "pytest"}).json()
    assert r["sla_business_days"] == 10
    overdue = client.get("/api/v1/arco/requests", params={"sla": "OVERDUE"}).json()
    assert any(x["request_sk"] == r["request_sk"] and x["days_past_due"] >= 1 for x in overdue)
    assert q("SELECT count(*) FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd WHERE ac.value_code='ARCO_READ' AND a.arco_request_id=:k", k=r["request_sk"]).scalar_one() == 1


def test_case_M_audience_excludes_and_audits(client):
    before = q("SELECT count(*) FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd WHERE ac.value_code='AUDIENCE_RUN'").scalar_one()
    a = client.get("/api/v1/audiences", params={"purpose": "COMMERCIAL", "channel": "EMAIL", "role": "AFFILIATE"}, headers={"X-Actor": "campanas"}).json()
    assert a["count"] == len(a["items"]) > 0 and all(x["reason"] == "ELIGIBLE" for x in a["items"])
    sks = {x["party_sk"] for x in a["items"]}
    assert party_of("SF_EC", CASES["Q"]["sf_ec"]) not in sks                      # fallecido
    assert party_of("SAP_CRM", CASES["E"]["crm_bp"]) not in sks                   # sin consentimiento comercial
    assert party_of("SAP_CRM", CASES["J"]["child"]) not in sks                    # menor
    minors = q("SELECT count(*) FROM mdm.party_person WHERE party_sk = ANY(:s) AND birth_date > CURRENT_DATE - interval '18 years'", s=list(sks)).scalar_one()
    assert minors == 0
    golden = q("SELECT count(*) FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd WHERE p.party_sk = ANY(:s) AND g.value_code<>'GOLDEN'", s=list(sks)).scalar_one()
    assert golden == 0
    after = q("SELECT count(*) FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd WHERE ac.value_code='AUDIENCE_RUN'").scalar_one()
    assert after == before + 1
    filt = client.get("/api/v1/audiences", params={"purpose": "COMMERCIAL", "channel": "EMAIL", "service": "CREDITO_SOCIAL", "enrollment_status": "ACTIVE"}, headers={"X-Actor": "campanas"}).json()
    assert filt["count"] <= a["count"] + 1000 and filt["audited"]


def test_consents_and_channel_preferences_api(client):
    p = party_of("SAP_CRM", CASES["I"]["crm_bp"])
    r = client.post(f"/api/v1/parties/{p}/consents", json={"consent_type": "COMMERCIAL", "status": "REVOKED", "evidence_ref": "Llamada"}, headers={"X-Actor": "pytest"})
    assert r.status_code == 201
    assert all(v in ("CONSENT_REVOKED",) for (_, pu), v in reasons(client, p).items() if pu == "COMMERCIAL")
    client.post(f"/api/v1/parties/{p}/consents", json={"consent_type": "COMMERCIAL", "status": "GRANTED"}, headers={"X-Actor": "pytest"})
    r = client.put(f"/api/v1/parties/{p}/preferences", json=[{"channel": "EMAIL", "purpose": "COMMERCIAL", "allowed": False}], headers={"X-Actor": "pytest"}).json()
    assert r["written"] == 1
    rr = reasons(client, p)
    assert all(v == "CHANNEL_DENIED" for (val, pu), v in rr.items() if pu == "COMMERCIAL" and "@" in val)
    assert q("SELECT count(*) FROM mdm.party_consent WHERE party_sk=:p AND consent_type_cd=(SELECT value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code='CAT_CONSENT_TYPE' AND value_code='COMMERCIAL')", p=p).scalar_one() >= 3


def test_changes_feed(client):
    r = client.get("/api/v1/changes", params={"limit": 50}).json()
    assert len(r["items"]) == 50 and r["next_cursor"] and {"party_sk", "entity", "action", "golden_version", "occurred_at"} <= set(r["items"][0])
    r2 = client.get("/api/v1/changes", params={"limit": 50, "cursor": r["next_cursor"]}).json()
    assert r2["items"][0]["audit_sk"] > r["items"][-1]["audit_sk"]
    since = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    recent = client.get("/api/v1/changes", params={"since": since, "entity": "PARTY_CONSENT", "limit": 20}).json()
    assert all(x["entity"] == "PARTY_CONSENT" for x in recent["items"])


def test_export_drive_generates_deliverables(tmp_path):
    from app.core.db import SessionLocal
    from app.export.drive import export_all

    with SessionLocal() as session:
        files = export_all(session, tmp_path / "drive")
    names = {Path(f).name for f in files}
    assert any(n.startswith("diccionario_datos") for n in names) and any(n.startswith("catalogos_rdm") for n in names)
    assert "matriz_elegibilidad_12_precedencias.md" in names and any(n.startswith("resumen_ejecutivo") for n in names)
    assert (tmp_path / "drive" / "06_Demo" / "DEMO.md").exists()
