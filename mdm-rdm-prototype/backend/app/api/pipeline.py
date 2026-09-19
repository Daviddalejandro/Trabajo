"""Endpoints de operación del pipeline (SPEC §11): ejecución por fuente, rehomologación y estadísticas."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.pipeline.rehomologate import rehomologate, rehomologate_preview
from app.pipeline.run import run_ingest
from app.pipeline.sources import SOURCES

router = APIRouter(tags=["pipeline"])


def actor_header(x_actor: str = Header(default="anonimo", alias="X-Actor")) -> str:
    return x_actor[:120]


@router.post("/pipeline/{source}/run", summary="Ejecuta la ingesta de una fuente (7 etapas)")
def run(source: str, mode: str = Query("full", pattern="^(full|delta)$"), file: str | None = None,
        actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    if source not in SOURCES:
        raise HTTPException(404, f"Fuente {source} no existe; válidas: {', '.join(SOURCES)}")
    return run_ingest(session, source, mode, file, actor)


class RecordIn(BaseModel):
    external_id: str = Field(min_length=1, max_length=60)
    payload: dict


@router.get("/pipeline/batches", summary="Bitácora de cargas (staging.LOAD_BATCH): masivas FULL/DELTA y transaccionales TX")
def batches(limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    rows = session.execute(text("""
        SELECT b.batch_id, s.source_system_cd AS source, b.mode, b.status, b.started_at, b.finished_at, b.actor,
               b.extracted, b.unchanged_hash, b.standardized, b.homologated, b.unknown_codes, b.dq_passed, b.dq_quarantined,
               b.xref_hits, b.loaded, b.matched, b.auto_merged, b.probable, b.detail,
               (SELECT count(*) FROM mdm.party_bucket k WHERE k.batch_id=b.batch_id) AS buckets
        FROM staging.load_batch b JOIN rdm.source_system s ON s.source_system_sk=b.source_system_cd
        ORDER BY b.batch_id DESC LIMIT :l"""), {"l": limit}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/pipeline/{source}/example", summary="Un registro nativo de la fuente (de su landing zone) para probar la carga transaccional")
def example(source: str, session: Session = Depends(get_session)):
    if source not in SOURCES:
        raise HTTPException(404, f"Fuente {source} no existe; válidas: {', '.join(SOURCES)}")
    _, table = SOURCES[source]
    row = session.execute(text(f"SELECT external_id, payload FROM staging.{table} ORDER BY raw_sk DESC LIMIT 1")).first()
    if not row:
        raise HTTPException(404, f"La landing zone de {source} está vacía: ingiera primero la fuente")
    from datetime import datetime
    return {"source": source, "external_id_example": row[0], "suggested_external_id": f"TX{datetime.now().strftime('%H%M%S')}", "payload": row[1]}


@router.post("/pipeline/{source}/record", summary="Carga transaccional: un registro nativo por las 7 etapas (lote TX auditado, buckets y matching incluidos)")
def record(source: str, body: RecordIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    if source not in SOURCES:
        raise HTTPException(404, f"Fuente {source} no existe; válidas: {', '.join(SOURCES)}")
    r = run_ingest(session, source, "tx", None, actor, rows=[(body.external_id, body.payload)])
    system_cd = SOURCES[source][0]
    party = session.execute(text("SELECT x.party_sk FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd "
                                 "WHERE s.source_system_cd=:s AND x.external_id=:e"), {"s": system_cd, "e": body.external_id}).scalar()
    outcome = None
    if party:
        g = session.execute(text("SELECT g.value_code FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd WHERE p.party_sk=:p"), {"p": party}).scalar()
        merged_into = session.execute(text("SELECT surviving_party_sk FROM mdm.party_merge_history WHERE merged_party_sk=:p AND unmerged_at IS NULL ORDER BY merge_sk DESC LIMIT 1"), {"p": party}).scalar()
        pending = session.execute(text("""SELECT m.match_sk, d.value_code, m.total_score FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd
            WHERE (m.party_a_sk=:p OR m.party_b_sk=:p) AND m.match_status IN ('PENDING','IN_REVIEW') ORDER BY m.match_sk DESC"""), {"p": party}).all()
        buckets = session.execute(text("""SELECT s.value_code, b.blocking_key, (SELECT count(*) FROM mdm.bucket_candidate c2 WHERE c2.bucket_sk=b.bucket_sk) AS members
            FROM mdm.bucket_candidate c JOIN mdm.party_bucket b ON b.bucket_sk=c.bucket_sk JOIN rdm.reference_value s ON s.value_sk=b.blocking_strategy_cd
            WHERE c.party_sk=:p AND b.batch_id=:b ORDER BY 1"""), {"p": party, "b": r["batch_id"]}).all()
        outcome = {"party_sk": party, "golden_status": g, "merged_into": merged_into, "xref_hit": r["xref_hits"] > 0,
                   "pending_matches": [{"match_sk": m, "decision": d, "score": float(sc)} for m, d, sc in pending],
                   "buckets": [{"strategy": st, "key": k, "members": int(n)} for st, k, n in buckets]}
    return {**r, "outcome": outcome}


@router.get("/rdm/rehomologate/preview", summary="Cuántos UNKNOWN hay y cuántos se corregirían con los mapeos vigentes (§7.2)")
def rehomologate_preview_endpoint(catalog: str | None = None, session: Session = Depends(get_session)):
    return rehomologate_preview(session, catalog)


@router.post("/rdm/rehomologate", summary="Reprocesa los UNKNOWN de un catálogo (§7.2)")
def rehomologate_endpoint(catalog: str | None = None, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    return rehomologate(session, catalog, actor)


@router.get("/stats", summary="Contadores para el dashboard")
def stats(session: Session = Depends(get_session)):
    parties = session.execute(text("""
        SELECT g.value_code AS golden_status, t.value_code AS party_type, count(*) AS n
        FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd
        GROUP BY 1,2 ORDER BY 1,2""")).mappings().all()
    dq = session.execute(text("""
        SELECT c.value_code AS category, s.value_code AS severity, count(*) FILTER (WHERE i.resolved_at IS NULL) AS open, count(*) AS total
        FROM mdm.party_dq_issue i JOIN rdm.reference_value c ON c.value_sk=i.dq_category_cd JOIN rdm.reference_value s ON s.value_sk=i.severity_cd
        GROUP BY 1,2 ORDER BY 1,2""")).mappings().all()
    batches = session.execute(text("""
        SELECT DISTINCT ON (b.source_system_cd) s.source_system_cd AS source, b.batch_id, b.mode, b.status, b.finished_at,
               b.extracted, b.unchanged_hash, b.dq_passed, b.dq_quarantined, b.xref_hits, b.loaded, b.unknown_codes
        FROM staging.load_batch b JOIN rdm.source_system s ON s.source_system_sk=b.source_system_cd
        ORDER BY b.source_system_cd, b.batch_id DESC""")).mappings().all()
    matches = session.execute(text("""
        SELECT d.value_code AS decision, m.match_status, count(*) AS n FROM mdm.party_match m
        JOIN rdm.reference_value d ON d.value_sk=m.decision_cd GROUP BY 1,2 ORDER BY 1,2""")).mappings().all()
    return {"parties": [dict(r) for r in parties], "dq_issues": [dict(r) for r in dq], "last_batches": [dict(r) for r in batches],
            "matches": [dict(r) for r in matches],
            "contact_points": session.execute(text("SELECT count(*) FROM mdm.contact_point")).scalar_one(),
            "audit_rows": session.execute(text("SELECT count(*) FROM mdm.party_audit_log")).scalar_one()}
