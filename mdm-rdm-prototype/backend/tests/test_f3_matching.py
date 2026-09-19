"""F3 · criterios de aceptación (SPEC §14): casos A, C, D, G, L, N; score_detail desglosado;
XREF evita re-matching; survivorship registra fuente ganadora por campo; teléfono compartido
no puntúa. Anticipos de F4: decisión del steward (B) y tareas por owner (K)."""
import json
from pathlib import Path

from sqlalchemy import text

from app.core.db import engine

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "data" / "synth" / "manifest.json").read_text(encoding="utf-8"))
CASES = MANIFEST["cases"]


def q(sql, **p):
    with engine.connect() as conn:
        return conn.execute(text(sql), p)


def party_of(system: str, external_id: str) -> int:
    return q("SELECT x.party_sk FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd "
             "WHERE s.source_system_cd=:s AND x.external_id=:e", s=system, e=external_id).scalar_one()


def status_of(party_sk: int) -> str:
    return q("SELECT g.value_code FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd WHERE p.party_sk=:p", p=party_sk).scalar_one()


def match_between(a: int, b: int):
    return q("""SELECT m.match_sk, m.total_score, d.value_code, m.match_status, m.score_detail FROM mdm.party_match m
                JOIN rdm.reference_value d ON d.value_sk=m.decision_cd WHERE m.party_a_sk=LEAST(:a,:b) AND m.party_b_sk=GREATEST(:a,:b)
                ORDER BY m.match_sk DESC""", a=a, b=b).first()


# ------------------------------------------------------------------ inventario del motor
def test_match_rules_seeded_with_spec_weights():
    rows = {(r[0], r[1]): float(r[2]) for r in q("SELECT t.value_code, r.attribute, r.weight FROM mdm.match_rule r JOIN rdm.reference_value t ON t.value_sk=r.entity_type_cd WHERE r.version=1").all()}
    assert rows[("PERSON", "document")] == 30 and rows[("PERSON", "first_surname")] == 20 and rows[("PERSON", "phone")] == 3
    assert rows[("ORGANIZATION", "nit")] == 50 and rows[("ORGANIZATION", "legal_name")] == 25
    assert sum(v for (e, _), v in rows.items() if e == "PERSON") == 100 and sum(v for (e, _), v in rows.items() if e == "ORGANIZATION") == 100


def test_no_candidates_left_except_forced_review():
    st = dict(q("SELECT g.value_code, count(*) FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd GROUP BY 1").all())
    assert st["GOLDEN"] > 800 and st["MERGED"] > 500
    forced = q("SELECT count(*) FROM mdm.party_dq_issue WHERE staging_ref='matching'").scalar_one()
    assert st.get("CANDIDATE", 0) == forced   # todo CANDIDATE restante tiene su hallazgo UNIQUENESS (regla dura 3.16)
    assert q("SELECT count(*) FROM mdm.party_bucket").scalar_one() > 0 and q("SELECT count(*) FROM mdm.bucket_candidate").scalar_one() > 0


# ------------------------------------------------------------------ caso A · auto-merge + survivorship
def test_case_A_auto_merge_and_survivorship():
    sd, crm = party_of("SAP_ECC_SD", CASES["A"]["ecc_sd"]), party_of("SAP_CRM", CASES["A"]["crm_bp"])
    assert sd == crm and status_of(sd) == "GOLDEN"
    mh = q("""SELECT m.merge_sk, mt.value_code, m.decided_by, m.pre_merge_snapshot, m.match_sk FROM mdm.party_merge_history m
              JOIN rdm.reference_value mt ON mt.value_sk=m.merge_type_cd WHERE m.surviving_party_sk=:p AND NOT m.unmerged""", p=sd).first()
    assert mh[1] == "AUTO" and mh[2].startswith("engine.v1.p") and {"surviving", "merged"} <= set(mh[3])   # pesos v1, política N
    m = q("SELECT total_score, score_detail, match_status FROM mdm.party_match WHERE match_sk=:k", k=mh[4]).one()
    assert float(m[0]) >= 85 and m[2] == "RESOLVED"
    attrs = {d["attribute"]: d for d in m[1]}
    assert attrs["document"]["points"] == 30 and attrs["first_surname"]["points"] == 20 and "similarity" in attrs["first_name"]
    # survivorship: nombre y documento desde SAP_CRM (prioridad SAP_CRM > SAP_ECC_SD); evidencia por campo
    sv = {r[0]: (r[1], r[2]) for r in q("""SELECT sv.field_name, st.value_code, s.source_system_cd FROM mdm.party_survivorship sv
        JOIN rdm.reference_value st ON st.value_sk=sv.strategy_cd LEFT JOIN rdm.source_system s ON s.source_system_sk=sv.winning_source_cd WHERE sv.party_sk=:p""", p=sd).all()}
    assert sv["first_name"] == ("SOURCE_PRIORITY", "SAP_CRM") and sv["document"] == ("SOURCE_PRIORITY", "SAP_CRM") and sv["birth_date"][1] == "SAP_CRM"
    assert sv["email"][0] == "MOST_RECENT" and sv["roles"][0] == "MOST_COMPLETE"
    first = q("SELECT first_name FROM mdm.party_person WHERE party_sk=:p", p=sd).scalar_one()
    raw = q("SELECT payload->>'NAME_FIRST' FROM staging.stg_crm_bp_raw WHERE external_id=:e", e=CASES["A"]["crm_bp"]).scalar_one()
    assert first == raw.title()   # la variante tipográfica de SD no sobrevive
    assert q("SELECT golden_version FROM mdm.party WHERE party_sk=:p", p=sd).scalar_one() >= 2
    # el absorbido conserva su XREF apuntando al sobreviviente y queda MERGED
    merged_sk = q("SELECT merged_party_sk FROM mdm.party_merge_history WHERE merge_sk=:k", k=mh[0]).scalar_one()
    assert status_of(merged_sk) == "MERGED"


def test_merge_audit_grouped_by_merge_sk():
    sd = party_of("SAP_ECC_SD", CASES["A"]["ecc_sd"])
    merge_sk = q("SELECT merge_sk FROM mdm.party_merge_history WHERE surviving_party_sk=:p AND NOT unmerged", p=sd).scalar_one()
    rows = q("""SELECT ac.value_code, count(*) FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd
                WHERE a.merge_sk=:k GROUP BY 1""", k=merge_sk).all()
    assert dict(rows).get("MERGE", 0) >= 5


# ------------------------------------------------------------------ caso C · posible
def test_case_C_possible_recorded_without_action():
    a, b = party_of("SAP_CRM", CASES["C"]["crm_bp"]), party_of("WEB_PORTAL", CASES["C"]["web_portal"])
    assert a != b and status_of(a) == "GOLDEN" and status_of(b) == "GOLDEN"
    m = match_between(a, b)
    assert m is not None and 50 <= float(m[1]) < 70 and m[2] == "POSSIBLE"
    assert q("SELECT count(*) FROM mdm.party_merge_history WHERE :a IN (surviving_party_sk, merged_party_sk) AND :b IN (surviving_party_sk, merged_party_sk)", a=a, b=b).scalar_one() == 0


# ------------------------------------------------------------------ caso D · organización duplicada
def test_case_D_org_auto_merge():
    mm, sd = party_of("SAP_ECC_MM", CASES["D"]["ecc_mm"]), party_of("SAP_ECC_SD", CASES["D"]["ecc_sd"])
    assert mm == sd and status_of(sd) == "GOLDEN"
    m = q("""SELECT m.total_score, m.score_detail FROM mdm.party_match m JOIN mdm.party_merge_history h ON h.match_sk=m.match_sk
             WHERE h.surviving_party_sk=:p AND NOT h.unmerged""", p=sd).first()
    assert float(m[0]) >= 85
    attrs = {d["attribute"]: d for d in m[1]}
    assert attrs["nit"]["points"] == 50 and attrs["legal_name"]["points"] == 25
    assert q("SELECT legal_name FROM mdm.party_org WHERE party_sk=:p", p=sd).scalar_one() in ("LA ESPIGA", "La Espiga S.A.S.")
    assert q("SELECT count(*) FROM mdm.party_identifier WHERE party_sk=:p", p=sd).scalar_one() >= 1


# ------------------------------------------------------------------ caso G · caché XREF
def test_case_G_second_run_no_matching(client):
    r = client.post("/api/v1/pipeline/ecc_sd/run", params={"mode": "delta"}, headers={"X-Actor": "pytest"}).json()
    assert r["unchanged_hash"] == MANIFEST["counts"]["ecc_sd"] - 1 and r["loaded"] == 0 and r["matched"] == 0 and r["auto_merged"] == 0
    r2 = client.post("/api/v1/matching/run", headers={"X-Actor": "pytest"}).json()
    assert r2["auto_merged"] == 0 and r2["promoted"] == 0


# ------------------------------------------------------------------ teléfono compartido no puntúa (caso J)
def test_shared_phone_does_not_score():
    mother, child = party_of("SAP_CRM", CASES["J"]["mother"]), party_of("SAP_CRM", CASES["J"]["child"])
    assert mother != child
    m = match_between(mother, child)
    if m is not None:
        attrs = {d["attribute"]: d for d in m[4]}
        assert attrs["phone"]["points"] == 0


# ------------------------------------------------------------------ caso N · match-preview
def test_case_N_match_preview_does_not_persist(client):
    sd = party_of("SAP_ECC_SD", CASES["A"]["ecc_sd"])
    raw = q("SELECT payload FROM staging.stg_crm_bp_raw WHERE external_id=:e", e=CASES["A"]["crm_bp"]).scalar_one()
    before = q("SELECT count(*) FROM mdm.party_match").scalar_one(), q("SELECT count(*) FROM mdm.party").scalar_one()
    body = {"party_type": "PERSON", "first_name": raw["NAME_FIRST"], "first_surname": raw["NAME_LAST"], "second_surname": raw["NAME_LST2"],
            "birth_date": f"{raw['BIRTHDT'][:4]}-{raw['BIRTHDT'][4:6]}-{raw['BIRTHDT'][6:]}",
            "identifiers": [{"id_type": "CC", "id_number": raw["IDNUMBER"]}], "emails": [raw["SMTP_ADDR"]], "divipola": raw["CITY1"]}
    r = client.post("/api/v1/parties/match-preview", json=body)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["persisted"] is False and out["candidates"][0]["party_sk"] == sd and out["candidates"][0]["score"] >= 85
    assert out["candidates"][0]["decision"] == "AUTO_MERGE" and any(d["attribute"] == "document" for d in out["candidates"][0]["detail"])
    assert (q("SELECT count(*) FROM mdm.party_match").scalar_one(), q("SELECT count(*) FROM mdm.party").scalar_one()) == before


# ------------------------------------------------------------------ cola PROBABLE (B, K) y decisiones
def test_probable_queue_contains_B_and_K(client):
    items = client.get("/api/v1/matches", params={"decision": "PROBABLE", "status": "PENDING", "limit": 100}).json()["items"]
    pairs = {frozenset((i["party_a_sk"], i["party_b_sk"])) for i in items}
    b = frozenset((party_of("WEB_PORTAL", CASES["B"]["web_portal_1"]), party_of("WEB_PORTAL", CASES["B"]["web_portal_2"])))
    k = frozenset((party_of("SF_EC", CASES["K"]["sf_ec"]), party_of("SAP_CRM", CASES["K"]["crm_bp"])))
    assert b in pairs and k in pairs
    item = next(i for i in items if frozenset((i["party_a_sk"], i["party_b_sk"])) == k)
    detail = client.get(f"/api/v1/matches/{item['match_sk']}").json()
    assert {s["source_system_cd"] for s in detail["sources"]} == {"SF_EC", "SAP_CRM"} and len(detail["score_detail"]) == 8 and detail["rules"]


def test_decision_requires_justification(client):
    item = client.get("/api/v1/matches", params={"decision": "PROBABLE", "status": "PENDING", "limit": 1}).json()["items"][0]
    assert client.post(f"/api/v1/matches/{item['match_sk']}/decision", json={"action": "MERGE", "justification": ""}).status_code == 422


def test_case_B_single_source_steward_merge(client):
    a, b = party_of("WEB_PORTAL", CASES["B"]["web_portal_1"]), party_of("WEB_PORTAL", CASES["B"]["web_portal_2"])
    m = match_between(a, b)
    r = client.post(f"/api/v1/matches/{m[0]}/decision", json={"action": "MERGE", "justification": "Mismo usuario re-registrado: nombre, fecha y correo coinciden"},
                    headers={"X-Actor": "steward.portal"})
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "MERGED" and r.json()["merge_type"] == "STEWARD"
    assert party_of("WEB_PORTAL", CASES["B"]["web_portal_1"]) == party_of("WEB_PORTAL", CASES["B"]["web_portal_2"])
    assert q("SELECT match_status FROM mdm.party_match WHERE match_sk=:k", k=m[0]).scalar_one() == "RESOLVED"
    audit = q("""SELECT count(*) FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd
                 WHERE a.entity='PARTY_MATCH' AND a.entity_sk=:k AND ac.value_code='REVIEW_DECISION'""", k=m[0]).scalar_one()
    assert audit == 1


def test_case_K_owner_consensus_workflow(client):
    a, b = party_of("SF_EC", CASES["K"]["sf_ec"]), party_of("SAP_CRM", CASES["K"]["crm_bp"])
    m = match_between(a, b)
    r = client.post(f"/api/v1/matches/{m[0]}/decision", json={"action": "MERGE", "justification": "Nombres y fecha coinciden; pasaporte vs cédula"},
                    headers={"X-Actor": "steward.mdm"})
    assert r.status_code == 200 and r.json()["result"] == "IN_REVIEW" and set(r.json()["sources"]) == {"SF_EC", "SAP_CRM"}
    tasks = client.get("/api/v1/review-tasks", params={"status": "RECEIVED"}).json()
    mine = [t for t in tasks if t["match_sk"] == m[0]]
    assert len(mine) == 2 and {t["assignee"] for t in mine} == {"steward.sfec", "steward.crm"} and all(t["due_at"] for t in mine)
    r1 = client.post(f"/api/v1/review-tasks/{mine[0]['task_sk']}/decision", json={"decision": "MERGE", "justification": "Empleado verificado en nómina"}, headers={"X-Actor": mine[0]["assignee"]}).json()
    assert r1["result"] == "PENDING_OTHER_OWNERS"
    r2 = client.post(f"/api/v1/review-tasks/{mine[1]['task_sk']}/decision", json={"decision": "MERGE", "justification": "Afiliado confirmado por documento alterno"}, headers={"X-Actor": mine[1]["assignee"]}).json()
    assert r2["result"] == "MERGED" and r2["merge_type"] == "OWNER_CONSENSUS"
    assert party_of("SF_EC", CASES["K"]["sf_ec"]) == party_of("SAP_CRM", CASES["K"]["crm_bp"])
    assert q("SELECT count(*) FROM mdm.match_review_task WHERE match_sk=:k AND decided_at IS NULL", k=m[0]).scalar_one() == 0


# ------------------------------------------------------------------ caso L · unmerge
def test_case_L_unmerge_restores_both_parties(client):
    sd = party_of("SAP_ECC_SD", CASES["A"]["ecc_sd"])
    mh = q("SELECT merge_sk, merged_party_sk FROM mdm.party_merge_history WHERE surviving_party_sk=:p AND NOT unmerged", p=sd).one()
    merge_sk, merged = mh
    before_links = q("SELECT count(*) FROM mdm.party_contact_point WHERE party_sk=:p", p=sd).scalar_one()
    r = client.post(f"/api/v1/parties/{sd}/unmerge", json={"merge_sk": merge_sk, "reason": "Homónimos con el mismo documento por error de captura en CRM"},
                    headers={"X-Actor": "steward.mdm"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["restored_rows"] > 0 and out["merged_party_status"] == "CANDIDATE"   # comparte documento con un golden (regla dura 3.16)
    assert party_of("SAP_CRM", CASES["A"]["crm_bp"]) == merged and party_of("SAP_ECC_SD", CASES["A"]["ecc_sd"]) == sd
    assert status_of(sd) == "GOLDEN" and status_of(merged) == "CANDIDATE"
    # el absorbido recupera sus filas hijas; el sobreviviente no conserva más de las que tenía (las que chocaban por unicidad nunca se movieron)
    assert q("SELECT count(*) FROM mdm.party_contact_point WHERE party_sk=:p", p=merged).scalar_one() > 0
    assert q("SELECT count(*) FROM mdm.party_contact_point WHERE party_sk=:p", p=sd).scalar_one() <= before_links
    assert q("SELECT unmerged, unmerged_by, unmerge_reason IS NOT NULL FROM mdm.party_merge_history WHERE merge_sk=:k", k=merge_sk).one() == (True, "steward.mdm", True)
    assert q("SELECT d.value_code, m.match_status FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd JOIN mdm.party_merge_history h ON h.match_sk=m.match_sk WHERE h.merge_sk=:k", k=merge_sk).one() == ("NO_MATCH", "RESOLVED")
    assert q("SELECT count(*) FROM mdm.party_dq_issue WHERE party_sk=:p AND staging_ref='unmerge'", p=merged).scalar_one() == 1
    acts = dict(q("SELECT ac.value_code, count(*) FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd WHERE a.merge_sk=:k GROUP BY 1", k=merge_sk).all())
    assert acts.get("UNMERGE", 0) > 0 and acts.get("MERGE", 0) > 0
    # survivorship re-ejecutado en ambos; el nombre del golden SD vuelve a la variante de SD
    assert q("SELECT count(*) FROM mdm.party_survivorship WHERE party_sk IN (:a, :b)", a=sd, b=merged).scalar_one() > 0
    # una nueva corrida no re-fusiona: la decisión humana NO_MATCH es vinculante
    r2 = client.post("/api/v1/matching/run", headers={"X-Actor": "pytest"}).json()
    assert r2["auto_merged"] == 0 and status_of(merged) == "CANDIDATE"
    assert client.post(f"/api/v1/parties/{sd}/unmerge", json={"merge_sk": merge_sk, "reason": "repetir no debe funcionar"}).status_code == 409
