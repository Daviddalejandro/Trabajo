"""Consultas RDM para la API y el pipeline (SPEC §5.1, §11). Toda resolución externa
usa CATALOG_CODE + VALUE_CODE, nunca SKs (regla dura §3.4)."""
from sqlalchemy import text
from sqlalchemy.orm import Session

TECHNICAL_MEMBERS = [
    {"value_sk": 0, "value_code": "UNKNOWN", "value_name": "Desconocido / sin homologar", "parent_value_code": None,
     "is_active": True, "technical": True, "attributes": {}},
    {"value_sk": -1, "value_code": "NOT_APPLICABLE", "value_name": "No aplica", "parent_value_code": None,
     "is_active": True, "technical": True, "attributes": {}},
]


def set_actor(session: Session, actor: str) -> None:
    session.execute(text("SELECT set_config('app.actor', :a, true)"), {"a": actor})


def list_domains(session: Session) -> list[dict]:
    rows = session.execute(text("""
        SELECT d.domain_code, d.domain_name, count(c.catalog_sk) AS catalogs
        FROM rdm.domain d LEFT JOIN rdm.catalog c ON c.domain_sk = d.domain_sk
        GROUP BY d.domain_sk ORDER BY d.domain_code""")).mappings().all()
    return [dict(r) for r in rows]


def list_catalogs(session: Session, domain: str | None = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT c.catalog_code, c.catalog_name, d.domain_code, c.official_source, c.is_hierarchical,
               count(v.value_sk) FILTER (WHERE v.is_active) AS active_values,
               count(v.value_sk) FILTER (WHERE NOT v.is_active) AS deprecated_values
        FROM rdm.catalog c JOIN rdm.domain d ON d.domain_sk = c.domain_sk
        LEFT JOIN rdm.reference_value v ON v.catalog_sk = c.catalog_sk
        WHERE (CAST(:domain AS TEXT) IS NULL OR d.domain_code = :domain)
        GROUP BY c.catalog_sk, d.domain_code ORDER BY d.domain_code, c.catalog_code"""),
        {"domain": domain}).mappings().all()
    return [dict(r) for r in rows]


def get_catalog(session: Session, code: str) -> dict | None:
    r = session.execute(text(
        "SELECT c.catalog_sk, c.catalog_code, c.catalog_name, d.domain_code, c.official_source, c.is_hierarchical "
        "FROM rdm.catalog c JOIN rdm.domain d ON d.domain_sk=c.domain_sk WHERE c.catalog_code=:c"),
        {"c": code}).mappings().first()
    return dict(r) if r else None


def list_values(session: Session, catalog_code: str, include_inactive: bool = False,
                limit: int = 200, cursor: int = 0) -> tuple[list[dict], int | None]:
    """Paginación por value_sk (cursor). Los miembros técnicos 0/-1 se anteponen en la
    primera página porque aplican a todo catálogo (regla dura §3.3)."""
    rows = session.execute(text("""
        SELECT l.value_sk, l.value_code, l.value_name, l.parent_value_code, l.is_active,
               l.valid_from, l.valid_to,
               COALESCE((SELECT jsonb_object_agg(f.field_code, f.field_value)
                         FROM rdm.reference_field_value f WHERE f.value_sk = l.value_sk), '{}'::jsonb) AS attributes
        FROM rdm.vw_rdm_lookup l
        WHERE l.catalog_code = :c AND l.value_sk > :cursor AND (:inc OR l.is_active)
        ORDER BY l.value_sk LIMIT :lim"""),
        {"c": catalog_code, "cursor": cursor, "inc": include_inactive, "lim": limit + 1}).mappings().all()
    items = [dict(r) | {"technical": False} for r in rows[:limit]]
    next_cursor = items[-1]["value_sk"] if len(rows) > limit else None
    if cursor == 0:
        items = TECHNICAL_MEMBERS + items
    return items, next_cursor


def create_value(session: Session, catalog_code: str, value_code: str, value_name: str,
                 parent_value_code: str | None, attributes: dict[str, str] | None, actor: str) -> dict:
    set_actor(session, actor)
    cat = get_catalog(session, catalog_code)
    if cat is None:
        raise LookupError(f"Catálogo {catalog_code} no existe")
    parent_sk = None
    if parent_value_code:
        parent_sk = session.execute(text(
            "SELECT value_sk FROM rdm.reference_value WHERE catalog_sk=:c AND value_code=:p AND is_active"),
            {"c": cat["catalog_sk"], "p": parent_value_code}).scalar()
        if parent_sk is None:
            raise LookupError(f"Padre {parent_value_code} no existe o está deprecado en {catalog_code}")
    exists = session.execute(text(
        "SELECT value_sk FROM rdm.reference_value WHERE catalog_sk=:c AND value_code=:v"),
        {"c": cat["catalog_sk"], "v": value_code}).scalar()
    if exists:
        raise ValueError(f"El código {value_code} ya fue publicado en {catalog_code}; los códigos no se reciclan (regla dura 3.7)")
    vsk = session.execute(text(
        "INSERT INTO rdm.reference_value(catalog_sk, value_code, value_name, parent_value_sk) "
        "VALUES (:c, :v, :n, :p) RETURNING value_sk"),
        {"c": cat["catalog_sk"], "v": value_code, "n": value_name, "p": parent_sk}).scalar_one()
    for k, val in (attributes or {}).items():
        session.execute(text(
            "INSERT INTO rdm.reference_field_value(value_sk, field_code, field_value) VALUES (:v, :f, :x)"),
            {"v": vsk, "f": k, "x": str(val)})
    return {"value_sk": vsk, "catalog_code": catalog_code, "value_code": value_code, "value_name": value_name,
            "parent_value_code": parent_value_code, "attributes": attributes or {}, "is_active": True}


def deprecate_value(session: Session, catalog_code: str, value_code: str, actor: str) -> dict:
    set_actor(session, actor)
    row = session.execute(text("""
        UPDATE rdm.reference_value v SET is_active = FALSE, valid_to = now()
        FROM rdm.catalog c
        WHERE c.catalog_sk = v.catalog_sk AND c.catalog_code = :c AND v.value_code = :v AND v.is_active
        RETURNING v.value_sk, v.value_code, v.valid_to"""), {"c": catalog_code, "v": value_code}).mappings().first()
    if row is None:
        raise LookupError(f"{catalog_code}.{value_code} no existe o ya está deprecado")
    return dict(row) | {"is_active": False}


def homologate(session: Session, system: str, field: str, value: str) -> dict | None:
    r = session.execute(text("""
        SELECT source_system_cd, source_field, source_value, domain_code, catalog_code,
               value_sk, value_code, value_name
        FROM rdm.vw_rdm_source_to_canonical
        WHERE source_system_cd = :s AND source_field = :f AND source_value = :v"""),
        {"s": system, "f": field, "v": value}).mappings().first()
    return dict(r) if r else None


def crosswalk(session: Session, from_system: str, field: str, value: str, to_system: str | None = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT catalog_code, value_code, from_system_cd, from_field, from_value, to_system_cd, to_field, to_value
        FROM rdm.vw_rdm_crosswalk
        WHERE from_system_cd = :s AND from_field = :f AND from_value = :v
          AND (CAST(:t AS TEXT) IS NULL OR to_system_cd = :t)
        ORDER BY to_system_cd, to_field"""), {"s": from_system, "f": field, "v": value, "t": to_system}).mappings().all()
    return [dict(r) for r in rows]


def list_mappings(session: Session, system: str | None = None, catalog: str | None = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT source_system_cd, source_field, source_value, catalog_code, value_code, value_name, valid_from
        FROM rdm.vw_rdm_source_to_canonical
        WHERE (CAST(:s AS TEXT) IS NULL OR source_system_cd = :s) AND (CAST(:c AS TEXT) IS NULL OR catalog_code = :c)
        ORDER BY source_system_cd, source_field, source_value"""), {"s": system, "c": catalog}).mappings().all()
    return [dict(r) for r in rows]


def list_source_systems(session: Session) -> list[dict]:
    rows = session.execute(text(
        "SELECT source_system_cd, name, is_prototype_active, data_owner, data_steward "
        "FROM rdm.source_system ORDER BY source_system_cd")).mappings().all()
    return [dict(r) for r in rows]


def audit_tail(session: Session, entity: str | None = None, limit: int = 50) -> list[dict]:
    rows = session.execute(text("""
        SELECT audit_sk, entity, entity_sk, action, actor, occurred_at
        FROM rdm.rdm_audit_log WHERE (CAST(:e AS TEXT) IS NULL OR entity = :e)
        ORDER BY audit_sk DESC LIMIT :l"""), {"e": entity, "l": limit}).mappings().all()
    return [dict(r) for r in rows]
