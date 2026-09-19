"""Vitrina S1–S5 (cargas DELTA sobre la base de la suite), carga transaccional TX por API, bitácora de lotes,
modelo relacional desde el catálogo y buckets de bloqueo (SPEC §7, §8.1)."""
from sqlalchemy import text

from app.core.db import SessionLocal, engine


def q(sql, **p):
    with engine.connect() as conn:
        return conn.execute(text(sql), p)


def test_showcase_cases_s1_to_s7():
    from app.synth.showcase import CASES, load, report

    with SessionLocal() as session:
        m, batches = load(session, "pytest-showcase")
        rows = report(session, m)
        session.commit()
    assert {b["mode"] for b in batches} == {"DELTA"} and sum(b["extracted"] for b in batches) == sum(m["counts"].values())
    bad = [(r["case"], r["evidence"]) for r in rows if not r["ok"]]
    assert not bad, bad
    assert [r["case"] for r in rows] == list(CASES)
    # S1: par PROBABLE con documento «posible error de digitación» y veto; S3: POSSIBLE con documento contradictorio
    by = {r["case"]: r for r in rows}
    assert "veto_review" in by["S1"]["evidence"] and "DISAGREE" in by["S3"]["evidence"] and "3 identificadores" in by["S4"]["evidence"]
    # S6: todos los campos con un error de digitación → comparado y en zona gris con parciales; S7: sin bucket común → sin par
    assert "document=PARTIAL/TYPO" in by["S6"]["evidence"] and "birth_date=PARTIAL/DM_SWAP" in by["S6"]["evidence"] and "POSSIBLE" in by["S6"]["evidence"]
    assert "sin par" in by["S7"]["evidence"] and by["S7"]["party"]


def test_transactional_record_goes_through_the_seven_stages(client):
    ex = client.get("/api/v1/pipeline/web_portal/example").json()
    payload = dict(ex["payload"]); payload["email"] = "tx." + payload["email"]; payload["num_doc"] = ""; payload["tipo_doc"] = ""
    r = client.post("/api/v1/pipeline/web_portal/record", json={"external_id": "uTX0001", "payload": payload}, headers={"X-Actor": "pytest-tx"}).json()
    assert r["mode"] == "TX" and r["extracted"] == 1 and r["loaded"] == 1 and r["outcome"]["party_sk"]
    o = r["outcome"]
    assert o["xref_hit"] is False and (o["pending_matches"] or o["merged_into"] or o["golden_status"] == "GOLDEN")
    assert q("SELECT mode, detail->>'path' FROM staging.load_batch WHERE batch_id=:b", b=r["batch_id"]).one() == ("TX", "transaccional (API)")
    # el mismo ID externo otra vez = cambio: XREF, sin party nuevo
    payload["nombres"] = payload["nombres"] + " Segundo"
    r2 = client.post("/api/v1/pipeline/web_portal/record", json={"external_id": "uTX0001", "payload": payload}, headers={"X-Actor": "pytest-tx"}).json()
    assert r2["xref_hits"] == 1 and r2["outcome"]["party_sk"] == o["party_sk"]
    # y sin cambios = idempotente por hash
    r3 = client.post("/api/v1/pipeline/web_portal/record", json={"external_id": "uTX0001", "payload": payload}, headers={"X-Actor": "pytest-tx"}).json()
    assert r3["unchanged_hash"] == 1 and r3["loaded"] == 0
    assert client.get("/api/v1/pipeline/batches", params={"limit": 3}).json()[0]["mode"] == "TX"
    assert client.post("/api/v1/pipeline/nope/record", json={"external_id": "x", "payload": {}}).status_code == 404


def test_erd_and_buckets_endpoints(client):
    e = client.get("/api/v1/model/erd").json()
    names = {t["name"] for t in e["tables"] if t["schema"] == "mdm"}
    assert len(names) == 30 and {"party", "party_match", "match_policy", "party_bucket"} <= names
    party = next(t for t in e["tables"] if t["name"] == "party")
    assert party["layer"] == "core" and party["rows"] > 0 and any(c["pk"] for c in party["columns"])
    assert any(f["from"] == "mdm.party_person" and f["to"] == "mdm.party" for f in e["fks"]) and any(f["to"].startswith("rdm.") for f in e["fks"])
    b = client.get("/api/v1/matching/buckets").json()
    assert b["totals"]["buckets"] > 0 and {r["strategy"] for r in b["per_strategy"]} >= {"DOC_HASH", "EMAIL_HASH", "SURNAME_SOUNDEX", "NIT_HASH"}
    assert b["top"][0]["members"] >= 2 and all(r["max_size"] >= 2 for r in b["per_strategy"])
    sk = q("SELECT p.party_sk FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd JOIN mdm.party_person pp ON pp.party_sk=p.party_sk WHERE g.value_code='GOLDEN' ORDER BY 1 LIMIT 1").scalar_one()
    pb = client.get(f"/api/v1/matching/buckets/party/{sk}").json()
    assert pb["party_type"] == "PERSON" and {k["strategy"] for k in pb["keys"]} >= {"DOC_HASH", "SURNAME_SOUNDEX"} and pb["universe"] > 0
    assert client.get("/api/v1/matching/buckets/party/999999999").status_code == 404
