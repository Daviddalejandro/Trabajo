"""Merge y unmerge de parties (SPEC §5.2 capa 7, §3.13).

Merge: snapshot completo de ambos parties (capas 2–5 y 8) en PARTY_MERGE_HISTORY.pre_merge_snapshot,
reapuntamiento de las filas hijas al sobreviviente (las que violan una unicidad se conservan en el
absorbido, nunca se borran), absorbido → MERGED, sobreviviente → GOLDEN, re-survivorship. Todo
audita con `merge_sk` y acción MERGE.

Unmerge: restaura fila por fila desde el snapshot (ambos parties), re-survivorship en ambos, el
match queda resuelto como NO_MATCH y el absorbido vuelve a GOLDEN salvo que comparta documento con
un golden (regla dura §3.16: queda CANDIDATE con hallazgo UNIQUENESS y matching forzado).
"""
from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# (tabla, pk, columnas de party)
CHILD_TABLES = [
    ("xref_party_source", "xref_sk", ["party_sk"]),
    ("party_identifier", "identifier_sk", ["party_sk"]),
    ("party_name", "party_name_sk", ["party_sk"]),
    ("party_role", "party_role_sk", ["party_sk"]),
    ("party_segment", "party_segment_sk", ["party_sk"]),
    ("party_service_enrollment", "enrollment_sk", ["party_sk"]),
    ("party_relationship", "relationship_sk", ["from_party_sk", "to_party_sk"]),
    ("party_group_member", "group_member_sk", ["party_sk"]),
    ("party_contact_point", "party_contact_sk", ["party_sk"]),
    ("party_address", "address_sk", ["party_sk"]),
    ("party_contact_pref", "pref_sk", ["party_sk"]),
    ("party_consent", "consent_sk", ["party_sk"]),
    ("party_dq_issue", "dq_issue_sk", ["party_sk"]),
    ("party_data_retention", "retention_sk", ["party_sk"]),
]
CORE_TABLES = [("party", "party_sk"), ("party_person", "party_sk"), ("party_org", "party_sk")]
# tablas con "vigente por tipo": el absorbido cierra las suyas cuando el sobreviviente ya tiene una vigente
CURRENT_PER_TYPE = {
    "party_segment": ("segment_type_cd", "valid_to", "CURRENT_DATE"),
    "party_consent": ("consent_type_cd", "valid_to", "now()"),
}


def _json(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return float(o)
    return str(o)


def _sk(session: Session, catalog: str, code: str) -> int:
    return session.execute(text("SELECT value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code=:c AND value_code=:v"), {"c": catalog, "v": code}).scalar_one()


def _set(session: Session, name: str, value) -> None:
    session.execute(text("SELECT set_config(:n, :v, false)"), {"n": name, "v": "" if value is None else str(value)})


def snapshot(session: Session, party_sk: int) -> dict:
    snap: dict = {"party_sk": party_sk, "tables": {}}
    for table, pk in CORE_TABLES:
        row = session.execute(text(f"SELECT to_jsonb(t) FROM mdm.{table} t WHERE {pk}=:p"), {"p": party_sk}).scalar()
        if row:
            snap["tables"][table] = [row]
    for table, pk, cols in CHILD_TABLES:
        cond = " OR ".join(f"{c}=:p" for c in cols)
        rows = session.execute(text(f"SELECT to_jsonb(t) FROM mdm.{table} t WHERE {cond} ORDER BY {pk}"), {"p": party_sk}).scalars().all()
        if rows:
            snap["tables"][table] = rows
    return snap


def _column_types(session: Session, table: str) -> dict[str, str]:
    rows = session.execute(text("SELECT column_name, udt_name FROM information_schema.columns WHERE table_schema='mdm' AND table_name=:t"), {"t": table}).all()
    return {c: ("timestamptz" if u == "timestamptz" else u) for c, u in rows}


def restore_rows(session: Session, table: str, pk: str, rows: list[dict]) -> int:
    """Restaura columnas completas desde el snapshot (CAST por tipo de columna)."""
    types = _column_types(session, table)
    n = 0
    for row in rows:
        sets = ", ".join(f"{c} = CAST(:{c} AS {types[c]})" for c in row if c != pk and c in types)
        params = {c: (json.dumps(v) if isinstance(v, (dict, list)) else v) for c, v in row.items()}
        n += session.execute(text(f"UPDATE mdm.{table} SET {sets} WHERE {pk} = :{pk}"), params).rowcount
    return n


def merge_parties(session: Session, surviving: int, merged: int, match_sk: int | None, merge_type: str,
                  decided_by: str, justification: str | None) -> int:
    if surviving == merged:
        raise ValueError("Un party no puede fusionarse consigo mismo")
    st = {r[0]: (r[1], r[2]) for r in session.execute(text(
        "SELECT p.party_sk, g.value_code, t.value_code FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd "
        "JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd WHERE p.party_sk IN (:a, :b)"), {"a": surviving, "b": merged}).all()}
    if len(st) != 2:
        raise LookupError("Party inexistente")
    if st[surviving][1] != st[merged][1]:
        raise ValueError("Nunca se fusiona PERSON con ORGANIZATION (regla dura 3.17)")
    if "MERGED" in (st[surviving][0], st[merged][0]):
        raise ValueError("Uno de los parties ya está absorbido (MERGED)")
    snap = {"surviving": snapshot(session, surviving), "merged": snapshot(session, merged)}
    merge_sk = session.execute(text("""
        INSERT INTO mdm.party_merge_history (surviving_party_sk, merged_party_sk, merge_type_cd, match_sk, justification, decided_by, pre_merge_snapshot)
        VALUES (:s, :m, :t, :k, :j, :d, CAST(:snap AS jsonb)) RETURNING merge_sk"""),
        {"s": surviving, "m": merged, "t": _sk(session, "CAT_MERGE_TYPE", merge_type), "k": match_sk, "j": justification, "d": decided_by,
         "snap": json.dumps(snap, default=_json)}).scalar_one()
    _set(session, "app.merge_sk", merge_sk); _set(session, "app.audit_action", "MERGE")
    if merge_type != "AUTO":   # en AUTO el actor de auditoría es el del pipeline; decided_by conserva al motor
        _set(session, "app.actor", decided_by)
    try:
        for table, pk, cols in CHILD_TABLES:
            if table in CURRENT_PER_TYPE:
                type_col, close_col, now_expr = CURRENT_PER_TYPE[table]
                session.execute(text(f"""UPDATE mdm.{table} m SET {close_col} = {now_expr} WHERE m.party_sk = :m AND m.{close_col} IS NULL
                    AND EXISTS (SELECT 1 FROM mdm.{table} s WHERE s.party_sk = :s AND s.{type_col} = m.{type_col} AND s.{close_col} IS NULL)"""),
                                {"m": merged, "s": surviving})
            if table == "party_contact_pref":   # preferencias de canal duplicadas: el sobreviviente conserva las suyas
                session.execute(text("""UPDATE mdm.party_contact_pref m SET valid_to = now() WHERE m.party_sk = :m AND m.valid_to IS NULL AND m.party_contact_sk IS NULL
                    AND EXISTS (SELECT 1 FROM mdm.party_contact_pref s WHERE s.party_sk = :s AND s.valid_to IS NULL AND s.party_contact_sk IS NULL
                                AND s.channel_cd = m.channel_cd AND s.purpose_cd = m.purpose_cd)"""), {"m": merged, "s": surviving})
            for row in snap["merged"]["tables"].get(table, []):
                sets = ", ".join(f"{c} = CASE WHEN {c} = :m THEN :s ELSE {c} END" for c in cols)
                if table == "party_relationship" and {row["from_party_sk"], row["to_party_sk"]} == {merged, surviving}:
                    continue   # relación entre los dos parties: se conserva en el absorbido, no se vuelve reflexiva
                try:
                    with session.begin_nested():   # el savepoint se revierte solo si falla
                        session.execute(text(f"UPDATE mdm.{table} SET {sets} WHERE {pk} = :pk"), {"m": merged, "s": surviving, "pk": row[pk]})
                except IntegrityError:
                    pass   # viola una unicidad: la fila se conserva en el absorbido (nunca se borra)
        # vínculos de contacto que chocan (mismo punto de contacto en ambos): las preferencias por contacto del
        # absorbido pasan al vínculo equivalente del sobreviviente; el vínculo duplicado se conserva en el absorbido
        dup = session.execute(text("""SELECT ml.party_contact_sk AS m_link, sl.party_contact_sk AS s_link FROM mdm.party_contact_point ml
            JOIN mdm.party_contact_point sl ON sl.contact_point_sk = ml.contact_point_sk AND sl.party_sk = :s WHERE ml.party_sk = :m"""),
                              {"m": merged, "s": surviving}).all()
        for m_link, s_link in dup:
            for pref_sk in session.execute(text("SELECT pref_sk FROM mdm.party_contact_pref WHERE party_contact_sk=:l"), {"l": m_link}).scalars().all():
                try:
                    with session.begin_nested():
                        session.execute(text("UPDATE mdm.party_contact_pref SET party_sk=:s, party_contact_sk=:sl WHERE pref_sk=:k"), {"s": surviving, "sl": s_link, "k": pref_sk})
                except IntegrityError:
                    pass
        session.execute(text("DELETE FROM mdm.party_survivorship WHERE party_sk=:m"), {"m": merged})
        session.execute(text("DELETE FROM mdm.party_contact_eligibility_cache WHERE party_sk=:m"), {"m": merged})
        session.execute(text("UPDATE mdm.party SET golden_status_cd=:g, updated_at=now() WHERE party_sk=:m"), {"g": _sk(session, "CAT_GOLDEN_STATUS", "MERGED"), "m": merged})
        session.execute(text("UPDATE mdm.party SET golden_status_cd=:g, updated_at=now() WHERE party_sk=:s"), {"g": _sk(session, "CAT_GOLDEN_STATUS", "GOLDEN"), "s": surviving})
        if match_sk:
            session.execute(text("UPDATE mdm.party_match SET match_status='RESOLVED' WHERE match_sk=:k"), {"k": match_sk})
        from app.survivorship.engine import apply_survivorship
        apply_survivorship(session, surviving)
    finally:
        _set(session, "app.merge_sk", None); _set(session, "app.audit_action", None)
    return merge_sk


def unmerge(session: Session, merge_sk: int, actor: str, reason: str) -> dict:
    m = session.execute(text("SELECT surviving_party_sk, merged_party_sk, pre_merge_snapshot, unmerged, match_sk FROM mdm.party_merge_history WHERE merge_sk=:k"),
                        {"k": merge_sk}).first()
    if m is None:
        raise LookupError("Merge inexistente")
    if m.unmerged:
        raise ValueError("Este merge ya fue revertido")
    surviving, merged, snap = m.surviving_party_sk, m.merged_party_sk, m.pre_merge_snapshot
    _set(session, "app.merge_sk", merge_sk); _set(session, "app.audit_action", "UNMERGE"); _set(session, "app.actor", actor)
    restored = 0
    try:
        # 1) devolver al absorbido las filas que hoy apuntan al sobreviviente y que en el snapshot eran suyas, y restaurar columnas
        for side in ("merged", "surviving"):
            tables = snap[side]["tables"]
            for table, pk, _cols in CHILD_TABLES:
                restored += restore_rows(session, table, pk, tables.get(table, []))
            for table, pk in CORE_TABLES:
                restore_rows(session, table, pk, tables.get(table, []))
        session.execute(text("DELETE FROM mdm.party_survivorship WHERE party_sk IN (:a, :b)"), {"a": surviving, "b": merged})
        session.execute(text("DELETE FROM mdm.party_contact_eligibility_cache WHERE party_sk IN (:a, :b)"), {"a": surviving, "b": merged})
        session.execute(text("UPDATE mdm.party_merge_history SET unmerged=TRUE, unmerged_by=:u, unmerged_at=now(), unmerge_reason=:r WHERE merge_sk=:k"),
                        {"u": actor, "r": reason, "k": merge_sk})
        if m.match_sk:
            session.execute(text("UPDATE mdm.party_match SET match_status='RESOLVED', decision_cd=:d WHERE match_sk=:k"),
                            {"d": _sk(session, "CAT_MATCH_DECISION", "NO_MATCH"), "k": m.match_sk})
        # 2) estados: sobreviviente GOLDEN; absorbido GOLDEN salvo conflicto de documento con otro golden (regla dura 3.16)
        golden = _sk(session, "CAT_GOLDEN_STATUS", "GOLDEN")
        session.execute(text("UPDATE mdm.party SET golden_status_cd=:g, updated_at=now() WHERE party_sk=:s"), {"g": golden, "s": surviving})
        status = "GOLDEN"
        try:
            with session.begin_nested():
                session.execute(text("UPDATE mdm.party SET golden_status_cd=:g, updated_at=now() WHERE party_sk=:m"), {"g": golden, "m": merged})
        except IntegrityError:
            status = "CANDIDATE"
            session.execute(text("UPDATE mdm.party SET golden_status_cd=:g, updated_at=now() WHERE party_sk=:m"), {"g": _sk(session, "CAT_GOLDEN_STATUS", "CANDIDATE"), "m": merged})
            session.execute(text("""INSERT INTO mdm.party_dq_issue (staging_ref, party_sk, dq_category_cd, field, detail, severity_cd)
                VALUES ('unmerge', :m, :c, 'identifier', CAST(:d AS jsonb), :s)"""),
                            {"m": merged, "c": _sk(session, "CAT_DQ_CATEGORY", "UNIQUENESS"), "s": _sk(session, "CAT_SEVERITY", "WARNING"),
                             "d": json.dumps({"message": "Tras el unmerge comparte documento con un golden: permanece CANDIDATE con matching forzado (regla dura 3.16)",
                                              "merge_sk": merge_sk, "other_party": surviving})})
        from app.survivorship.engine import apply_survivorship
        apply_survivorship(session, surviving); apply_survivorship(session, merged)
    finally:
        _set(session, "app.merge_sk", None); _set(session, "app.audit_action", None)
    return {"merge_sk": merge_sk, "surviving_party_sk": surviving, "merged_party_sk": merged, "restored_rows": restored, "merged_party_status": status}
