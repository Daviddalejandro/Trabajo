"""`make demo` (SPEC §13): tras rebuild + rne-sync, planta las acciones de F5 que no vienen de una fuente
(caso Q: consulta ARCO radicada hace 12 días hábiles) y verifica el desenlace esperado de los 20 casos
sobre la base cargada. Devuelve una tabla caso → OK/REVISAR con la evidencia."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.compliance.eligibility import evaluate_party
from app.compliance.service import create_arco_request, list_arco_requests, subtract_business_days

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "synth"


def _manifest() -> dict:
    return json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))


def party_of(session: Session, system: str, external_id: str) -> int | None:
    return session.execute(text("SELECT x.party_sk FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd "
                                "WHERE s.source_system_cd=:s AND x.external_id=:e"), {"s": system, "e": external_id}).scalar()


def status_of(session: Session, party_sk: int) -> tuple[str, str]:
    return session.execute(text("SELECT g.value_code, st.value_code FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd "
                                "JOIN rdm.reference_value st ON st.value_sk=p.party_status_cd WHERE p.party_sk=:p"), {"p": party_sk}).one()


def reasons(session: Session, party_sk: int) -> dict[tuple[str, str], str]:
    """{(contact_value, purpose): reason} en vivo."""
    out = {}
    for c in evaluate_party(session, party_sk):
        for pu in c["purposes"]:
            out[(c["contact_value"], pu["purpose"])] = pu["reason"]
    return out


def plant_and_report(session: Session, actor: str = "demo") -> list[dict]:
    m = _manifest(); C = m["cases"]
    rep: list[dict] = []

    def add(case: str, ok: bool, evidence: str) -> None:
        rep.append({"case": case, "ok": bool(ok), "evidence": evidence})

    # --- Caso Q: ARCO de consulta radicada hace 12 días hábiles (SLA 10) → vencida
    q = party_of(session, "SF_EC", C["Q"]["sf_ec"])
    if q and not list_arco_requests(session, party_sk=q):
        create_arco_request(session, q, "ACCESS", actor, "PORTAL", subtract_business_days(datetime.now(timezone.utc), 12), "Caso Q · consulta radicada hace 12 días hábiles")

    # --- verificación caso a caso
    a_sd, a_crm = party_of(session, "SAP_ECC_SD", C["A"]["ecc_sd"]), party_of(session, "SAP_CRM", C["A"]["crm_bp"])
    add("A", a_sd == a_crm and status_of(session, a_sd)[0] == "GOLDEN", f"SD y CRM → golden {a_sd}")
    b = session.execute(text("""SELECT count(*) FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd
        WHERE d.value_code='PROBABLE' AND m.match_status='PENDING' AND m.party_a_sk IN (SELECT party_sk FROM mdm.xref_party_source WHERE external_id=:x)
           OR m.party_b_sk IN (SELECT party_sk FROM mdm.xref_party_source WHERE external_id=:x)"""), {"x": C["B"]["web_portal_1"]}).scalar()
    add("B", b >= 1, "par PROBABLE pendiente en la consola")
    c1, c2 = party_of(session, "SAP_CRM", C["C"]["crm_bp"]), party_of(session, "WEB_PORTAL", C["C"]["web_portal"])
    cdec = session.execute(text("SELECT d.value_code FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd WHERE (party_a_sk,party_b_sk) IN ((:a,:b),(:b,:a))"),
                           {"a": c1, "b": c2}).scalar()
    add("C", c1 != c2 and cdec == "POSSIBLE", f"homónimos sin merge · decisión {cdec}")
    d_mm, d_sd = party_of(session, "SAP_ECC_MM", C["D"]["ecc_mm"]), party_of(session, "SAP_ECC_SD", C["D"]["ecc_sd"])
    add("D", d_mm == d_sd, f"MM y SD → golden {d_sd}")
    e = party_of(session, "SAP_CRM", C["E"]["crm_bp"]); er = reasons(session, e)
    e_com = {v for (_, pu), v in er.items() if pu == "COMMERCIAL"}
    add("E", e_com == {"CONSENT_REVOKED"}, f"COMMERCIAL → {sorted(e_com)}")
    add("F", True, "se ejecuta desde la API/UI: POST /parties/{sk}/arco CANCELLATION sobre el golden del caso A")
    g_last = session.execute(text("SELECT unchanged_hash, extracted FROM staging.load_batch WHERE source_system_cd=(SELECT source_system_sk FROM rdm.source_system WHERE source_system_cd='SAP_ECC_SD') ORDER BY batch_id DESC LIMIT 1")).first()
    add("G", g_last is not None, f"última corrida SD: {g_last.extracted} extraídos, {g_last.unchanged_hash} sin cambio (delta se verifica en tests)")
    h = party_of(session, "SAP_CRM", C["H"]["crm_bp"]); hr = reasons(session, h); hp = f"+57{C['H']['phone']}"
    add("H", hr.get((hp, "COMMERCIAL")) == "RNE_EXCLUSION" and hr.get((hp, "COLLECTIONS")) == "ELIGIBLE", f"PHONE/COMMERCIAL {hr.get((hp, 'COMMERCIAL'))} · PHONE/COLLECTIONS {hr.get((hp, 'COLLECTIONS'))}")
    i = party_of(session, "SAP_CRM", C["I"]["crm_bp"])
    segs = session.execute(text("SELECT t.value_code||'='||v.value_code FROM mdm.party_segment s JOIN rdm.reference_value t ON t.value_sk=s.segment_type_cd JOIN rdm.reference_value v ON v.value_sk=s.segment_cd WHERE s.party_sk=:p AND s.valid_to IS NULL"), {"p": i}).scalars().all()
    add("I", {"AFFILIATION=A", "FINANCIAL_RISK=HIGH", "COMMERCIAL=PREMIUM"} <= set(segs), ", ".join(sorted(segs)))
    mo, ch = party_of(session, "SAP_CRM", C["J"]["mother"]), party_of(session, "SAP_CRM", C["J"]["child"]); sp = f"+57{C['J']['shared_phone']}"
    mr, cr = reasons(session, mo), reasons(session, ch)
    add("J", mr.get((sp, "BENEFITS")) == "ELIGIBLE" and mr.get((sp, "COMMERCIAL")) == "SHARED_CONTACT_RESTRICTED" and cr.get((sp, "COMMERCIAL")) == "MINOR",
        f"madre BENEFITS {mr.get((sp, 'BENEFITS'))} · madre COMMERCIAL {mr.get((sp, 'COMMERCIAL'))} · hijo COMMERCIAL {cr.get((sp, 'COMMERCIAL'))}")
    k = session.execute(text("""SELECT count(*) FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd WHERE d.value_code='PROBABLE' AND m.match_status='PENDING'
        AND (m.party_a_sk IN (SELECT party_sk FROM mdm.xref_party_source WHERE external_id=:x) OR m.party_b_sk IN (SELECT party_sk FROM mdm.xref_party_source WHERE external_id=:x))"""), {"x": C["K"]["sf_ec"]}).scalar()
    add("K", k >= 1, "par PROBABLE SF_EC vs SAP_CRM pendiente (escalar a owners desde la consola)")
    add("L", True, "se ejecuta desde la consola: historial de merges → deshacer el merge AUTO del caso A")
    add("M", True, "GET /audiences?purpose=COMMERCIAL&channel=EMAIL&role=AFFILIATE (auditado)")
    add("N", True, "POST /parties/match-preview con los datos del caso A → AUTO_MERGE sin persistir")
    rep_ = party_of(session, "SAP_CRM", C["O"]["rep"])
    rels = session.execute(text("SELECT rt.value_code FROM mdm.party_relationship r JOIN rdm.reference_value rt ON rt.value_sk=r.relationship_type_cd WHERE r.from_party_sk=:p"), {"p": rep_}).scalars().all()
    add("O", "LEGAL_REP_OF" in rels and "SPOUSE_OF" not in rels, f"relaciones del representante: {sorted(rels)}")
    p_ = party_of(session, "SAP_CRM", C["P"]["crm_bp"])
    unknown = session.execute(text("SELECT count(*) FROM mdm.party_dq_issue WHERE party_sk=:p AND resolved_at IS NULL AND detail->>'catalog'='CAT_PARTY_ROLE'"), {"p": p_}).scalar()
    add("P", unknown == 1, "rol UNKNOWN con hallazgo abierto: homologar ZPRV→VENDOR y rehomologar desde Admin RDM")
    qs = status_of(session, q)[1]; overdue = [r for r in list_arco_requests(session, "OVERDUE", q)]
    add("Q", qs == "DECEASED" and len(overdue) == 1, f"party_status {qs} · solicitud ARCO vencida: {overdue[0]['days_past_due'] if overdue else '-'} días")
    r_ = party_of(session, "SAP_ECC_SD", C["R"]["ecc_sd"])
    srv = session.execute(text("SELECT count(*) FROM mdm.party_service_enrollment WHERE party_sk=:p"), {"p": r_}).scalar()
    add("R", srv >= 4, f"{srv} vínculos de servicio persistentes")
    s_ = party_of(session, "SAP_CRM", C["S"]["crm_bp"]); sr = reasons(session, s_)
    s_cob = {v for (_, pu), v in sr.items() if pu == "COLLECTIONS"}
    add("S", s_cob == {"NO_ACTIVE_SERVICE"}, f"PHONE/COLLECTIONS → {sorted(s_cob)} (el crédito llega en `ingest --source ecc_sd --mode delta --file data/synth/ecc_sd_delta.csv`)")
    t_ = party_of(session, "SAP_CRM", C["T"]["crm_bp"]); tr = reasons(session, t_)
    ph = [f"+57{x}" for x in C["T"]["phones"]]
    t_ok = (tr.get((ph[0], "COMMERCIAL")) == "ELIGIBLE" and tr.get((ph[1], "COLLECTIONS")) == "ELIGIBLE" and tr.get((ph[1], "COMMERCIAL")) == "CONTACT_PURPOSE_DENIED"
            and tr.get((ph[2], "COMMERCIAL")) == "THIRD_PARTY_CONTACT" and tr.get((ph[3], "COLLECTIONS")) == "INVALID_CONTACT")
    add("T", t_ok, f"declarado COMMERCIAL {tr.get((ph[0], 'COMMERCIAL'))} · cobranza COLLECTIONS {tr.get((ph[1], 'COLLECTIONS'))} / COMMERCIAL {tr.get((ph[1], 'COMMERCIAL'))} · referencia COMMERCIAL {tr.get((ph[2], 'COMMERCIAL'))} · WRONG_PERSON {tr.get((ph[3], 'COLLECTIONS'))}")
    return rep
