"""Vistas de arquitectura para la consola: el modelo relacional del MDM (tablas, columnas, claves foráneas y
volúmenes leídos del catálogo de PostgreSQL) y los buckets de bloqueo del matching (SPEC §8.1): cómo cada
registro nuevo, masivo o transaccional, cae en bloques por documento, correo, celular, Soundex del apellido,
NIT o tokens de la razón social, y solo se compara con quienes comparten un bloque."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.matching.features import blocking_keys, load_features

router = APIRouter(tags=["modelo"])

# Capa del modelo (SPEC §5.2) por tabla; staging y rdm se muestran como capas de apoyo
LAYER_OF = {
    "xref_party_source": "sources",
    "party": "core", "party_person": "core", "party_org": "core",
    "party_identifier": "identity", "party_name": "identity",
    "party_role": "roles", "party_relationship": "roles", "party_group": "roles", "party_group_member": "roles", "party_segment": "roles", "party_service_enrollment": "roles",
    "contact_point": "contact", "party_contact_point": "contact", "party_contact_pref": "contact", "party_address": "contact", "party_contact_eligibility_cache": "contact",
    "party_dq_issue": "governance", "party_audit_log": "governance", "party_data_retention": "governance",
    "party_match": "golden", "party_bucket": "golden", "bucket_candidate": "golden", "match_rule": "golden", "match_policy": "golden", "match_review_task": "golden",
    "party_merge_history": "golden", "party_survivorship": "golden",
    "party_consent": "consents", "data_subject_request": "consents",
}


@router.get("/model/erd", summary="Modelo relacional (mdm + staging) desde el catálogo: tablas por capa, columnas, PK/FK y filas")
def erd(session: Session = Depends(get_session)):
    cols = session.execute(text("""
        SELECT c.table_schema, c.table_name, c.column_name, c.data_type, c.is_nullable = 'NO' AS not_null, c.ordinal_position
        FROM information_schema.columns c WHERE c.table_schema IN ('mdm', 'staging') ORDER BY c.table_schema, c.table_name, c.ordinal_position""")).all()
    pks = session.execute(text("""
        SELECT tc.table_schema, tc.table_name, kcu.column_name FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema IN ('mdm', 'staging')""")).all()
    fks = session.execute(text("""
        SELECT tc.table_schema, tc.table_name, kcu.column_name, ccu.table_schema AS ref_schema, ccu.table_name AS ref_table, ccu.column_name AS ref_column, tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
        JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.constraint_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema IN ('mdm', 'staging') ORDER BY 1, 2, 3""")).all()
    pkset = {(s, t, c) for s, t, c in pks}
    fkmap = {(s, t, c): f"{rs}.{rt}" for s, t, c, rs, rt, _, _ in fks}
    tables: dict[str, dict] = {}
    for s, t, c, dt, nn, _ in cols:
        key = f"{s}.{t}"
        tb = tables.setdefault(key, {"schema": s, "name": t, "layer": LAYER_OF.get(t, "staging" if s == "staging" else "other"), "columns": [], "rows": 0})
        tb["columns"].append({"name": c, "type": dt, "not_null": bool(nn), "pk": (s, t, c) in pkset, "fk": fkmap.get((s, t, c))})
    for key, tb in tables.items():
        tb["rows"] = session.execute(text(f"SELECT count(*) FROM {key}")).scalar_one()
    # FK hacia el RDM se resumen (43 catálogos): cuántas columnas *_cd apuntan a rdm.reference_value o rdm.source_system
    edges = [{"from": f"{s}.{t}", "column": c, "to": f"{rs}.{rt}", "to_column": rc} for s, t, c, rs, rt, rc, _ in fks]
    return {"tables": sorted(tables.values(), key=lambda x: (x["schema"], x["name"])), "fks": edges,
            "layers": ["sources", "core", "identity", "roles", "contact", "governance", "golden", "consents", "staging"]}


@router.get("/matching/buckets", summary="Buckets de bloqueo (§8.1): tamaño y candidatos por estrategia, distribución y los más poblados")
def buckets(batch_id: int | None = None, session: Session = Depends(get_session)):
    where = "WHERE b.batch_id = :b" if batch_id else ""
    params = {"b": batch_id} if batch_id else {}
    per = session.execute(text(f"""
        WITH sz AS (SELECT b.bucket_sk, s.value_code AS strategy, t.value_code AS party_type, b.blocking_key, b.batch_id,
                           (SELECT count(*) FROM mdm.bucket_candidate c WHERE c.bucket_sk=b.bucket_sk) AS members
                    FROM mdm.party_bucket b JOIN rdm.reference_value s ON s.value_sk=b.blocking_strategy_cd JOIN rdm.reference_value t ON t.value_sk=b.party_type_cd {where})
        SELECT strategy, party_type, count(*) AS buckets, sum(members) AS candidates, round(avg(members), 2) AS avg_size, max(members) AS max_size,
               count(*) FILTER (WHERE members = 2) AS size_2, count(*) FILTER (WHERE members BETWEEN 3 AND 5) AS size_3_5, count(*) FILTER (WHERE members > 5) AS size_6_plus
        FROM sz GROUP BY 1, 2 ORDER BY 2, 1"""), params).mappings().all()
    top = session.execute(text(f"""
        SELECT b.bucket_sk, s.value_code AS strategy, t.value_code AS party_type, b.blocking_key, b.batch_id, b.created_at,
               (SELECT count(*) FROM mdm.bucket_candidate c WHERE c.bucket_sk=b.bucket_sk) AS members
        FROM mdm.party_bucket b JOIN rdm.reference_value s ON s.value_sk=b.blocking_strategy_cd JOIN rdm.reference_value t ON t.value_sk=b.party_type_cd {where}
        ORDER BY members DESC, b.bucket_sk LIMIT 12"""), params).mappings().all()
    strategies = session.execute(text("SELECT value_code, value_name FROM rdm.vw_rdm_lookup WHERE catalog_code='CAT_BLOCKING_STRATEGY' AND value_code NOT IN ('UNKNOWN','NOT_APPLICABLE') ORDER BY 1")).all()
    totals = session.execute(text(f"SELECT count(*) AS buckets, (SELECT count(*) FROM mdm.bucket_candidate c JOIN mdm.party_bucket b2 ON b2.bucket_sk=c.bucket_sk {where.replace('b.', 'b2.')}) AS candidates FROM mdm.party_bucket b {where}"), params).mappings().one()
    return {"batch_id": batch_id, "totals": dict(totals), "per_strategy": [dict(r) for r in per], "top": [dict(r) for r in top],
            "strategies": [{"code": c, "name": n} for c, n in strategies]}


@router.get("/matching/buckets/party/{party_sk}", summary="Claves de bloqueo de un party y con quién comparte cada bucket (a quién se compararía un registro igual)")
def party_buckets(party_sk: int, limit: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)):
    mine = load_features(session, [party_sk], any_status=True).get(party_sk)
    if not mine:
        raise HTTPException(404, f"party {party_sk} no existe")
    universe = load_features(session)   # GOLDEN + CANDIDATE: contra quién se compara un registro nuevo
    index: dict[tuple[str, str], list[int]] = {}
    for sk, f in universe.items():
        if f["party_type"] != mine["party_type"] or sk == party_sk:
            continue
        for key in blocking_keys(f):
            index.setdefault(key, []).append(sk)
    out = []
    for strategy, key in blocking_keys(mine):
        members = index.get((strategy, key), [])
        out.append({"strategy": strategy, "key": key, "others": len(members),
                    "sample": [{"party_sk": m, "display_name": universe[m].get("full_name_normalized") or universe[m].get("legal_name_normalized"), "golden_status": universe[m]["golden_status"]} for m in members[:limit]]})
    compared = {m for k in out for m in index.get((k["strategy"], k["key"]), [])}
    return {"party_sk": party_sk, "party_type": mine["party_type"], "golden_status": mine["golden_status"], "display_name": mine.get("full_name_normalized") or mine.get("legal_name_normalized"),
            "keys": out, "would_compare_with": len(compared), "universe": len(universe)}
