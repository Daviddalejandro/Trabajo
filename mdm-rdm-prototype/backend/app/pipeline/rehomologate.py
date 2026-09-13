"""§7.2 · Rehomologación tras cambios en el RDM: los campos que quedaron en 0 = UNKNOWN se
reprocesan sin nueva extracción, el hallazgo se cierra y se audita con acción REHOMOLOGATE."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.pipeline.run import close_batch, open_batch, set_context


def rehomologate(session: Session, catalog: str | None = None, actor: str = "rdm-admin") -> dict:
    rows = session.execute(text("""
        SELECT i.dq_issue_sk, i.party_sk, i.source_system_cd, i.detail, s.source_system_cd AS system_cd
        FROM mdm.party_dq_issue i JOIN rdm.source_system s ON s.source_system_sk = i.source_system_cd
        WHERE i.resolved_at IS NULL AND i.detail ? 'target_table' AND (CAST(:c AS TEXT) IS NULL OR i.detail->>'catalog' = :c)
        ORDER BY i.dq_issue_sk"""), {"c": catalog}).mappings().all()
    result = {"catalog": catalog, "candidates": len(rows), "resolved": 0, "still_unknown": 0, "batches": []}
    by_source: dict[int, list] = {}
    for r in rows:
        by_source.setdefault(r["source_system_cd"], []).append(r)
    for source_sk, items in by_source.items():
        batch_id = open_batch(session, source_sk, "REHOMOLOGATE", actor)
        set_context(session, actor, batch_id, source_sk)
        session.execute(text("SELECT set_config('app.audit_action', 'REHOMOLOGATE', false)"))
        resolved = 0
        for r in items:
            d = r["detail"]
            sk = session.execute(text("""
                SELECT value_sk FROM rdm.vw_rdm_source_to_canonical
                WHERE source_system_cd=:s AND source_field=:f AND source_value=:v AND catalog_code=:c"""),
                {"s": r["system_cd"], "f": d.get("source_field"), "v": d.get("source_value"), "c": d.get("catalog")}).scalar()
            if sk is None:
                result["still_unknown"] += 1
                continue
            session.execute(text(f"UPDATE mdm.{d['target_table']} SET {d['target_column']} = :sk WHERE {d['target_pk']} = :pk"),
                            {"sk": sk, "pk": d["target_sk"]})
            session.execute(text("UPDATE mdm.party_dq_issue SET resolved_at=now(), detail = detail || CAST(:x AS jsonb) WHERE dq_issue_sk=:k"),
                            {"x": '{"resolution": "REHOMOLOGATE"}', "k": r["dq_issue_sk"]})
            resolved += 1
        session.execute(text("SELECT set_config('app.audit_action', '', false)"))
        close_batch(session, batch_id, "OK", {"extracted": len(items), "homologated": resolved, "unknown_codes": len(items) - resolved, "loaded": resolved})
        result["resolved"] += resolved
        result["batches"].append(batch_id)
        set_context(session, actor)
    session.commit()
    return result


def rehomologate_preview(session: Session, catalog: str | None = None) -> dict:
    """§7.2 · Cuántos campos UNKNOWN hay por catálogo y cuántos se corregirían hoy con los mapeos
    vigentes (sin escribir nada). Alimenta el botón "Rehomologar" del Admin RDM (SPEC §12)."""
    rows = session.execute(text("""
        SELECT i.detail->>'catalog' AS catalog, s.source_system_cd AS system_cd, i.detail->>'source_field' AS source_field,
               i.detail->>'source_value' AS source_value, count(*) AS n,
               EXISTS (SELECT 1 FROM rdm.vw_rdm_source_to_canonical v WHERE v.source_system_cd=s.source_system_cd
                       AND v.source_field=i.detail->>'source_field' AND v.source_value=i.detail->>'source_value'
                       AND v.catalog_code=i.detail->>'catalog') AS resolvable
        FROM mdm.party_dq_issue i JOIN rdm.source_system s ON s.source_system_sk = i.source_system_cd
        WHERE i.resolved_at IS NULL AND i.detail ? 'target_table' AND (CAST(:c AS TEXT) IS NULL OR i.detail->>'catalog' = :c)
        GROUP BY 1,2,3,4,6 ORDER BY 1,2,3,4"""), {"c": catalog}).mappings().all()
    items = [dict(r) for r in rows]
    return {"catalog": catalog, "unknown": sum(r["n"] for r in items), "resolvable": sum(r["n"] for r in items if r["resolvable"]),
            "items": items}
