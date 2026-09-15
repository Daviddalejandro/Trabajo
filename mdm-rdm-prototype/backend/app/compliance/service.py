"""Operaciones de cumplimiento (SPEC §10 y §11): consentimientos multi-tipo, preferencias de canal y de
contacto, confirmación de contactos, ARCO con SLA en días hábiles, RNE simulado, audiencias, purga
simulada y feed de cambios del golden. Todas las escrituras en mdm.* auditan por trigger con el actor de
la sesión; las derivadas de una solicitud ARCO llevan arco_request_id (Ley 1581/2012 art. 17)."""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.compliance.eligibility import recompute_parties, recompute_party
from app.pipeline.common import contact_hash, e164

# Festivos nacionales de Colombia 2026 (Ley 51/1983) para el cómputo de días hábiles del SLA ARCO.
CO_HOLIDAYS_2026 = {date(2026, 1, 1), date(2026, 1, 12), date(2026, 3, 23), date(2026, 4, 2), date(2026, 4, 3), date(2026, 5, 1),
                    date(2026, 5, 18), date(2026, 6, 8), date(2026, 6, 15), date(2026, 6, 29), date(2026, 7, 20), date(2026, 8, 7),
                    date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 16), date(2026, 12, 8), date(2026, 12, 25)}


def add_business_days(start: datetime, days: int) -> datetime:
    d = start
    remaining = days
    while remaining > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.date() not in CO_HOLIDAYS_2026:
            remaining -= 1
    return d


def subtract_business_days(start: datetime, days: int) -> datetime:
    d = start
    remaining = days
    while remaining > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5 and d.date() not in CO_HOLIDAYS_2026:
            remaining -= 1
    return d


def _sk(session: Session, catalog: str, code: str) -> int:
    v = session.execute(text("SELECT value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code=:c AND value_code=:v AND is_active"), {"c": catalog, "v": code}).scalar()
    if v is None:
        raise LookupError(f"{catalog}.{code} no existe en el RDM")
    return v


def _attr(session: Session, catalog: str, code: str, field: str) -> str | None:
    return session.execute(text("""SELECT f.field_value FROM rdm.vw_rdm_lookup l JOIN rdm.reference_field_value f ON f.value_sk=l.value_sk
        WHERE l.catalog_code=:c AND l.value_code=:v AND f.field_code=:f"""), {"c": catalog, "v": code, "f": field}).scalar()


def _console_source(session: Session) -> int:
    return session.execute(text("SELECT source_system_sk FROM rdm.source_system WHERE source_system_cd='MDM_CONSOLE'")).scalar_one()


def _set(session: Session, name: str, value) -> None:
    session.execute(text("SELECT set_config(:n, :v, false)"), {"n": name, "v": "" if value is None else str(value)})


def _audit(session: Session, party_sk: int | None, entity: str, entity_sk: int | None, action: str, actor: str, payload: dict,
           arco_request_id: int | None = None) -> None:
    session.execute(text("""INSERT INTO mdm.party_audit_log (party_sk, entity, entity_sk, action_cd, new_value, actor, arco_request_id, source_system_cd)
        VALUES (:p, :e, :k, :a, CAST(:v AS jsonb), :actor, :r, :s)"""),
                    {"p": party_sk, "e": entity, "k": entity_sk, "a": _sk(session, "CAT_AUDIT_ACTION", action), "v": json.dumps(payload, default=str),
                     "actor": actor, "r": arco_request_id, "s": _console_source(session)})


def _party_exists(session: Session, party_sk: int) -> None:
    if session.execute(text("SELECT 1 FROM mdm.party WHERE party_sk=:p"), {"p": party_sk}).scalar() is None:
        raise LookupError("Party no existe")


# ------------------------------------------------------------------ consentimientos y preferencias
def set_consent(session: Session, party_sk: int, consent_type: str, status: str, actor: str, evidence_ref: str | None = None,
                arco_request_id: int | None = None) -> dict:
    """Crea una fila nueva y cierra la vigente (nunca edita el histórico, SPEC §5.2 capa 8)."""
    _party_exists(session, party_sk)
    _set(session, "app.actor", actor); _set(session, "app.arco_request_id", arco_request_id)
    t, st = _sk(session, "CAT_CONSENT_TYPE", consent_type), _sk(session, "CAT_CONSENT_STATUS", status)
    session.execute(text("UPDATE mdm.party_consent SET valid_to=now() WHERE party_sk=:p AND consent_type_cd=:t AND valid_to IS NULL"), {"p": party_sk, "t": t})
    granted = status == "GRANTED"
    sk = session.execute(text("""INSERT INTO mdm.party_consent (party_sk, consent_type_cd, consent_status_cd, granted_at, revoked_at, evidence_ref, source_system_cd)
        VALUES (:p, :t, :s, CASE WHEN :g THEN now() END, CASE WHEN :g THEN NULL ELSE now() END, :e, :src) RETURNING consent_sk"""),
                         {"p": party_sk, "t": t, "s": st, "g": granted, "e": evidence_ref or f"MDM_CONSOLE:{actor}", "src": _console_source(session)}).scalar_one()
    recompute_party(session, party_sk)
    _set(session, "app.arco_request_id", None)
    return {"consent_sk": sk, "party_sk": party_sk, "consent_type": consent_type, "status": status}


def set_preferences(session: Session, party_sk: int, items: list[dict], actor: str, party_contact_sk: int | None = None) -> dict:
    """Preferencias de canal (party_contact_sk NULL) o de contacto (una fila por finalidad). Cierra la vigente si cambia."""
    _party_exists(session, party_sk)
    _set(session, "app.actor", actor)
    console = _console_source(session)
    if party_contact_sk is not None:
        link = session.execute(text("SELECT c.channel_cd FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk "
                                    "WHERE l.party_contact_sk=:k AND l.party_sk=:p"), {"k": party_contact_sk, "p": party_sk}).scalar()
        if link is None:
            raise LookupError("El vínculo de contacto no pertenece a este party")
    written = 0
    for it in items:
        ch = link if party_contact_sk is not None else _sk(session, "CAT_CONTACT_CHANNEL", it["channel"])
        pu = _sk(session, "CAT_CONTACT_PURPOSE", it["purpose"])
        fq = _sk(session, "CAT_CONTACT_FREQUENCY", it.get("frequency") or "ANY")
        cur = session.execute(text("""SELECT pref_sk, allowed, frequency_cd FROM mdm.party_contact_pref WHERE party_sk=:p AND channel_cd=:c AND purpose_cd=:u
            AND party_contact_sk IS NOT DISTINCT FROM :l AND valid_to IS NULL"""), {"p": party_sk, "c": ch, "u": pu, "l": party_contact_sk}).first()
        if cur and cur.allowed == bool(it["allowed"]) and cur.frequency_cd == fq:
            continue
        if cur:
            session.execute(text("UPDATE mdm.party_contact_pref SET valid_to=now() WHERE pref_sk=:k"), {"k": cur.pref_sk})
        session.execute(text("""INSERT INTO mdm.party_contact_pref (party_sk, channel_cd, party_contact_sk, purpose_cd, allowed, frequency_cd, origin_cd)
            VALUES (:p, :c, :l, :u, :a, :f, :o)"""), {"p": party_sk, "c": ch, "l": party_contact_sk, "u": pu, "a": bool(it["allowed"]), "f": fq,
                                                    "o": _sk(session, "CAT_PREF_ORIGIN", it.get("origin") or "TITULAR")})
        written += 1
    _ = console
    rows = recompute_party(session, party_sk)
    return {"party_sk": party_sk, "party_contact_sk": party_contact_sk, "written": written,
            "contacts": [r for r in rows if party_contact_sk is None or r["party_contact_sk"] == party_contact_sk]}


def set_confirmation(session: Session, party_sk: int, party_contact_sk: int, status: str, actor: str, evidence: str | None = None) -> dict:
    _party_exists(session, party_sk)
    _set(session, "app.actor", actor)
    st = _sk(session, "CAT_CONTACT_CONFIRMATION", status)
    n = session.execute(text("UPDATE mdm.party_contact_point SET confirmation_status_cd=:s WHERE party_contact_sk=:k AND party_sk=:p"),
                        {"s": st, "k": party_contact_sk, "p": party_sk}).rowcount
    if not n:
        raise LookupError("El vínculo de contacto no pertenece a este party")
    _audit(session, party_sk, "PARTY_CONTACT_POINT", party_contact_sk, "UPDATE", actor, {"confirmation_status": status, "evidence": evidence, "origin": "gestión"})
    rows = recompute_party(session, party_sk)
    return {"party_sk": party_sk, "party_contact_sk": party_contact_sk, "confirmation_status": status,
            "contact": next((r for r in rows if r["party_contact_sk"] == party_contact_sk), None)}


def list_contacts(session: Session, party_sk: int, purpose: str | None = None, confirmation: str | None = None, origin: str | None = None,
                  usage_role: str | None = None) -> list[dict]:
    """Lista de trabajo (p. ej. cobranza): vínculos filtrables por finalidad elegible, confirmación, origen y rol de uso."""
    rows = session.execute(text("""
        SELECT l.party_contact_sk, l.contact_point_sk, ch.value_code AS channel, c.contact_value, ur.value_code AS usage_role, cf.value_code AS confirmation,
               og.value_code AS origin, c.rne_excluded, l.is_primary, s.source_system_cd,
               (SELECT jsonb_object_agg(pu.value_code, jsonb_build_object('is_eligible', e.is_eligible, 'reason', rs.value_code))
                  FROM mdm.party_contact_eligibility_cache e JOIN rdm.reference_value pu ON pu.value_sk=e.purpose_cd JOIN rdm.reference_value rs ON rs.value_sk=e.reason_cd
                  WHERE e.party_contact_sk=l.party_contact_sk) AS eligibility
        FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk
        JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd JOIN rdm.reference_value ur ON ur.value_sk=l.usage_role_cd
        JOIN rdm.reference_value cf ON cf.value_sk=l.confirmation_status_cd JOIN rdm.reference_value og ON og.value_sk=l.origin_cd
        JOIN rdm.source_system s ON s.source_system_sk=l.source_system_cd
        WHERE l.party_sk=:p AND l.valid_to IS NULL AND (CAST(:cf AS TEXT) IS NULL OR cf.value_code=:cf)
          AND (CAST(:og AS TEXT) IS NULL OR og.value_code=:og) AND (CAST(:ur AS TEXT) IS NULL OR ur.value_code=:ur)
        ORDER BY l.party_contact_sk"""), {"p": party_sk, "cf": confirmation, "og": origin, "ur": usage_role}).mappings().all()
    out = [dict(r) for r in rows]
    if purpose:
        out = [r for r in out if (r["eligibility"] or {}).get(purpose, {}).get("is_eligible")]
    return out


# ------------------------------------------------------------------ ARCO
def create_arco_request(session: Session, party_sk: int, arco_type: str, actor: str, channel_received: str | None = None,
                        requested_at: datetime | None = None, note: str | None = None) -> dict:
    """Consultas 10 días hábiles (Ley 1581/2012 art. 14); reclamos 15 (art. 15); supresión conforme Decreto 1377/2013 art. 9.
    La cancelación en el prototipo revoca los consentimientos y marca retención PURGE_ELIGIBLE: trazabilidad antes que borrado."""
    _party_exists(session, party_sk)
    _set(session, "app.actor", actor)
    sla = int(_attr(session, "CAT_ARCO_REQUEST_TYPE", arco_type, "sla_business_days") or 15)
    requested_at = requested_at or datetime.now(timezone.utc)
    due_at = add_business_days(requested_at, sla)
    sk = session.execute(text("""INSERT INTO mdm.data_subject_request (party_sk, arco_type_cd, request_status_cd, requested_at, due_at, channel_received, resolution_note)
        VALUES (:p, :t, :s, :r, :d, :c, :n) RETURNING request_sk"""),
                         {"p": party_sk, "t": _sk(session, "CAT_ARCO_REQUEST_TYPE", arco_type), "s": _sk(session, "CAT_REQUEST_STATUS", "RECEIVED"),
                          "r": requested_at, "d": due_at, "c": channel_received, "n": note}).scalar_one()
    _set(session, "app.arco_request_id", sk)
    actions: list[str] = []
    if arco_type == "ACCESS":
        _audit(session, party_sk, "PARTY", party_sk, "ARCO_READ", actor, {"arco_type": arco_type, "note": "Lectura del golden entregada al titular"}, sk)
        actions.append("ARCO_READ auditado")
    if arco_type == "CANCELLATION":
        current = session.execute(text("""SELECT ct.value_code FROM mdm.party_consent c JOIN rdm.reference_value ct ON ct.value_sk=c.consent_type_cd
            JOIN rdm.reference_value cs ON cs.value_sk=c.consent_status_cd WHERE c.party_sk=:p AND c.valid_to IS NULL AND cs.value_code='GRANTED'"""), {"p": party_sk}).scalars().all()
        for ct in current:
            set_consent(session, party_sk, ct, "REVOKED", actor, evidence_ref=f"ARCO:{sk}", arco_request_id=sk)
            _set(session, "app.arco_request_id", sk)
        actions.append(f"{len(current)} consentimientos revocados")
        session.execute(text("""INSERT INTO mdm.party_data_retention (party_sk, entity, entity_sk, retention_rule_cd, purge_after, legal_basis, purge_status)
            VALUES (:p, 'PARTY', :p, :r, CURRENT_DATE, 'Decreto 1377/2013 art. 9 · supresión solicitada por el titular', 'SCHEDULED')"""),
                        {"p": party_sk, "r": _sk(session, "CAT_RETENTION_RULE", "PURGE_ELIGIBLE")})
        session.execute(text("UPDATE mdm.data_subject_request SET request_status_cd=:s WHERE request_sk=:k"), {"s": _sk(session, "CAT_REQUEST_STATUS", "IN_PROGRESS"), "k": sk})
        _audit(session, party_sk, "PARTY_DATA_RETENTION", party_sk, "PURGE_MARK", actor, {"rule": "PURGE_ELIGIBLE", "arco_request_id": sk}, sk)
        actions.append("retención PURGE_ELIGIBLE marcada")
        recompute_party(session, party_sk)
    _set(session, "app.arco_request_id", None)
    return {"request_sk": sk, "party_sk": party_sk, "arco_type": arco_type, "sla_business_days": sla, "requested_at": requested_at, "due_at": due_at, "actions": actions}


def resolve_arco_request(session: Session, request_sk: int, status: str, actor: str, note: str | None = None) -> dict:
    if status not in ("RESOLVED", "REJECTED", "IN_PROGRESS"):
        raise ValueError("Estado inválido: RESOLVED | REJECTED | IN_PROGRESS")
    _set(session, "app.actor", actor); _set(session, "app.arco_request_id", request_sk)
    r = session.execute(text("""UPDATE mdm.data_subject_request SET request_status_cd=:s, resolved_at=CASE WHEN :final THEN now() ELSE resolved_at END,
        resolution_note=COALESCE(:n, resolution_note) WHERE request_sk=:k RETURNING party_sk"""),
                        {"s": _sk(session, "CAT_REQUEST_STATUS", status), "final": status in ("RESOLVED", "REJECTED"), "n": note, "k": request_sk}).first()
    if r is None:
        raise LookupError("Solicitud inexistente")
    _audit(session, r.party_sk, "DATA_SUBJECT_REQUEST", request_sk, "ARCO_UPDATE", actor, {"status": status, "note": note}, request_sk)
    _set(session, "app.arco_request_id", None)
    return {"request_sk": request_sk, "status": status}


def list_arco_requests(session: Session, sla: str | None = None, party_sk: int | None = None, limit: int = 200) -> list[dict]:
    rows = session.execute(text("""
        SELECT r.request_sk, r.party_sk, COALESCE(pp.full_name_normalized, po.legal_name_normalized) AS display_name, at.value_code AS arco_type,
               st.value_code AS status, r.requested_at, r.due_at, r.resolved_at, r.channel_received, r.resolution_note,
               CASE WHEN r.resolved_at IS NOT NULL THEN 'RESOLVED' WHEN r.due_at < now() THEN 'OVERDUE'
                    WHEN r.due_at < now() + interval '2 days' THEN 'DUE_SOON' ELSE 'ON_TRACK' END AS sla_status,
               EXTRACT(day FROM now() - r.due_at)::int AS days_past_due
        FROM mdm.data_subject_request r JOIN rdm.reference_value at ON at.value_sk=r.arco_type_cd JOIN rdm.reference_value st ON st.value_sk=r.request_status_cd
        LEFT JOIN mdm.party_person pp ON pp.party_sk=r.party_sk LEFT JOIN mdm.party_org po ON po.party_sk=r.party_sk
        WHERE (CAST(:p AS BIGINT) IS NULL OR r.party_sk=:p) ORDER BY r.due_at NULLS LAST, r.request_sk LIMIT :l"""), {"p": party_sk, "l": limit}).mappings().all()
    out = [dict(r) for r in rows]
    if sla and sla != "ALL":
        out = [r for r in out if r["sla_status"] == sla or (sla == "OPEN" and r["sla_status"] != "RESOLVED")]
    return out


# ------------------------------------------------------------------ RNE
def rne_sync(session: Session, file: str | Path, actor: str) -> dict:
    """Marca rne_excluded en los CONTACT_POINT cuyo hash coincide y lo retira de los que ya no están en el registro.
    Nunca toca preferencias ni finalidades distintas de COMMERCIAL (Ley 2300/2023 art. 5)."""
    _set(session, "app.actor", actor)
    path = Path(file)
    hashes = set()
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = e164(row.get("numero") or row.get("number") or "")
            if v:
                hashes.add(contact_hash("PHONE", v))
    phone = _sk(session, "CAT_CONTACT_CHANNEL", "PHONE")
    marked = session.execute(text("""UPDATE mdm.contact_point SET rne_excluded=true, rne_synced_at=now()
        WHERE channel_cd=:ch AND contact_hash = ANY(:h) AND NOT rne_excluded RETURNING contact_point_sk"""), {"ch": phone, "h": list(hashes)}).scalars().all()
    cleared = session.execute(text("""UPDATE mdm.contact_point SET rne_excluded=false, rne_synced_at=now()
        WHERE channel_cd=:ch AND rne_excluded AND NOT (contact_hash = ANY(:h)) RETURNING contact_point_sk"""), {"ch": phone, "h": list(hashes)}).scalars().all()
    session.execute(text("UPDATE mdm.contact_point SET rne_synced_at=now() WHERE channel_cd=:ch AND contact_hash = ANY(:h)"), {"ch": phone, "h": list(hashes)})
    affected = list(marked) + list(cleared)
    parties = session.execute(text("SELECT DISTINCT party_sk FROM mdm.party_contact_point WHERE contact_point_sk = ANY(:c)"), {"c": affected}).scalars().all() if affected else []
    n = recompute_parties(session, list(parties))
    _audit(session, None, "CONTACT_POINT", None, "RNE_SYNC", actor, {"file": str(path), "numbers": len(hashes), "marked": len(marked), "cleared": len(cleared), "parties_recomputed": n})
    return {"file": str(path), "numbers_in_registry": len(hashes), "marked": len(marked), "cleared": len(cleared), "parties_recomputed": n}


# ------------------------------------------------------------------ audiencias
def audience(session: Session, purpose: str, channel: str, actor: str, role: str | None = None, segment: str | None = None, service: str | None = None,
             enrollment_status: str | None = None, limit: int = 500) -> dict:
    """Solo parties GOLDEN y ACTIVE con contacto elegible para la finalidad y el canal (SPEC §10.4). Se audita actor, filtros y conteo
    porque es un tratamiento con finalidad declarada (Ley 1581/2012 art. 4 lit. b)."""
    seg_type, _, seg_code = (segment or "").partition(".")
    rows = session.execute(text("""
        SELECT DISTINCT ON (p.party_sk, c.contact_value) p.party_sk, COALESCE(pp.full_name_normalized, po.legal_name_normalized) AS display_name,
               c.contact_value, ch.value_code AS channel, rs.value_code AS reason
        FROM mdm.party_contact_eligibility_cache e
        JOIN mdm.party p ON p.party_sk=e.party_sk JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd AND g.value_code='GOLDEN'
        JOIN rdm.reference_value st ON st.value_sk=p.party_status_cd AND st.value_code='ACTIVE'
        JOIN rdm.reference_value pu ON pu.value_sk=e.purpose_cd AND pu.value_code=:purpose
        JOIN rdm.reference_value rs ON rs.value_sk=e.reason_cd
        JOIN mdm.party_contact_point l ON l.party_contact_sk=e.party_contact_sk AND l.valid_to IS NULL
        JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd AND ch.value_code=:channel
        LEFT JOIN mdm.party_person pp ON pp.party_sk=p.party_sk LEFT JOIN mdm.party_org po ON po.party_sk=p.party_sk
        WHERE e.is_eligible
          AND (CAST(:role AS TEXT) IS NULL OR EXISTS (SELECT 1 FROM mdm.party_role r JOIN rdm.reference_value v ON v.value_sk=r.role_cd WHERE r.party_sk=p.party_sk AND v.value_code=:role AND r.valid_to IS NULL))
          AND (CAST(:seg_type AS TEXT) = '' OR EXISTS (SELECT 1 FROM mdm.party_segment sg JOIN rdm.reference_value t ON t.value_sk=sg.segment_type_cd JOIN rdm.reference_value v ON v.value_sk=sg.segment_cd
                                                       WHERE sg.party_sk=p.party_sk AND sg.valid_to IS NULL AND t.value_code=:seg_type AND v.value_code=:seg_code))
          AND (CAST(:service AS TEXT) IS NULL OR EXISTS (SELECT 1 FROM mdm.party_service_enrollment en JOIN rdm.reference_value v ON v.value_sk=en.service_cd JOIN rdm.reference_value es ON es.value_sk=en.enrollment_status_cd
                                                        WHERE en.party_sk=p.party_sk AND v.value_code=:service AND (CAST(:es AS TEXT) IS NULL OR es.value_code=:es)))
        ORDER BY p.party_sk, c.contact_value LIMIT :lim"""),
                           {"purpose": purpose, "channel": channel, "role": role, "seg_type": seg_type, "seg_code": seg_code, "service": service, "es": enrollment_status, "lim": limit}).mappings().all()
    items = [dict(r) for r in rows]
    filters = {"purpose": purpose, "channel": channel, "role": role, "segment": segment, "service": service, "enrollment_status": enrollment_status}
    _audit(session, None, "AUDIENCE", None, "AUDIENCE_RUN", actor, {"filters": filters, "count": len(items)})
    return {"filters": filters, "count": len(items), "items": items, "audited": True}


# ------------------------------------------------------------------ retención y purga simulada
def purge_candidates(session: Session, actor: str, dry_run: bool = True) -> dict:
    """Parties con purge_after vencido, sin LEGAL_HOLD y sin vínculo de servicio activo. El prototipo nunca borra (SPEC §10.5)."""
    _set(session, "app.actor", actor)
    rows = session.execute(text("""
        SELECT r.retention_sk, r.party_sk, COALESCE(pp.full_name_normalized, po.legal_name_normalized) AS display_name, r.entity, r.entity_sk,
               rr.value_code AS rule, r.purge_after, r.legal_basis, r.purge_status
        FROM mdm.party_data_retention r JOIN rdm.reference_value rr ON rr.value_sk=r.retention_rule_cd
        LEFT JOIN mdm.party_person pp ON pp.party_sk=r.party_sk LEFT JOIN mdm.party_org po ON po.party_sk=r.party_sk
        WHERE r.purge_after <= CURRENT_DATE AND r.purge_status='SCHEDULED' AND rr.value_code <> 'LEGAL_HOLD'
          AND NOT EXISTS (SELECT 1 FROM mdm.party_data_retention h JOIN rdm.reference_value hr ON hr.value_sk=h.retention_rule_cd WHERE h.party_sk=r.party_sk AND hr.value_code='LEGAL_HOLD' AND h.purge_status<>'PURGED')
          AND NOT EXISTS (SELECT 1 FROM mdm.party_service_enrollment e JOIN rdm.reference_value es ON es.value_sk=e.enrollment_status_cd WHERE e.party_sk=r.party_sk AND es.value_code IN ('ACTIVE','SUSPENDED'))
        ORDER BY r.purge_after, r.retention_sk""")).mappings().all()
    items = [dict(r) for r in rows]
    for it in items:
        _audit(session, it["party_sk"], "PARTY_DATA_RETENTION", it["retention_sk"], "PURGE_SIMULATED", actor, {"dry_run": dry_run, "rule": it["rule"], "purge_after": it["purge_after"]})
    return {"dry_run": dry_run, "count": len(items), "items": items, "note": "Simulación: el prototipo nunca borra; la purga real es producción (SPEC §10.5)"}


# ------------------------------------------------------------------ feed de cambios
def changes(session: Session, since: datetime | None = None, entity: str | None = None, limit: int = 200, cursor: int = 0) -> dict:
    """Feed de cambios del golden derivado de PARTY_AUDIT_LOG (mismo contrato que el tópico Kafka en producción)."""
    rows = session.execute(text("""
        SELECT a.audit_sk, a.party_sk, a.entity, a.entity_sk, ac.value_code AS action, p.golden_version, g.value_code AS golden_status, a.actor,
               s.source_system_cd, a.batch_id, a.merge_sk, a.arco_request_id, a.occurred_at
        FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd
        LEFT JOIN mdm.party p ON p.party_sk=a.party_sk LEFT JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd
        LEFT JOIN rdm.source_system s ON s.source_system_sk=a.source_system_cd
        WHERE a.audit_sk > :cursor AND (CAST(:since AS TIMESTAMPTZ) IS NULL OR a.occurred_at >= :since) AND (CAST(:e AS TEXT) IS NULL OR a.entity=:e)
        ORDER BY a.audit_sk LIMIT :lim"""), {"cursor": cursor, "since": since, "e": entity, "lim": limit + 1}).mappings().all()
    items = [dict(r) for r in rows[:limit]]
    return {"items": items, "next_cursor": items[-1]["audit_sk"] if len(rows) > limit else None}
