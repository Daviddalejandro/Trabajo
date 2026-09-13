"""Cola de stewardship, detalle con evidencia, decisiones, tareas por owner, unmerge y
match-preview (SPEC §11, §8.5, §8.6)."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.matching.engine import preview, run_matching
from app.stewardship.decisions import decide_match, decide_task, match_sources
from app.stewardship.merge import unmerge

router = APIRouter(tags=["stewardship"])


def actor_header(x_actor: str = Header(default="anonimo", alias="X-Actor")) -> str:
    return x_actor[:120]


def role_header(x_role: str = Header(default="STEWARD", alias="X-Role")) -> str:
    return x_role.upper()


class DecisionIn(BaseModel):
    action: str = Field(pattern="^(MERGE|NO_MATCH|ESCALATE)$")
    justification: str = Field(min_length=5)


class TaskDecisionIn(BaseModel):
    decision: str = Field(pattern="^(MERGE|NO_MATCH|ESCALATE)$")
    justification: str = Field(min_length=5)


class UnmergeIn(BaseModel):
    merge_sk: int
    reason: str = Field(min_length=5)


class PreviewIn(BaseModel):
    party_type: str = "PERSON"
    first_name: str | None = None
    first_surname: str | None = None
    second_surname: str | None = None
    birth_date: str | None = None
    identifiers: list[dict] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    divipola: str | None = None
    country: str | None = None
    legal_name: str | None = None
    trade_name: str | None = None
    ciiu: str | None = None


PARTY_SUMMARY = """
    SELECT p.party_sk, t.value_code AS party_type, g.value_code AS golden_status, st.value_code AS party_status,
           COALESCE(pp.full_name_normalized, po.legal_name_normalized) AS display_name, pp.birth_date,
           (SELECT array_agg(v.value_code || ':' || i.id_number) FROM mdm.party_identifier i JOIN rdm.reference_value v ON v.value_sk=i.id_type_cd WHERE i.party_sk=p.party_sk) AS identifiers,
           (SELECT array_agg(DISTINCT s.source_system_cd) FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd WHERE x.party_sk=p.party_sk) AS sources
    FROM mdm.party p JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd
    JOIN rdm.reference_value st ON st.value_sk=p.party_status_cd
    LEFT JOIN mdm.party_person pp ON pp.party_sk=p.party_sk LEFT JOIN mdm.party_org po ON po.party_sk=p.party_sk WHERE p.party_sk=:p"""


def party_summary(session: Session, party_sk: int) -> dict:
    r = session.execute(text(PARTY_SUMMARY), {"p": party_sk}).mappings().first()
    return dict(r) if r else {"party_sk": party_sk}


@router.get("/matches", summary="Cola de stewardship")
def list_matches(decision: str | None = "PROBABLE", status: str | None = "PENDING", limit: int = Query(50, ge=1, le=500),
                 cursor: int = Query(0, ge=0), session: Session = Depends(get_session)):
    rows = session.execute(text("""
        SELECT m.match_sk, m.party_a_sk, m.party_b_sk, m.total_score, d.value_code AS decision, m.match_status, m.rule_version, m.matched_at,
               (SELECT count(*) FROM mdm.match_review_task t WHERE t.match_sk=m.match_sk AND t.decided_at IS NULL) AS open_tasks
        FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd
        WHERE m.match_sk > :cursor AND (CAST(:dec AS TEXT) IS NULL OR d.value_code=:dec) AND (CAST(:st AS TEXT) IS NULL OR m.match_status=:st)
        ORDER BY m.match_sk LIMIT :lim"""), {"cursor": cursor, "dec": decision, "st": status, "lim": limit + 1}).mappings().all()
    items = [dict(r) | {"party_a": party_summary(session, r["party_a_sk"]), "party_b": party_summary(session, r["party_b_sk"])} for r in rows[:limit]]
    return {"items": items, "next_cursor": items[-1]["match_sk"] if len(rows) > limit else None}


@router.get("/matches/{match_sk}", summary="Detalle con score_detail desglosado, fuentes y tareas")
def get_match(match_sk: int, session: Session = Depends(get_session)):
    m = session.execute(text("""SELECT m.match_sk, m.party_a_sk, m.party_b_sk, m.total_score, m.score_detail, d.value_code AS decision, m.match_status, m.rule_version, m.matched_at
        FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd WHERE m.match_sk=:k"""), {"k": match_sk}).mappings().first()
    if m is None:
        raise HTTPException(404, "Match inexistente")
    tasks = session.execute(text("""SELECT t.task_sk, s.source_system_cd, s.data_owner, t.assignee, st.value_code AS status, d.value_code AS decision, t.justification,
        t.created_at, t.due_at, t.decided_at, t.decided_by, t.due_at < now() AND t.decided_at IS NULL AS overdue FROM mdm.match_review_task t
        JOIN rdm.source_system s ON s.source_system_sk=t.source_system_cd JOIN rdm.reference_value st ON st.value_sk=t.task_status_cd
        LEFT JOIN rdm.reference_value d ON d.value_sk=t.decision_cd WHERE t.match_sk=:k ORDER BY t.task_sk"""), {"k": match_sk}).mappings().all()
    rules = session.execute(text("SELECT r.attribute, r.weight, r.algorithm, r.params FROM mdm.match_rule r JOIN rdm.reference_value t ON t.value_sk=r.entity_type_cd "
                                 "JOIN mdm.party p ON p.party_type_cd=r.entity_type_cd WHERE p.party_sk=:p AND r.version=:v ORDER BY r.weight DESC"),
                            {"p": m["party_a_sk"], "v": m["rule_version"]}).mappings().all()
    return dict(m) | {"party_a": party_summary(session, m["party_a_sk"]), "party_b": party_summary(session, m["party_b_sk"]),
                      "sources": match_sources(session, match_sk), "tasks": [dict(t) for t in tasks], "rules": [dict(r) for r in rules]}


@router.post("/matches/{match_sk}/decision", summary="Decisión del steward (justificación obligatoria)")
def post_decision(match_sk: int, body: DecisionIn, actor: str = Depends(actor_header), role: str = Depends(role_header), session: Session = Depends(get_session)):
    try:
        out = decide_match(session, match_sk, body.action, body.justification, actor, role)
        session.commit(); return out
    except LookupError as e:
        session.rollback(); raise HTTPException(404, str(e))
    except ValueError as e:
        session.rollback(); raise HTTPException(409, str(e))


@router.get("/review-tasks", summary="Tareas de revisión por owner de fuente")
def list_tasks(assignee: str | None = None, status: str | None = None, session: Session = Depends(get_session)):
    rows = session.execute(text("""SELECT t.task_sk, t.match_sk, s.source_system_cd, s.data_owner, t.assignee, st.value_code AS status, d.value_code AS decision,
        t.due_at, t.decided_at, t.due_at < now() AND t.decided_at IS NULL AS overdue, m.total_score FROM mdm.match_review_task t
        JOIN rdm.source_system s ON s.source_system_sk=t.source_system_cd JOIN rdm.reference_value st ON st.value_sk=t.task_status_cd
        LEFT JOIN rdm.reference_value d ON d.value_sk=t.decision_cd JOIN mdm.party_match m ON m.match_sk=t.match_sk
        WHERE (CAST(:a AS TEXT) IS NULL OR t.assignee=:a) AND (CAST(:s AS TEXT) IS NULL OR st.value_code=:s) ORDER BY t.due_at NULLS LAST, t.task_sk"""),
                           {"a": assignee, "s": status}).mappings().all()
    return [dict(r) for r in rows]


@router.post("/review-tasks/{task_sk}/decision", summary="Decisión del owner de la fuente (regla de cierre §8.5)")
def post_task_decision(task_sk: int, body: TaskDecisionIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    try:
        out = decide_task(session, task_sk, body.decision, body.justification, actor)
        session.commit(); return out
    except LookupError as e:
        session.rollback(); raise HTTPException(404, str(e))
    except ValueError as e:
        session.rollback(); raise HTTPException(409, str(e))


@router.post("/parties/{party_sk}/unmerge", summary="Deshace un merge desde el snapshot previo")
def post_unmerge(party_sk: int, body: UnmergeIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    owner = session.execute(text("SELECT 1 FROM mdm.party_merge_history WHERE merge_sk=:k AND :p IN (surviving_party_sk, merged_party_sk)"), {"k": body.merge_sk, "p": party_sk}).scalar()
    if not owner:
        raise HTTPException(404, "El merge no corresponde a este party")
    try:
        out = unmerge(session, body.merge_sk, actor, body.reason)
        session.commit(); return out
    except ValueError as e:
        session.rollback(); raise HTTPException(409, str(e))


@router.post("/parties/match-preview", summary="Prevención de duplicados en origen: candidatos sin persistir (§8.6)")
def post_preview(body: PreviewIn, limit: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)):
    out = preview(session, body.model_dump(), limit)
    session.rollback()   # nada se persiste
    return out


@router.post("/matching/run", summary="Ejecuta el matching sobre los candidatos pendientes")
def post_run(actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    return run_matching(session, actor)
