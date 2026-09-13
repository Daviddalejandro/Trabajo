"""Endpoints de operación del pipeline (SPEC §11): ejecución por fuente, rehomologación y estadísticas."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
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
