"""F4 · Endpoints de apoyo de la consola y la Vista 360 (SPEC §11, §12): historial de merges con
snapshot, previsualización de rehomologación, relaciones con el otro extremo identificado y
vínculos de servicio. Los casos B, K, unmerge y Admin RDM desde la UI se verifican con Playwright
(frontend/e2e/f4.spec.ts, `make test-e2e`)."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.db import engine
from app.main import app

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "data" / "synth" / "manifest.json").read_text(encoding="utf-8"))
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


def test_merges_list_and_detail_with_snapshot(client):
    r = client.get("/api/v1/merges", params={"limit": 5}).json()
    assert r["items"] and {"surviving", "merged", "merge_type", "decided_by"} <= set(r["items"][0])
    reverted = client.get("/api/v1/merges", params={"unmerged": True}).json()["items"]
    assert all(x["unmerged"] for x in reverted)                             # caso L (F3) si la suite completa corrió antes
    current = client.get("/api/v1/merges", params={"unmerged": False}).json()["items"]
    assert current and not any(x["unmerged"] for x in current)
    d = client.get(f"/api/v1/merges/{r['items'][0]['merge_sk']}").json()
    assert set(d["snapshot_counts"]) == {"surviving", "merged"} and d["snapshot_counts"]["merged"]["party"] == 1
    assert d["pre_merge_snapshot"]["merged"]["tables"]["party"]
    assert any(a["action"] == "MERGE" for a in d["audit"])
    assert client.get("/api/v1/merges/999999").status_code == 404


def test_merges_filter_by_party(client):
    sd = party_of("SAP_ECC_SD", CASES["A"]["ecc_sd"])
    items = client.get("/api/v1/merges", params={"party_sk": sd}).json()["items"]
    assert items and all(sd in (x["surviving_party_sk"], x["merged_party_sk"]) for x in items)


def test_rehomologate_preview_counts_unknown_and_resolvable(client):
    p = client.get("/api/v1/rdm/rehomologate/preview").json()
    assert p["unknown"] >= p["resolvable"] >= 0 and isinstance(p["items"], list)
    open_unknown = q("SELECT count(*) FROM mdm.party_dq_issue WHERE resolved_at IS NULL AND detail ? 'target_table'").scalar_one()
    assert p["unknown"] == open_unknown
    role = client.get("/api/v1/rdm/rehomologate/preview", params={"catalog": "CAT_PARTY_ROLE"}).json()
    open_role = q("SELECT count(*) FROM mdm.party_dq_issue WHERE resolved_at IS NULL AND detail->>'catalog'='CAT_PARTY_ROLE'").scalar_one()
    assert role["unknown"] == open_role and all(i["catalog"] == "CAT_PARTY_ROLE" for i in role["items"])


def test_relationships_endpoint_identifies_other_end(client):
    rep = party_of("SAP_CRM", CASES["O"]["rep"])
    rels = client.get(f"/api/v1/parties/{rep}/relationships").json()
    out = [r for r in rels if r["relationship_type"] == "LEGAL_REP_OF"]
    assert out and out[0]["direction"] == "OUT" and out[0]["other_party_type"] == "ORGANIZATION" and out[0]["other_display_name"]
    org = party_of("SAP_CRM", CASES["O"]["org1"])
    inbound = client.get(f"/api/v1/parties/{org}/relationships", params={"direction": "in"}).json()
    assert all(r["direction"] == "IN" for r in inbound) and any(r["other_party_sk"] == rep for r in inbound)


def test_services_endpoint_with_status_filter(client):
    sd = party_of("SAP_ECC_SD", CASES["R"]["ecc_sd"])
    allv = client.get(f"/api/v1/parties/{sd}/services").json()
    closed = client.get(f"/api/v1/parties/{sd}/services", params={"status": "CLOSED"}).json()
    assert {s["service"] for s in allv} >= {"CREDITO_SOCIAL", "SALUD_EPS"} and all(s["service_name"] for s in allv)
    assert closed and all(s["status"] == "CLOSED" for s in closed) and len(closed) < len(allv)


def test_golden_relationships_carry_other_display_name(client):
    mother = party_of("SAP_CRM", CASES["O"]["mother"])
    g = client.get(f"/api/v1/parties/{mother}/golden").json()
    rel = [r for r in g["roles_relationships"]["relationships"] if r["relationship_type"] == "PARENT_OF"]
    assert rel and rel[0]["other_display_name"] and rel[0]["other_party_type"] == "PERSON"


def test_golden_summary_answers_contactability_and_pending_matches(client):
    """Resumen ejecutivo de la Vista 360: elegibilidad por finalidad, servicios por UES, hallazgos abiertos,
    pares pendientes y condiciones derivadas (Ley 2300/2023 arts. 3 y 5)."""
    p = party_of("SAP_CRM", CASES["C"]["crm_bp"])            # caso C: par POSSIBLE que queda pendiente (nadie lo decide en F3)
    g = client.get(f"/api/v1/parties/{p}/golden").json()
    sm = g["summary"]
    assert {"eligibility", "services", "open_dq_issues", "pending_matches", "sources", "is_minor", "is_deceased"} <= set(sm)
    assert {e["purpose"] for e in sm["eligibility"]} >= {"COMMERCIAL", "COLLECTIONS", "BENEFITS"}
    assert all({"is_eligible", "eligible_contacts", "contacts", "reasons"} <= set(e) for e in sm["eligibility"])
    pend = g["golden_record"]["pending_matches"]
    assert sm["pending_matches"] == len(pend) >= 1
    other = party_of("WEB_PORTAL", CASES["C"]["web_portal"])
    k = next(m for m in pend if m["other_party_sk"] == other)
    assert k["decision"] == "POSSIBLE" and k["match_status"] in ("PENDING", "IN_REVIEW") and k["other_display_name"] and k["rule_version"] >= 1
    assert 50 <= float(k["total_score"]) < 70


def test_golden_minor_flag_and_group_members_case_J(client):
    child = party_of("SAP_CRM", CASES["J"]["child"]); mother = party_of("SAP_CRM", CASES["J"]["mother"])
    g = client.get(f"/api/v1/parties/{child}/golden").json()
    assert g["summary"]["is_minor"] is True and g["summary"]["is_deceased"] is False
    groups = g["roles_relationships"]["groups"]
    assert groups and any(m["party_sk"] == mother for grp in groups for m in (grp["members"] or []))
    m = next(m for grp in groups for m in (grp["members"] or []) if m["party_sk"] == mother)
    assert m["display_name"] and m["member_role"] and "is_anchor" in m
    # columnas nuevas por capa (validez técnica del contacto, rol del vínculo, geocodificación, vigencias)
    assert all({"is_verified", "valid_from", "valid_to"} <= set(c) for c in g["contactability"]["contacts"])
    assert all({"geocoding_status", "captured_at"} <= set(a) for a in g["contactability"]["addresses"])
    assert all("role" in s for s in g["roles_relationships"]["services"])
    assert all({"valid_from", "valid_to"} <= set(n) for n in g["identity"]["names"])


def test_case_U_showcase_party_has_every_layer_populated(client):
    """Caso U · vitrina 360: una sola persona con las ocho capas pobladas, incluidas las relaciones
    persona↔organización y persona↔persona que la Consola de Stewardship muestra en Evidencia A/B."""
    u = party_of("SAP_CRM", CASES["U"]["crm_bp"])
    g = client.get(f"/api/v1/parties/{u}/golden").json()
    assert {s["source_system_cd"] for s in g["sources"]} == {"SF_EC", "SAP_CRM", "SAP_ECC_SD", "SAP_ECC_MM", "WEB_PORTAL"}
    rr = g["roles_relationships"]
    assert {r["role"] for r in rr["roles"]} == {"EMPLOYEE", "AFFILIATE", "VENDOR", "DIGITAL_USER"}
    assert all(r["sub_role"] for r in rr["roles"])
    assert {(s["segment_type"], s["segment"]) for s in rr["segments"] if not s["valid_to"]} == \
           {("AFFILIATION", "A"), ("FINANCIAL_RISK", "LOW"), ("COMMERCIAL", "PREMIUM")}
    assert {s["business_unit"] for s in rr["services"]} == {"CREDITO", "SALUD", "SUBSIDIO"}
    rels = {(r["relationship_type"], r["other_party_type"]) for r in rr["relationships"]}
    assert {("EMPLOYEE_OF", "ORGANIZATION"), ("LEGAL_REP_OF", "ORGANIZATION"), ("SHAREHOLDER_OF", "ORGANIZATION")} <= rels
    assert {("SPOUSE_OF", "PERSON"), ("PARENT_OF", "PERSON"), ("CHILD_OF", "PERSON"), ("BENEFICIARY_OF", "PERSON")} <= rels
    assert all(r["other_display_name"] for r in rr["relationships"])        # el otro extremo siempre identificado
    assert rr["groups"] and g["consents"]["consents"] and g["golden_record"]["survivorship"]
    assert len([m for m in g["golden_record"]["merges"] if not m["unmerged"]]) >= 4
    assert {c["usage_role"] for c in g["contactability"]["contacts"]} >= {"OWNER", "REFERENCE"}
    assert g["summary"]["sources"] == 5 and g["summary"]["pending_matches"] >= 1   # visible en la cola de stewardship


def test_search_normalizes_accents_and_punctuation(client):
    """El nombre se guarda normalizado: el texto buscado se normaliza igual (SPEC §11)."""
    u = party_of("SAP_CRM", CASES["U"]["crm_bp"])
    for term in ["Mariana Lucía Restrepo", "mariana lucia restrepo", "Restrepo, Vanegas"]:
        items = client.get("/api/v1/parties", params={"q": term, "status": "GOLDEN", "limit": 50}).json()["items"]
        assert u in [i["party_sk"] for i in items], term
    by_doc = client.get("/api/v1/parties", params={"q": CASES["U"]["doc"]}).json()["items"]
    assert u in [i["party_sk"] for i in by_doc]                             # documento exacto sigue funcionando
    by_mail = client.get("/api/v1/parties", params={"q": CASES["U"]["email"]}).json()["items"]
    assert u in [i["party_sk"] for i in by_mail]                            # correo exacto sigue funcionando


def test_frontend_build_exists_or_skipped():
    dist = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"
    if not dist.exists():
        pytest.skip("frontend/dist no construido (make test-frontend)")
    assert "root" in dist.read_text(encoding="utf-8")
