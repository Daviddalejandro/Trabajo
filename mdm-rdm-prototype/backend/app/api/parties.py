"""Consulta de parties (SPEC §11): búsqueda, golden por capas, fuentes, relaciones, servicios y auditoría."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session

router = APIRouter(prefix="/parties", tags=["parties"])


def rows(session: Session, sql: str, **p) -> list[dict]:
    return [dict(r) for r in session.execute(text(sql), p).mappings().all()]


RELATIONSHIPS_SQL = """
    SELECT CASE WHEN r.from_party_sk=:p THEN 'OUT' ELSE 'IN' END AS direction, rt.value_code AS relationship_type, r.from_party_sk, r.to_party_sk,
           CASE WHEN r.from_party_sk=:p THEN r.to_party_sk ELSE r.from_party_sk END AS other_party_sk,
           COALESCE(op.full_name_normalized, oo.legal_name_normalized) AS other_display_name, ot.value_code AS other_party_type,
           r.valid_from, r.valid_to, s.source_system_cd, r.captured_at
    FROM mdm.party_relationship r JOIN rdm.reference_value rt ON rt.value_sk=r.relationship_type_cd JOIN rdm.source_system s ON s.source_system_sk=r.source_system_cd
    JOIN mdm.party o ON o.party_sk = CASE WHEN r.from_party_sk=:p THEN r.to_party_sk ELSE r.from_party_sk END
    JOIN rdm.reference_value ot ON ot.value_sk=o.party_type_cd
    LEFT JOIN mdm.party_person op ON op.party_sk=o.party_sk LEFT JOIN mdm.party_org oo ON oo.party_sk=o.party_sk
    WHERE r.from_party_sk=:p OR r.to_party_sk=:p ORDER BY r.relationship_sk"""

SERVICES_SQL = """
    SELECT e.enrollment_sk, bu.value_code AS business_unit, sv.value_code AS service, sv.value_name AS service_name, es.value_code AS status,
           e.enrolled_at, e.closed_at, e.source_reference, s.source_system_cd, e.captured_at
    FROM mdm.party_service_enrollment e JOIN rdm.reference_value bu ON bu.value_sk=e.business_unit_cd JOIN rdm.reference_value sv ON sv.value_sk=e.service_cd
    JOIN rdm.reference_value es ON es.value_sk=e.enrollment_status_cd JOIN rdm.source_system s ON s.source_system_sk=e.source_system_cd
    WHERE e.party_sk=:p AND (CAST(:st AS TEXT) IS NULL OR es.value_code=:st) ORDER BY e.enrollment_sk"""


@router.get("", summary="Búsqueda de parties (nombre normalizado, documento, email, ID externo)")
def search(q: str | None = None, role: str | None = None, segment: str | None = None, service: str | None = None,
           status: str | None = None, external_id: str | None = None, limit: int = Query(50, ge=1, le=500), cursor: int = Query(0, ge=0),
           session: Session = Depends(get_session)):
    data = rows(session, """
        SELECT p.party_sk, t.value_code AS party_type, g.value_code AS golden_status, st.value_code AS party_status, p.golden_version,
               p.completeness_score, COALESCE(pp.full_name_normalized, po.legal_name_normalized) AS display_name
        FROM mdm.party p
        JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd
        JOIN rdm.reference_value st ON st.value_sk=p.party_status_cd
        LEFT JOIN mdm.party_person pp ON pp.party_sk=p.party_sk LEFT JOIN mdm.party_org po ON po.party_sk=p.party_sk
        WHERE p.party_sk > :cursor
          AND (CAST(:q AS TEXT) IS NULL OR pp.full_name_normalized ILIKE '%' || :q || '%' OR po.legal_name_normalized ILIKE '%' || :q || '%'
               OR EXISTS (SELECT 1 FROM mdm.party_identifier i WHERE i.party_sk=p.party_sk AND i.id_number=:q)
               OR EXISTS (SELECT 1 FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk WHERE l.party_sk=p.party_sk AND c.contact_value=:q))
          AND (CAST(:external_id AS TEXT) IS NULL OR EXISTS (SELECT 1 FROM mdm.xref_party_source x WHERE x.party_sk=p.party_sk AND x.external_id=:external_id))
          AND (CAST(:role AS TEXT) IS NULL OR EXISTS (SELECT 1 FROM mdm.party_role r JOIN rdm.reference_value v ON v.value_sk=r.role_cd WHERE r.party_sk=p.party_sk AND v.value_code=:role))
          AND (CAST(:segment AS TEXT) IS NULL OR EXISTS (SELECT 1 FROM mdm.party_segment sg JOIN rdm.reference_value v ON v.value_sk=sg.segment_cd WHERE sg.party_sk=p.party_sk AND sg.valid_to IS NULL AND v.value_code=:segment))
          AND (CAST(:service AS TEXT) IS NULL OR EXISTS (SELECT 1 FROM mdm.party_service_enrollment e JOIN rdm.reference_value v ON v.value_sk=e.service_cd WHERE e.party_sk=p.party_sk AND v.value_code=:service))
          AND (CAST(:status AS TEXT) IS NULL OR g.value_code=:status OR st.value_code=:status)
        ORDER BY p.party_sk LIMIT :lim""", q=q, role=role, segment=segment, service=service, status=status, external_id=external_id,
                cursor=cursor, lim=limit + 1)
    return {"items": data[:limit], "next_cursor": data[limit - 1]["party_sk"] if len(data) > limit else None}


@router.get("/{party_sk}/golden", summary="Vista 360: las 8 capas del golden record")
def golden(party_sk: int, session: Session = Depends(get_session)):
    core = rows(session, """
        SELECT p.party_sk, t.value_code AS party_type, g.value_code AS golden_status, st.value_code AS party_status, p.golden_version,
               p.completeness_score, p.created_at, p.updated_at,
               pp.first_name, pp.middle_name, pp.first_surname, pp.second_surname, pp.birth_date, pp.death_date, ge.value_code AS gender,
               po.legal_name, po.trade_name, ci.value_code AS ciiu, ot.value_code AS org_type
        FROM mdm.party p JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd
        JOIN rdm.reference_value st ON st.value_sk=p.party_status_cd
        LEFT JOIN mdm.party_person pp ON pp.party_sk=p.party_sk LEFT JOIN rdm.reference_value ge ON ge.value_sk=pp.gender_cd
        LEFT JOIN mdm.party_org po ON po.party_sk=p.party_sk LEFT JOIN rdm.reference_value ci ON ci.value_sk=po.ciiu_cd LEFT JOIN rdm.reference_value ot ON ot.value_sk=po.org_type_cd
        WHERE p.party_sk=:p""", p=party_sk)
    if not core:
        raise HTTPException(404, "Party no existe")
    L = lambda sql: rows(session, sql, p=party_sk)  # noqa: E731
    return {
        "core": core[0],
        "sources": L("SELECT s.source_system_cd, x.external_id, x.first_seen_at, x.last_seen_at FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd WHERE x.party_sk=:p ORDER BY 1"),
        "identity": {
            "identifiers": L("SELECT t.value_code AS id_type, i.id_number, vs.value_code AS verification_source, i.is_verified, i.is_golden, s.source_system_cd, i.captured_at FROM mdm.party_identifier i JOIN rdm.reference_value t ON t.value_sk=i.id_type_cd JOIN rdm.reference_value vs ON vs.value_sk=i.verification_source_cd JOIN rdm.source_system s ON s.source_system_sk=i.source_system_cd WHERE i.party_sk=:p"),
            "names": L("SELECT t.value_code AS name_type, n.name_value, s.source_system_cd FROM mdm.party_name n JOIN rdm.reference_value t ON t.value_sk=n.name_type_cd JOIN rdm.source_system s ON s.source_system_sk=n.source_system_cd WHERE n.party_sk=:p")},
        "roles_relationships": {
            "roles": L("SELECT r.party_role_sk, ro.value_code AS role, sr.value_code AS sub_role, bu.value_code AS business_unit, r.valid_from, r.valid_to, s.source_system_cd FROM mdm.party_role r JOIN rdm.reference_value ro ON ro.value_sk=r.role_cd JOIN rdm.reference_value sr ON sr.value_sk=r.sub_role_cd JOIN rdm.reference_value bu ON bu.value_sk=r.business_unit_cd JOIN rdm.source_system s ON s.source_system_sk=r.source_system_cd WHERE r.party_sk=:p ORDER BY r.party_role_sk"),
            "segments": L("SELECT st.value_code AS segment_type, sg.value_code AS segment, g.valid_from, g.valid_to, s.source_system_cd FROM mdm.party_segment g JOIN rdm.reference_value st ON st.value_sk=g.segment_type_cd JOIN rdm.reference_value sg ON sg.value_sk=g.segment_cd JOIN rdm.source_system s ON s.source_system_sk=g.source_system_cd WHERE g.party_sk=:p ORDER BY g.party_segment_sk"),
            "services": rows(session, SERVICES_SQL, p=party_sk, st=None),
            "relationships": L(RELATIONSHIPS_SQL),
            "groups": L("SELECT g.group_sk, gt.value_code AS group_type, g.group_name, g.anchor_party_sk, mr.value_code AS member_role FROM mdm.party_group_member m JOIN mdm.party_group g ON g.group_sk=m.group_sk JOIN rdm.reference_value gt ON gt.value_sk=g.group_type_cd JOIN rdm.reference_value mr ON mr.value_sk=m.member_role_cd WHERE m.party_sk=:p")},
        "contactability": {
            "contacts": L("SELECT l.party_contact_sk, ch.value_code AS channel, c.contact_value, c.contact_point_sk, ur.value_code AS usage_role, cf.value_code AS confirmation, og.value_code AS origin, l.is_primary, c.rne_excluded, s.source_system_cd, l.captured_at FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd JOIN rdm.reference_value ur ON ur.value_sk=l.usage_role_cd JOIN rdm.reference_value cf ON cf.value_sk=l.confirmation_status_cd JOIN rdm.reference_value og ON og.value_sk=l.origin_cd JOIN rdm.source_system s ON s.source_system_sk=l.source_system_cd WHERE l.party_sk=:p ORDER BY l.party_contact_sk"),
            "addresses": L("SELECT a.address_line, co.value_code AS country, dv.value_code AS divipola, dv.value_name AS municipality, a.is_primary, s.source_system_cd FROM mdm.party_address a JOIN rdm.reference_value co ON co.value_sk=a.country_cd JOIN rdm.reference_value dv ON dv.value_sk=a.divipola_cd JOIN rdm.source_system s ON s.source_system_sk=a.source_system_cd WHERE a.party_sk=:p"),
            "preferences": L("SELECT pr.pref_sk, ch.value_code AS channel, pr.party_contact_sk, pu.value_code AS purpose, pr.allowed, og.value_code AS origin, pr.valid_to FROM mdm.party_contact_pref pr JOIN rdm.reference_value ch ON ch.value_sk=pr.channel_cd JOIN rdm.reference_value pu ON pu.value_sk=pr.purpose_cd JOIN rdm.reference_value og ON og.value_sk=pr.origin_cd WHERE pr.party_sk=:p AND pr.valid_to IS NULL ORDER BY pr.pref_sk"),
            "eligibility": L("SELECT e.party_contact_sk, pu.value_code AS purpose, e.is_eligible, rs.value_code AS reason, e.computed_at FROM mdm.party_contact_eligibility_cache e JOIN rdm.reference_value pu ON pu.value_sk=e.purpose_cd JOIN rdm.reference_value rs ON rs.value_sk=e.reason_cd WHERE e.party_sk=:p")},
        "governance": {
            "dq_issues": L("SELECT c.value_code AS category, i.field, sv.value_code AS severity, i.detail, i.detected_at, i.resolved_at FROM mdm.party_dq_issue i JOIN rdm.reference_value c ON c.value_sk=i.dq_category_cd JOIN rdm.reference_value sv ON sv.value_sk=i.severity_cd WHERE i.party_sk=:p ORDER BY i.dq_issue_sk"),
            "retention": L("SELECT r.entity, r.entity_sk, rr.value_code AS rule, r.purge_after, r.legal_basis, r.purge_status FROM mdm.party_data_retention r JOIN rdm.reference_value rr ON rr.value_sk=r.retention_rule_cd WHERE r.party_sk=:p")},
        "golden_record": {
            "survivorship": L("SELECT sv.field_name, st.value_code AS strategy, s.source_system_cd AS winning_source, sv.winning_value, sv.decided_at FROM mdm.party_survivorship sv JOIN rdm.reference_value st ON st.value_sk=sv.strategy_cd LEFT JOIN rdm.source_system s ON s.source_system_sk=sv.winning_source_cd WHERE sv.party_sk=:p"),
            "merges": L("SELECT m.merge_sk, m.surviving_party_sk, m.merged_party_sk, mt.value_code AS merge_type, m.justification, m.decided_by, m.merged_at, m.unmerged FROM mdm.party_merge_history m JOIN rdm.reference_value mt ON mt.value_sk=m.merge_type_cd WHERE m.surviving_party_sk=:p OR m.merged_party_sk=:p")},
        "consents": {
            "consents": L("SELECT ct.value_code AS consent_type, cs.value_code AS status, c.granted_at, c.revoked_at, c.evidence_ref, c.granted_by_party_sk, s.source_system_cd FROM mdm.party_consent c JOIN rdm.reference_value ct ON ct.value_sk=c.consent_type_cd JOIN rdm.reference_value cs ON cs.value_sk=c.consent_status_cd JOIN rdm.source_system s ON s.source_system_sk=c.source_system_cd WHERE c.party_sk=:p AND c.valid_to IS NULL"),
            "arco_requests": L("SELECT r.request_sk, at.value_code AS arco_type, rs.value_code AS status, r.requested_at, r.due_at, r.resolved_at FROM mdm.data_subject_request r JOIN rdm.reference_value at ON at.value_sk=r.arco_type_cd JOIN rdm.reference_value rs ON rs.value_sk=r.request_status_cd WHERE r.party_sk=:p")},
    }


@router.get("/{party_sk}/relationships", summary="Relaciones directas e inversas con el otro extremo identificado")
def relationships(party_sk: int, direction: str = Query("both", pattern="^(both|in|out)$"), session: Session = Depends(get_session)):
    data = rows(session, RELATIONSHIPS_SQL, p=party_sk)
    if direction != "both":
        data = [r for r in data if r["direction"] == direction.upper()]
    return data


@router.get("/{party_sk}/services", summary="Vínculos de servicio persistentes con UES")
def services(party_sk: int, status: str | None = None, session: Session = Depends(get_session)):
    return rows(session, SERVICES_SQL, p=party_sk, st=status)


@router.get("/{party_sk}/sources", summary="Fuentes que alimentan el party y linaje por fila")
def sources(party_sk: int, session: Session = Depends(get_session)):
    x = rows(session, "SELECT s.source_system_cd, x.external_id, x.first_seen_at, x.last_seen_at FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd WHERE x.party_sk=:p", p=party_sk)
    if not x:
        raise HTTPException(404, "Party no existe o no tiene XREF")
    lineage = {}
    for t in ["party_role", "party_segment", "party_identifier", "party_name", "party_relationship", "party_service_enrollment", "party_contact_point", "party_address", "party_consent"]:
        col = "from_party_sk" if t == "party_relationship" else "party_sk"
        lineage[t] = rows(session, f"SELECT s.source_system_cd, count(*) AS rows, max(f.captured_at) AS last_captured FROM mdm.{t} f JOIN rdm.source_system s ON s.source_system_sk=f.source_system_cd WHERE f.{col}=:p GROUP BY 1", p=party_sk)
    return {"party_sk": party_sk, "xref": x, "lineage": lineage}


@router.get("/{party_sk}/audit", summary="Trazabilidad del party")
def audit(party_sk: int, merge_sk: int | None = None, arco_request_id: int | None = None, limit: int = Query(200, ge=1, le=2000),
          session: Session = Depends(get_session)):
    return rows(session, """
        SELECT a.audit_sk, a.entity, a.entity_sk, ac.value_code AS action, a.actor, s.source_system_cd, a.batch_id, a.arco_request_id, a.merge_sk, a.occurred_at
        FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd LEFT JOIN rdm.source_system s ON s.source_system_sk=a.source_system_cd
        WHERE a.party_sk=:p AND (CAST(:m AS BIGINT) IS NULL OR a.merge_sk=:m) AND (CAST(:r AS BIGINT) IS NULL OR a.arco_request_id=:r)
        ORDER BY a.audit_sk DESC LIMIT :l""", p=party_sk, m=merge_sk, r=arco_request_id, l=limit)
