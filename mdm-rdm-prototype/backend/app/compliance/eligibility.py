"""Elegibilidad de contacto (SPEC §10.3): se computa por (party_contact_sk, purpose_cd) en el orden
de precedencia 1–12; el primer criterio que falla fija reason_cd. Se persiste en
PARTY_CONTACT_ELIGIBILITY_CACHE y se recalcula ante cualquier cambio de estado, consentimiento,
preferencia, confirmación, vínculo de servicio, RNE, merge o unmerge.

Base legal: Ley 2300/2023 arts. 3 y 5; Res. CRC 7356/2024; Ley 1581/2012 arts. 4 lit. b y d, 7;
Decreto 1377/2013 art. 12. Complemento técnico: DAMA-DMBOK2 cap. 11 (datos maestros de Party),
ISO/IEC 27001:2022 A.5.34 (privacidad y protección de PII)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

ADULT_AGE = 18


def _lookup(session: Session, catalog: str) -> dict[str, int]:
    return dict(session.execute(text("SELECT value_code, value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code=:c AND value_sk > 0"), {"c": catalog}).all())


def purposes_with_attrs(session: Session) -> list[dict]:
    rows = session.execute(text("""
        SELECT l.value_sk, l.value_code,
               COALESCE((SELECT jsonb_object_agg(f.field_code, f.field_value) FROM rdm.reference_field_value f WHERE f.value_sk=l.value_sk), '{}'::jsonb) AS attrs
        FROM rdm.vw_rdm_lookup l WHERE l.catalog_code='CAT_CONTACT_PURPOSE' AND l.value_sk > 0 AND l.is_active ORDER BY l.value_sk""")).mappings().all()
    return [{"sk": r["value_sk"], "code": r["value_code"], "rne_applies": str(r["attrs"].get("rne_applies", "false")).lower() == "true",
             "required_consent": r["attrs"].get("required_consent_type")} for r in rows]


def age_at(birth: date | None, today: date | None = None) -> int | None:
    if birth is None:
        return None
    today = today or date.today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def is_minor(birth: date | None) -> bool:
    a = age_at(birth)
    return a is not None and a < ADULT_AGE


def party_context(session: Session, party_sk: int) -> dict:
    core = session.execute(text("""
        SELECT p.party_sk, st.value_code AS party_status, g.value_code AS golden_status, t.value_code AS party_type, pp.birth_date
        FROM mdm.party p JOIN rdm.reference_value st ON st.value_sk=p.party_status_cd JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd
        JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd LEFT JOIN mdm.party_person pp ON pp.party_sk=p.party_sk WHERE p.party_sk=:p"""),
                           {"p": party_sk}).mappings().first()
    if core is None:
        raise LookupError("Party no existe")
    links = session.execute(text("""
        SELECT l.party_contact_sk, l.contact_point_sk, ch.value_code AS channel, c.contact_value, ur.value_code AS usage_role,
               cf.value_code AS confirmation, og.value_code AS origin, c.rne_excluded, l.is_primary,
               (SELECT min(pp.birth_date) FROM mdm.party_contact_point o JOIN rdm.reference_value r ON r.value_sk=o.usage_role_cd
                 LEFT JOIN mdm.party_person pp ON pp.party_sk=o.party_sk
                 WHERE o.contact_point_sk=l.contact_point_sk AND r.value_code='OWNER' AND o.valid_to IS NULL AND o.party_sk<>l.party_sk) AS owner_birth_date
        FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk
        JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd JOIN rdm.reference_value ur ON ur.value_sk=l.usage_role_cd
        JOIN rdm.reference_value cf ON cf.value_sk=l.confirmation_status_cd JOIN rdm.reference_value og ON og.value_sk=l.origin_cd
        WHERE l.party_sk=:p AND l.valid_to IS NULL ORDER BY l.party_contact_sk"""), {"p": party_sk}).mappings().all()
    prefs = session.execute(text("""
        SELECT pr.party_contact_sk, ch.value_code AS channel, pu.value_code AS purpose, pr.allowed, fq.value_code AS frequency
        FROM mdm.party_contact_pref pr JOIN rdm.reference_value ch ON ch.value_sk=pr.channel_cd JOIN rdm.reference_value pu ON pu.value_sk=pr.purpose_cd
        JOIN rdm.reference_value fq ON fq.value_sk=pr.frequency_cd WHERE pr.party_sk=:p AND pr.valid_to IS NULL"""), {"p": party_sk}).mappings().all()
    consents = dict(session.execute(text("""
        SELECT ct.value_code, cs.value_code FROM mdm.party_consent c JOIN rdm.reference_value ct ON ct.value_sk=c.consent_type_cd
        JOIN rdm.reference_value cs ON cs.value_sk=c.consent_status_cd WHERE c.party_sk=:p AND c.valid_to IS NULL"""), {"p": party_sk}).all())
    collections_service = session.execute(text("""
        SELECT 1 FROM mdm.party_service_enrollment e JOIN rdm.reference_value es ON es.value_sk=e.enrollment_status_cd
        JOIN rdm.reference_field_value f ON f.value_sk=e.service_cd AND f.field_code='collections_applies' AND lower(f.field_value)='true'
        WHERE e.party_sk=:p AND es.value_code IN ('ACTIVE','SUSPENDED') LIMIT 1"""), {"p": party_sk}).scalar() is not None
    return {"core": dict(core), "links": [dict(l) for l in links], "prefs": [dict(x) for x in prefs], "consents": consents,
            "collections_service": collections_service}


def decide(ctx: dict, link: dict, purpose: dict) -> tuple[str, dict]:
    """Aplica las 12 precedencias. Devuelve (reason_code, detalle de la preferencia aplicable)."""
    core = ctx["core"]; code = purpose["code"]
    contact_pref = next((p for p in ctx["prefs"] if p["party_contact_sk"] == link["party_contact_sk"] and p["purpose"] == code), None)
    channel_pref = next((p for p in ctx["prefs"] if p["party_contact_sk"] is None and p["channel"] == link["channel"] and p["purpose"] == code), None)
    pref = {"allowed": contact_pref["allowed"] if contact_pref else (channel_pref["allowed"] if channel_pref else None),
            "level": "CONTACT" if contact_pref else ("CHANNEL" if channel_pref else "DEFAULT")}
    if core["party_status"] == "DECEASED":                                                   # (1)
        return "DECEASED", pref
    if code == "COMMERCIAL" and is_minor(core["birth_date"]):                                # (2) Ley 1581/2012 art. 7
        return "MINOR", pref
    if link["rne_excluded"] and purpose["rne_applies"]:                                      # (3) Ley 2300/2023 art. 5
        return "RNE_EXCLUSION", pref
    if link["usage_role"] in ("SHARED", "GUARDIAN") and code == "COMMERCIAL" and is_minor(link["owner_birth_date"]):   # (4)
        return "SHARED_CONTACT_RESTRICTED", pref
    if link["usage_role"] == "REFERENCE" and code != "COLLECTIONS":                          # (5) principio de finalidad
        return "THIRD_PARTY_CONTACT", pref
    if contact_pref is not None and contact_pref["allowed"] is False:                        # (6) prevalece sobre el canal
        return "CONTACT_PURPOSE_DENIED", pref
    if link["confirmation"] in ("WRONG_PERSON", "INVALID"):                                  # (7b) nunca elegible
        return "INVALID_CONTACT", pref
    if link["confirmation"] != "CONFIRMED_BY_TITULAR" and not (contact_pref is not None and contact_pref["allowed"]):   # (7)
        return "UNCONFIRMED_CONTACT", pref
    if code == "COLLECTIONS" and not ctx["collections_service"]:                             # (8) Ley 2300/2023 art. 3
        return "NO_ACTIVE_SERVICE", pref
    req = purpose["required_consent"]                                                         # (9)
    if req:
        st = ctx["consents"].get(req)
        if st != "GRANTED":
            return ("CONSENT_REVOKED" if st in ("REVOKED", "DENIED") else "NO_CONSENT"), pref
    if contact_pref is None and channel_pref is not None and channel_pref["allowed"] is False:   # (10)
        return "CHANNEL_DENIED", pref
    freq = (contact_pref or channel_pref or {}).get("frequency")                              # (11) sin historial de envíos: NEVER = excedida
    if freq == "NEVER":
        return "FREQUENCY_EXCEEDED", pref
    return "ELIGIBLE", pref                                                                   # (12)


def evaluate_party(session: Session, party_sk: int) -> list[dict]:
    ctx = party_context(session, party_sk)
    purposes = purposes_with_attrs(session)
    out = []
    for link in ctx["links"]:
        row = {k: link[k] for k in ("party_contact_sk", "contact_point_sk", "channel", "contact_value", "usage_role", "confirmation", "origin", "rne_excluded", "is_primary")}
        row["purposes"] = []
        for pu in purposes:
            reason, pref = decide(ctx, link, pu)
            row["purposes"].append({"purpose": pu["code"], "is_eligible": reason == "ELIGIBLE", "reason": reason, "allowed": pref["allowed"], "level": pref["level"]})
        out.append(row)
    return out


def recompute_party(session: Session, party_sk: int) -> list[dict]:
    """Recalcula y persiste la caché de elegibilidad del party (SPEC §10.3)."""
    rows = evaluate_party(session, party_sk)
    reasons = _lookup(session, "CAT_ELIGIBILITY_REASON")
    purposes = _lookup(session, "CAT_CONTACT_PURPOSE")
    session.execute(text("DELETE FROM mdm.party_contact_eligibility_cache WHERE party_sk=:p"), {"p": party_sk})
    for r in rows:
        for pu in r["purposes"]:
            session.execute(text("""INSERT INTO mdm.party_contact_eligibility_cache (party_contact_sk, purpose_cd, party_sk, is_eligible, reason_cd)
                                    VALUES (:l, :pu, :p, :e, :r)"""),
                            {"l": r["party_contact_sk"], "pu": purposes[pu["purpose"]], "p": party_sk, "e": pu["is_eligible"], "r": reasons.get(pu["reason"], 0)})
    return rows


def recompute_parties(session: Session, party_sks: list[int]) -> int:
    n = 0
    for sk in dict.fromkeys(party_sks):
        try:
            recompute_party(session, sk); n += 1
        except LookupError:
            continue
    return n


def recompute_all(session: Session) -> int:
    sks = session.execute(text("SELECT party_sk FROM mdm.party ORDER BY party_sk")).scalars().all()
    return recompute_parties(session, list(sks))


def contactability(session: Session, party_sk: int, contact_point_sk: int | None = None, purpose: str | None = None) -> list[dict]:
    """Lectura en vivo (no desde caché) para GET /parties/{sk}/contactability (SPEC §11)."""
    rows = evaluate_party(session, party_sk)
    if contact_point_sk is not None:
        rows = [r for r in rows if r["contact_point_sk"] == contact_point_sk]
    if purpose:
        for r in rows:
            r["purposes"] = [p for p in r["purposes"] if p["purpose"] == purpose]
    return rows
