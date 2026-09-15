"""Decisiones de stewardship (SPEC §8.5): el steward decide directamente solo si ambos parties
provienen de una única fuente; con dos o más fuentes, o al escalar, se crea una MATCH_REVIEW_TASK
por fuente afectada asignada al data_steward de esa fuente. Regla de cierre: todos MERGE →
OWNER_CONSENSUS; cualquiera NO_MATCH → NO_MATCH; decisiones divididas o vencidas → Jefatura
(MANUAL_OVERRIDE). Cada decisión audita REVIEW_DECISION (Ley 1581/2012 art. 17; ISO/IEC
42001:2023 cl. 6.1; NIST AI RMF 1.0 GOVERN)."""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.stewardship.merge import merge_parties

REVIEW_DUE_BUSINESS_DAYS = 5


def _sk(session: Session, catalog: str, code: str) -> int:
    return session.execute(text("SELECT value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code=:c AND value_code=:v"), {"c": catalog, "v": code}).scalar_one()


def _audit(session: Session, party_sk: int | None, entity: str, entity_sk: int, actor: str, payload: dict) -> None:
    session.execute(text("""INSERT INTO mdm.party_audit_log (party_sk, entity, entity_sk, action_cd, new_value, actor)
        VALUES (:p, :e, :k, :a, CAST(:v AS jsonb), :actor)"""),
                    {"p": party_sk, "e": entity, "k": entity_sk, "a": _sk(session, "CAT_AUDIT_ACTION", "REVIEW_DECISION"), "v": json.dumps(payload, default=str), "actor": actor})


def match_sources(session: Session, match_sk: int) -> list[dict]:
    return [dict(r) for r in session.execute(text("""
        SELECT DISTINCT s.source_system_sk, s.source_system_cd, s.data_owner, s.data_steward FROM mdm.party_match m
        JOIN mdm.xref_party_source x ON x.party_sk IN (m.party_a_sk, m.party_b_sk)
        JOIN rdm.source_system s ON s.source_system_sk = x.source_system_cd WHERE m.match_sk = :k ORDER BY s.source_system_cd"""), {"k": match_sk}).mappings().all()]


def _match(session: Session, match_sk: int):
    m = session.execute(text("SELECT match_sk, party_a_sk, party_b_sk, total_score, match_status FROM mdm.party_match WHERE match_sk=:k"), {"k": match_sk}).first()
    if m is None:
        raise LookupError("Match inexistente")
    if m.match_status == "RESOLVED":
        raise ValueError("El match ya está resuelto")
    return m


def _resolve_no_match(session: Session, match_sk: int, actor: str, justification: str, how: str) -> None:
    session.execute(text("UPDATE mdm.party_match SET match_status='RESOLVED', decision_cd=:d WHERE match_sk=:k"), {"d": _sk(session, "CAT_MATCH_DECISION", "NO_MATCH"), "k": match_sk})
    session.execute(text("UPDATE mdm.match_review_task SET task_status_cd=:st WHERE match_sk=:k AND decided_at IS NULL"), {"st": _sk(session, "CAT_REQUEST_STATUS", "RESOLVED"), "k": match_sk})
    _audit(session, None, "PARTY_MATCH", match_sk, actor, {"decision": "NO_MATCH", "how": how, "justification": justification})


def _survivor(session: Session, a: int, b: int) -> tuple[int, int]:
    st = dict(session.execute(text("SELECT p.party_sk, g.value_code FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd WHERE p.party_sk IN (:a,:b)"), {"a": a, "b": b}).all())
    if st.get(a) == "GOLDEN" or st.get(b) != "GOLDEN":
        return a, b
    return b, a


def decide_match(session: Session, match_sk: int, action: str, justification: str | None, actor: str, role: str = "STEWARD") -> dict:
    if not justification or not justification.strip():
        raise ValueError("La justificación es obligatoria (regla dura 3.12)")
    m = _match(session, match_sk)
    sources = match_sources(session, match_sk)
    if role == "JEFATURA":   # decisión final de la Jefatura de Gobierno de Datos
        if action == "MERGE":
            s, a = _survivor(session, m.party_a_sk, m.party_b_sk)
            merge_sk = merge_parties(session, s, a, match_sk, "MANUAL_OVERRIDE", actor, justification)
            _audit(session, s, "PARTY_MATCH", match_sk, actor, {"decision": "MERGE", "how": "MANUAL_OVERRIDE", "merge_sk": merge_sk, "justification": justification})
            return {"match_sk": match_sk, "result": "MERGED", "merge_type": "MANUAL_OVERRIDE", "merge_sk": merge_sk}
        if action == "NO_MATCH":
            _resolve_no_match(session, match_sk, actor, justification, "MANUAL_OVERRIDE")
            return {"match_sk": match_sk, "result": "NO_MATCH", "how": "MANUAL_OVERRIDE"}
        raise ValueError("La Jefatura decide MERGE o NO_MATCH")
    if action == "NO_MATCH":
        _resolve_no_match(session, match_sk, actor, justification, "STEWARD")
        return {"match_sk": match_sk, "result": "NO_MATCH", "how": "STEWARD"}
    if action == "MERGE" and len(sources) <= 1:
        s, a = _survivor(session, m.party_a_sk, m.party_b_sk)
        merge_sk = merge_parties(session, s, a, match_sk, "STEWARD", actor, justification)
        _audit(session, s, "PARTY_MATCH", match_sk, actor, {"decision": "MERGE", "how": "STEWARD", "merge_sk": merge_sk, "justification": justification})
        return {"match_sk": match_sk, "result": "MERGED", "merge_type": "STEWARD", "merge_sk": merge_sk}
    if action not in ("MERGE", "ESCALATE"):
        raise ValueError("Acción inválida: MERGE | NO_MATCH | ESCALATE")
    # dos o más fuentes, o escalamiento explícito → una tarea por fuente afectada
    created = []
    for src in sources:
        exists = session.execute(text("SELECT task_sk FROM mdm.match_review_task WHERE match_sk=:k AND source_system_cd=:s AND decided_at IS NULL"), {"k": match_sk, "s": src["source_system_sk"]}).scalar()
        if exists:
            created.append(exists); continue
        tsk = session.execute(text("""INSERT INTO mdm.match_review_task (match_sk, source_system_cd, assignee, task_status_cd, due_at, justification)
            VALUES (:k, :s, :a, :st, now() + make_interval(days => :d), :j) RETURNING task_sk"""),
            {"k": match_sk, "s": src["source_system_sk"], "a": src["data_steward"], "st": _sk(session, "CAT_REQUEST_STATUS", "RECEIVED"),
             "d": REVIEW_DUE_BUSINESS_DAYS + 2, "j": f"Solicitud del steward ({action}): {justification}"}).scalar_one()
        created.append(tsk)
    session.execute(text("UPDATE mdm.party_match SET match_status='IN_REVIEW' WHERE match_sk=:k"), {"k": match_sk})
    _audit(session, m.party_a_sk, "PARTY_MATCH", match_sk, actor, {"decision": action, "how": "ESCALATED_TO_OWNERS", "tasks": created, "sources": [s["source_system_cd"] for s in sources], "justification": justification})
    return {"match_sk": match_sk, "result": "IN_REVIEW", "tasks": created, "sources": [s["source_system_cd"] for s in sources]}


def decide_task(session: Session, task_sk: int, decision: str, justification: str | None, actor: str) -> dict:
    if not justification or not justification.strip():
        raise ValueError("La justificación es obligatoria (regla dura 3.12)")
    if decision not in ("MERGE", "NO_MATCH", "ESCALATE"):
        raise ValueError("Decisión inválida: MERGE | NO_MATCH | ESCALATE")
    t = session.execute(text("SELECT task_sk, match_sk, decided_at FROM mdm.match_review_task WHERE task_sk=:k"), {"k": task_sk}).first()
    if t is None:
        raise LookupError("Tarea inexistente")
    if t.decided_at is not None:
        raise ValueError("La tarea ya fue decidida")
    session.execute(text("""UPDATE mdm.match_review_task SET decision_cd=:d, justification=:j, decided_at=now(), decided_by=:a, task_status_cd=:st WHERE task_sk=:k"""),
                    {"d": _sk(session, "CAT_STEWARD_DECISION", decision), "j": justification, "a": actor, "st": _sk(session, "CAT_REQUEST_STATUS", "RESOLVED"), "k": task_sk})
    # Regla de cierre
    tasks = session.execute(text("""SELECT t.task_sk, d.value_code AS decision, t.decided_at, t.due_at < now() AS overdue FROM mdm.match_review_task t
        LEFT JOIN rdm.reference_value d ON d.value_sk=t.decision_cd WHERE t.match_sk=:k"""), {"k": t.match_sk}).mappings().all()
    decisions = [x["decision"] for x in tasks if x["decided_at"] is not None]
    m = session.execute(text("SELECT party_a_sk, party_b_sk FROM mdm.party_match WHERE match_sk=:k"), {"k": t.match_sk}).first()
    if "NO_MATCH" in decisions:
        _resolve_no_match(session, t.match_sk, actor, justification, "OWNER_DECISION")
        return {"task_sk": task_sk, "match_sk": t.match_sk, "result": "NO_MATCH"}
    if len(decisions) == len(tasks) and all(d == "MERGE" for d in decisions):
        s, a = _survivor(session, m.party_a_sk, m.party_b_sk)
        merge_sk = merge_parties(session, s, a, t.match_sk, "OWNER_CONSENSUS", actor, "Consenso de owners: " + "; ".join(str(x["task_sk"]) for x in tasks))
        _audit(session, s, "PARTY_MATCH", t.match_sk, actor, {"decision": "MERGE", "how": "OWNER_CONSENSUS", "merge_sk": merge_sk})
        return {"task_sk": task_sk, "match_sk": t.match_sk, "result": "MERGED", "merge_type": "OWNER_CONSENSUS", "merge_sk": merge_sk}
    if len(decisions) == len(tasks):   # todas decididas y hay ESCALATE: queda para la Jefatura
        _audit(session, m.party_a_sk, "PARTY_MATCH", t.match_sk, actor, {"decision": "ESCALATED_TO_JEFATURA", "tasks": [dict(x) for x in tasks]})
        return {"task_sk": task_sk, "match_sk": t.match_sk, "result": "ESCALATED_TO_JEFATURA"}
    return {"task_sk": task_sk, "match_sk": t.match_sk, "result": "PENDING_OTHER_OWNERS", "decided": len(decisions), "total": len(tasks)}
