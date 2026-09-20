"""Política de matching v2 (SPEC §8 · afinable): estados por atributo, evidencia normalizada y cobertura,
grupos de suficiencia, vetos por identificador, política versionada (solo Jefatura), simulación sin
persistir y recálculo de la cola. Corre sobre la base reconstruida por conftest tras F3–F5."""
import json
from pathlib import Path

from sqlalchemy import text

from app.core.db import engine
from app.matching.policy import DEFAULT_POLICIES, decide_pair, validate_policy
from app.matching.rules import RULES_V1
from app.matching.scoring import score_person

MANIFEST = json.loads((Path(__file__).resolve().parents[1] / "data" / "synth" / "manifest.json").read_text(encoding="utf-8"))
CASES = MANIFEST["cases"]
JEFATURA = {"X-Actor": "jefatura.gd", "X-Role": "JEFATURA"}


def q(sql, **p):
    with engine.connect() as conn:
        return conn.execute(text(sql), p)


def party_of(system: str, external_id: str) -> int:
    return q("SELECT x.party_sk FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd "
             "WHERE s.source_system_cd=:s AND x.external_id=:e", s=system, e=external_id).scalar_one()


def match_between(a: int, b: int):
    return q("""SELECT m.match_sk, d.value_code AS decision, m.match_status, m.total_score, m.score_detail, m.decision_basis FROM mdm.party_match m
                JOIN rdm.reference_value d ON d.value_sk=m.decision_cd WHERE m.party_a_sk=LEAST(:a,:b) AND m.party_b_sk=GREATEST(:a,:b)
                ORDER BY m.match_sk DESC""", a=a, b=b).mappings().first()


# ------------------------------------------------------------------ decisión pura (sin base de datos)
def _rows(**states):
    """Filas de score_detail PERSON con los pesos v1 y el estado indicado por atributo (AGREE por defecto, MISSING si None)."""
    weights = {"document": 30, "first_surname": 20, "first_name": 15, "birth_date": 15, "second_surname": 10, "email": 5, "phone": 3, "municipality": 2}
    out = []
    for attr, w in weights.items():
        st = states.get(attr, "AGREE")
        pts = w if st == "AGREE" else (w / 2 if st == "PARTIAL" else 0)
        out.append({"attribute": attr, "value_a": "x" if st != "MISSING" else None, "value_b": "x" if st != "MISSING" else None,
                    "algorithm": "T", "similarity": 1.0, "points": pts, "weight": w, "note": "", "state": st})
    return out


def _policy(**over):
    return validate_policy(DEFAULT_POLICIES["PERSON"] | over, ["document", "first_surname", "first_name", "birth_date", "second_surname", "email", "phone", "municipality"]) | {"version": 0}


def _person(doc: str, contacts: bool = True) -> dict:
    import datetime as dt
    return {"party_type": "PERSON", "docs": {("CC", doc)}, "doc_numbers": {doc}, "first_surname": "Rangel", "sur1_k": "RANGEL", "sur1_soundex": "R524",
            "first_name": "Ana", "first_name_k": "ANA", "birth_date": dt.date(1990, 5, 4), "second_surname": "Mora", "sur2_k": "MORA",
            "emails": {"ana@x.test"} if contacts else set(), "phones": {"+573001234567"} if contacts else set(), "cities": {"11001"}}


def test_document_typo_is_partial_and_vetoed_by_default():
    """Un dígito transpuesto (1026256980 vs 1026259680) no es contradicción plena ni acierto: PARTIAL marcado TYPO (+12 de 30).
    Por defecto sigue vetado (nunca fusiona solo); la política puede levantar ese veto o convertirlo en NO_MATCH."""
    rules = {k: {"weight": w, "params": p} for k, w, _, p in RULES_V1["PERSON"]}
    _, rows = score_person(_person("1026256980"), _person("1026259680"), rules)
    doc = next(r for r in rows if r["attribute"] == "document")
    assert doc["state"] == "PARTIAL" and doc["reason"] == "TYPO" and doc["points"] == 12 and "digitación" in doc["note"]
    d, b = decide_pair(rows, _policy())
    assert d == "PROBABLE" and b["decided_by"] == "group:G4+veto_review:document" and b["typo"] == ["document"] and b["evidence"] == 82
    d, b = decide_pair(rows, _policy(veto_typo=False))
    assert d == "AUTO_MERGE" and b["decided_by"] == "group:G4" and b["vetoed_by"] == []
    d, b = decide_pair(rows, _policy(veto_mode="NO_MATCH"))
    assert d == "NO_MATCH" and b["decided_by"] == "veto:document"
    # dos dígitos distintos ya no es error de digitación: contradice
    _, rows = score_person(_person("1026256980"), _person("1026259681"), rules)
    assert next(r for r in rows if r["attribute"] == "document")["state"] == "DISAGREE"
    _, rows = score_person(_person("1026256980"), _person("1026296580"), rules)
    assert next(r for r in rows if r["attribute"] == "document")["state"] == "DISAGREE"


def test_typos_in_date_email_phone_and_names_score_partial():
    """La pregunta del autor: correo, celular, nombres y fecha no se califican solo exactos. Un solo carácter distinto
    (Damerau-Levenshtein = 1), día y mes intercambiados o un nombre a JW ≥ 0.85 puntúan parcial con su motivo; los
    grupos exigen coincidencia plena, así que un error de digitación nunca fusiona solo por grupo."""
    import datetime as dt
    rules = {k: {"weight": w, "params": p} for k, w, _, p in RULES_V1["PERSON"]}
    a = _person("1026256980")
    b = _person("1026256980") | {"birth_date": dt.date(1990, 4, 5), "emails": {"ana@x.tset"}, "phones": {"+573001234576"}, "first_name": "Ama", "first_name_k": "AMA"}
    _, rows = score_person(a, b, rules)
    got = {r["attribute"]: (r["state"], r["reason"], r["points"]) for r in rows}
    assert got["birth_date"] == ("PARTIAL", "DM_SWAP", 10)
    assert got["email"] == ("PARTIAL", "TYPO", 3) and got["phone"] == ("PARTIAL", "TYPO", 2)
    assert got["first_name"] == ("PARTIAL", "NEAR", 8)
    d, basis = decide_pair(rows, _policy())
    assert d == "AUTO_MERGE" and basis["decided_by"] == "group:G1" and basis["evidence"] == 85   # el documento y el apellido plenos deciden
    # sin documento comparable: los parciales suman evidencia pero no satisfacen G2/G3/G4 → vía de umbrales, nunca AUTO
    a2, b2 = a | {"docs": set(), "doc_numbers": set()}, b | {"docs": set(), "doc_numbers": set()}
    _, rows = score_person(a2, b2, rules)
    d, basis = decide_pair(rows, _policy())
    assert d == "PROBABLE" and basis["decided_by"] == "threshold:evidence" and basis["satisfied_groups"] == [] and 70 <= basis["evidence"] < 85
    # fecha: un dígito distinto y ±1 año siguen siendo parciales con motivo distinto; dos dígitos lejanos contradicen
    for bd, reason in ((dt.date(1990, 5, 14), "TYPO"), (dt.date(1991, 3, 4), "NEAR"), (dt.date(1975, 1, 1), None)):
        _, rows = score_person(a, a | {"birth_date": bd}, rules)
        r = next(x for x in rows if x["attribute"] == "birth_date")
        assert (r["state"], r["reason"]) == (("PARTIAL", reason) if reason else ("DISAGREE", None)), bd


def test_missing_attribute_is_neither_evidence_for_nor_against():
    d, b = decide_pair(_rows(document="MISSING"), _policy())
    assert b["evidence"] == 100 and b["coverage"] == 70 and d == "AUTO_MERGE" and b["decided_by"] == "group:G4"   # correo y teléfono confirmados
    d, b = decide_pair(_rows(document="MISSING", phone="MISSING"), _policy())
    assert d == "PROBABLE" and b["decided_by"] == "group:G2" and "G3" in b["satisfied_groups"] and "G4" not in b["satisfied_groups"]


def test_contradicting_document_blocks_auto_merge_and_mode_is_tunable():
    d, b = decide_pair(_rows(document="DISAGREE"), _policy())
    assert d == "PROBABLE" and b["vetoed_by"] == ["document"] and b["decided_by"].endswith("+veto_review:document")
    d, b = decide_pair(_rows(document="DISAGREE"), _policy(veto_mode="NO_MATCH"))
    assert d == "NO_MATCH" and b["decided_by"] == "veto:document"
    d, b = decide_pair(_rows(document="DISAGREE"), _policy(veto_attributes=[]))
    assert d == "AUTO_MERGE"   # sin veto el documento solo resta puntos


def test_threshold_path_needs_raw_points_and_never_auto_merges_without_group():
    # apellido + nombre + municipio: 37 puntos sobre 37 comparables = evidencia 100, pero por debajo del piso de 50 puntos brutos
    d, b = decide_pair(_rows(document="MISSING", birth_date="MISSING", second_surname="MISSING", email="MISSING", phone="MISSING"), _policy())
    assert d == "NO_MATCH" and b["evidence"] == 100
    # documento parcial (TI→CC) y todo lo demás igual: 85 brutos = AUTO en v1; en v2 sin grupo satisfecho queda PROBABLE
    d, b = decide_pair(_rows(document="PARTIAL"), _policy(groups=[]))
    assert d == "PROBABLE" and b["threshold_decision"] == "PROBABLE" and b["raw_points"] == 85 and b["evidence"] == 85 and not b["vetoed_by"]
    d, b = decide_pair(_rows(document="PARTIAL"), _policy(groups=[], auto_requires_group=False))
    assert d == "AUTO_MERGE" and b["decided_by"] == "threshold:evidence"
    # cobertura por debajo del mínimo (solo documento y primer apellido comparables: 50 %): se decide con puntos brutos
    d, b = decide_pair(_rows(first_name="MISSING", birth_date="MISSING", second_surname="MISSING", email="MISSING", phone="MISSING", municipality="MISSING"), _policy(groups=[]))
    assert b["coverage"] == 50 and b["decided_by"] == "threshold:raw_points" and b["raw_points"] == 50 and d == "POSSIBLE"


def test_validate_policy_rejects_inconsistent_parameters():
    import pytest
    attrs = ["document", "first_surname"]
    with pytest.raises(ValueError):
        validate_policy(DEFAULT_POLICIES["PERSON"] | {"thresholds": {"AUTO_MERGE": 60, "PROBABLE": 70, "POSSIBLE": 50}}, attrs)
    with pytest.raises(ValueError):
        validate_policy(DEFAULT_POLICIES["PERSON"], attrs)   # grupos con atributos desconocidos
    with pytest.raises(ValueError):
        validate_policy({"thresholds": {"AUTO_MERGE": 85, "PROBABLE": 70, "POSSIBLE": 50}, "groups": [{"code": "X", "attributes": ["document"], "decision": "NO_MATCH"}]}, attrs)


# ------------------------------------------------------------------ pares reales del escenario demo
def test_default_policy_seeded_and_exposed(client):
    r = client.get("/api/v1/matching/policy", params={"entity": "PERSON"}).json()
    assert r["active"]["version"] == 1 and [g["code"] for g in r["active"]["params"]["groups"]] == ["G1", "G2", "G3", "G4"]
    assert {a["attribute"] for a in r["attributes"]} == {"document", "first_surname", "first_name", "birth_date", "second_surname", "email", "phone", "municipality"}
    assert r["active"]["params"]["veto_mode"] == "REVIEW" and r["active"]["params"]["min_raw_points"] == 50
    o = client.get("/api/v1/matching/policy", params={"entity": "ORGANIZATION"}).json()
    assert o["active"]["version"] == 1 and o["active"]["params"]["veto_attributes"] == ["nit"]


def test_case_U_missing_document_is_scored_on_available_evidence(client):
    u, dup = party_of("SAP_CRM", CASES["U"]["crm_bp"]), party_of("WEB_PORTAL", CASES["U"]["web_portal_dup"])
    m = match_between(u, dup)
    assert m and m["decision"] == "PROBABLE" and m["match_status"] == "PENDING"
    states = {r["attribute"]: r["state"] for r in m["score_detail"]}
    assert states["document"] == "MISSING" and states["email"] == "DISAGREE" and states["phone"] == "AGREE" and states["birth_date"] == "AGREE"
    b = m["decision_basis"]
    assert b["coverage"] == 70 and 90 <= b["evidence"] < 100 and float(m["total_score"]) == b["evidence"]
    assert b["decided_by"] == "group:G2" and set(b["satisfied_groups"]) == {"G2", "G3"} and b["policy_version"] == 1
    g4 = next(g for g in b["groups"] if g["code"] == "G4")
    assert g4["applies"] and not g4["satisfied"] and g4["failing"] == ["email"]
    detail = client.get(f"/api/v1/matches/{m['match_sk']}").json()
    assert detail["decision_basis"]["decided_by"] == "group:G2"


def test_case_K_different_document_types_are_not_comparable():
    a, b = party_of("SF_EC", CASES["K"]["sf_ec"]), party_of("SAP_CRM", CASES["K"]["crm_bp"])
    if a == b:   # ya fusionado por consenso de owners en F3: la evidencia queda en el par resuelto
        m = q("""SELECT m.score_detail, m.decision_basis FROM mdm.party_match m JOIN mdm.party_merge_history h ON h.match_sk=m.match_sk
                 WHERE h.surviving_party_sk=:p OR h.merged_party_sk=:p ORDER BY m.match_sk DESC""", p=a).mappings().first()
    else:
        m = match_between(a, b)
    doc = next(r for r in m["score_detail"] if r["attribute"] == "document")
    assert doc["state"] == "MISSING" and "no comparables" in doc["note"] and not m["decision_basis"]["vetoed_by"]
    assert m["decision_basis"]["decision"] == "PROBABLE" and m["decision_basis"]["satisfied_groups"] == ["G2"]


def test_case_C_partial_birth_date_satisfies_no_group():
    a, b = party_of("SAP_CRM", CASES["C"]["crm_bp"]), party_of("WEB_PORTAL", CASES["C"]["web_portal"])
    m = match_between(a, b)
    assert m["decision"] == "POSSIBLE" and m["decision_basis"]["decided_by"] == "threshold:evidence" and m["decision_basis"]["satisfied_groups"] == []
    assert {r["attribute"]: r["state"] for r in m["score_detail"]}["birth_date"] == "PARTIAL"


def test_simulate_reports_transitions_without_persisting(client):
    before = q("SELECT count(*), count(*) FILTER (WHERE match_status='PENDING') FROM mdm.party_match").one()
    persons = q("SELECT count(*) FROM mdm.party_match m JOIN mdm.party p ON p.party_sk=m.party_a_sk JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd WHERE t.value_code='PERSON'").scalar_one()
    params = json.loads(json.dumps(DEFAULT_POLICIES["PERSON"]))
    next(g for g in params["groups"] if g["code"] == "G3")["decision"] = "AUTO_MERGE"
    r = client.post("/api/v1/matching/policy/simulate", json={"entity": "PERSON", "params": params, "scope": "all"})
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s["pairs"] == persons and s["pending_to_auto"] >= 1 and "PROBABLE→AUTO_MERGE" in s["transitions"]
    assert any(p["match_sk"] and p["new_decision"] == "AUTO_MERGE" and p["match_status"] == "PENDING" for p in r.json()["pairs"])
    assert "agreement_with_humans" in s
    assert q("SELECT count(*), count(*) FILTER (WHERE match_status='PENDING') FROM mdm.party_match").one() == before
    bad = client.post("/api/v1/matching/policy/simulate", json={"entity": "PERSON", "params": params | {"thresholds": {"AUTO_MERGE": 10, "PROBABLE": 70, "POSSIBLE": 50}}})
    assert bad.status_code == 422


def test_publish_requires_jefatura_then_recalculate_applies_it(client):
    params = json.loads(json.dumps(DEFAULT_POLICIES["PERSON"]))
    next(g for g in params["groups"] if g["code"] == "G3")["decision"] = "AUTO_MERGE"
    assert client.post("/api/v1/matching/policy", json={"entity": "PERSON", "params": params, "note": "prueba"}, headers={"X-Actor": "steward.mdm", "X-Role": "STEWARD"}).status_code == 403
    assert client.post("/api/v1/matching/recalculate", headers={"X-Actor": "steward.mdm", "X-Role": "STEWARD"}).status_code == 403
    r = client.post("/api/v1/matching/policy", json={"entity": "PERSON", "params": params, "note": "G3 fusiona solo (prueba F6)"}, headers=JEFATURA)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    pol = client.get("/api/v1/matching/policy", params={"entity": "PERSON"}).json()
    assert pol["active"]["version"] == 2 and [v["version"] for v in pol["versions"]] == [2, 1] and not pol["versions"][1]["is_active"]
    assert q("SELECT count(*) FROM mdm.party_audit_log WHERE entity='MATCH_POLICY'").scalar_one() >= 2   # inserción v2 + desactivación v1
    u, dup = party_of("SAP_CRM", CASES["U"]["crm_bp"]), party_of("WEB_PORTAL", CASES["U"]["web_portal_dup"])
    m = match_between(u, dup)
    rc = client.post("/api/v1/matching/recalculate", params={"entity": "PERSON"}, headers=JEFATURA)
    assert rc.status_code == 200, rc.text
    out = rc.json()
    assert out["auto_merged"] >= 1 and any(c["match_sk"] == m["match_sk"] and c["to"] == "AUTO_MERGE" for c in out["changes"])
    assert party_of("SAP_CRM", CASES["U"]["crm_bp"]) == party_of("WEB_PORTAL", CASES["U"]["web_portal_dup"])
    h = q("SELECT decided_by, justification FROM mdm.party_merge_history WHERE match_sk=:k", k=m["match_sk"]).one()
    assert h[0] == "engine.v1.p2" and "política v2" in h[1] and "group:G3" in h[1]
    after = match_between(u, dup)
    assert after["match_status"] == "RESOLVED" and after["decision"] == "AUTO_MERGE" and after["decision_basis"]["policy_version"] == 2
    # el caso C no cambia (ningún grupo lo satisface) y sigue pendiente
    c = match_between(party_of("SAP_CRM", CASES["C"]["crm_bp"]), party_of("WEB_PORTAL", CASES["C"]["web_portal"]))
    assert c["decision"] == "POSSIBLE" and c["match_status"] == "PENDING"
    # vuelta a la política inicial como versión 3 (la 2 queda en el historial, nunca se borra)
    r3 = client.post("/api/v1/matching/policy", json={"entity": "PERSON", "params": DEFAULT_POLICIES["PERSON"], "note": "restaura la inicial"}, headers=JEFATURA)
    assert r3.json()["version"] == 3 and q("SELECT count(*) FROM mdm.match_policy").scalar_one() == 4   # 3 PERSON + 1 ORGANIZATION
