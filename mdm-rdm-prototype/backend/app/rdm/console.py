"""Consola RDM (SPEC §12.2 ampliado): operaciones de las cinco capas del RDM que un usuario de Gobierno de Datos
ejecuta desde la interfaz: dominios, catálogos, campos personalizados (diccionario del EAV), valores, sistemas
fuente, integraciones y homologaciones versionadas. Nunca edita un canónico publicado (regla dura §3.7); toda
escritura queda en RDM_AUDIT_LOG con el actor de la sesión (Ley 1581/2012 art. 17; DAMA-DMBOK2 Cap. 10)."""
import re
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.rdm.service import get_catalog, set_actor

CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,59}$")
DATA_TYPES = ("TEXT", "NUMBER", "BOOLEAN", "DATE", "REGEX", "CODE")


def _code(value: str, what: str) -> str:
    v = (value or "").strip().upper()
    if not CODE_RE.match(v):
        raise ValueError(f"{what}: el código debe ser MAYÚSCULAS, dígitos y guion bajo, de 2 a 60 caracteres (recibido {value!r})")
    return v


# ------------------------------------------------------------------ resumen
def overview(session: Session) -> dict:
    row = session.execute(text("""
        SELECT (SELECT count(*) FROM rdm.domain) AS domains,
               (SELECT count(*) FROM rdm.catalog) AS catalogs,
               (SELECT count(*) FROM rdm.reference_value WHERE value_sk > 0 AND is_active) AS values_active,
               (SELECT count(*) FROM rdm.reference_value WHERE value_sk > 0 AND NOT is_active) AS values_deprecated,
               (SELECT count(*) FROM rdm.catalog_attribute WHERE is_active) AS attributes,
               (SELECT count(*) FROM rdm.reference_field_value) AS attribute_values,
               (SELECT count(*) FROM rdm.source_system) AS source_systems,
               (SELECT count(*) FROM rdm.catalog_source_integration) AS integrations,
               (SELECT count(*) FROM rdm.source_value_mapping WHERE valid_to IS NULL) AS mappings_current,
               (SELECT count(*) FROM rdm.source_value_mapping WHERE valid_to IS NOT NULL) AS mappings_closed,
               (SELECT count(*) FROM rdm.rdm_audit_log) AS audit_entries""")).mappings().one()
    return dict(row)


# ------------------------------------------------------------------ dominios y catálogos
def create_domain(session: Session, code: str, name: str, actor: str) -> dict:
    set_actor(session, actor)
    code = _code(code, "Dominio")
    if session.execute(text("SELECT 1 FROM rdm.domain WHERE domain_code=:c"), {"c": code}).first():
        raise FileExistsError(f"El dominio {code} ya existe")
    sk = session.execute(text("INSERT INTO rdm.domain(domain_code, domain_name) VALUES (:c, :n) RETURNING domain_sk"),
                         {"c": code, "n": name.strip()}).scalar_one()
    return {"domain_sk": sk, "domain_code": code, "domain_name": name.strip(), "catalogs": 0}


def create_catalog(session: Session, code: str, name: str, domain: str, official_source: str | None,
                   is_hierarchical: bool, actor: str) -> dict:
    set_actor(session, actor)
    code = _code(code, "Catálogo")
    if not code.startswith("CAT_"):
        raise ValueError("Catálogo: el código debe empezar por CAT_ (convención SPEC §5.1)")
    dsk = session.execute(text("SELECT domain_sk FROM rdm.domain WHERE domain_code=:d"), {"d": domain}).scalar()
    if dsk is None:
        raise LookupError(f"El dominio {domain} no existe: créelo primero (el RDM se construye de arriba hacia abajo)")
    if get_catalog(session, code):
        raise FileExistsError(f"El catálogo {code} ya existe")
    sk = session.execute(text(
        "INSERT INTO rdm.catalog(domain_sk, catalog_code, catalog_name, official_source, is_hierarchical) "
        "VALUES (:d, :c, :n, :s, :h) RETURNING catalog_sk"),
        {"d": dsk, "c": code, "n": name.strip(), "s": (official_source or "").strip() or None, "h": is_hierarchical}).scalar_one()
    return {"catalog_sk": sk, "catalog_code": code, "catalog_name": name.strip(), "domain_code": domain,
            "official_source": official_source, "is_hierarchical": is_hierarchical, "active_values": 0, "deprecated_values": 0}


def catalog_detail(session: Session, code: str) -> dict | None:
    cat = get_catalog(session, code)
    if cat is None:
        return None
    counts = session.execute(text("""
        SELECT count(*) FILTER (WHERE is_active) AS active_values, count(*) FILTER (WHERE NOT is_active) AS deprecated_values
        FROM rdm.reference_value WHERE catalog_sk=:c"""), {"c": cat["catalog_sk"]}).mappings().one()
    integrations = session.execute(text("""
        SELECT i.integration_sk, s.source_system_cd, s.name AS system_name, i.source_field,
               count(m.mapping_sk) FILTER (WHERE m.valid_to IS NULL) AS mappings_current,
               count(m.mapping_sk) FILTER (WHERE m.valid_to IS NOT NULL) AS mappings_closed
        FROM rdm.catalog_source_integration i
        JOIN rdm.source_system s ON s.source_system_sk = i.source_system_sk
        LEFT JOIN rdm.source_value_mapping m ON m.integration_sk = i.integration_sk
        WHERE i.catalog_sk = :c GROUP BY i.integration_sk, s.source_system_cd, s.name ORDER BY s.source_system_cd, i.source_field"""),
        {"c": cat["catalog_sk"]}).mappings().all()
    return {**cat, **dict(counts), "attributes": list_attributes(session, code), "integrations": [dict(r) for r in integrations]}


# ------------------------------------------------------------------ campos personalizados
def list_attributes(session: Session, catalog_code: str, include_inactive: bool = False) -> list[dict]:
    rows = session.execute(text("""
        SELECT a.attribute_sk, a.field_code, a.field_name, a.data_type, a.is_required, a.description, a.is_active,
               a.valid_from, a.valid_to,
               (SELECT count(*) FROM rdm.reference_field_value f JOIN rdm.reference_value v ON v.value_sk = f.value_sk
                 WHERE v.catalog_sk = a.catalog_sk AND f.field_code = a.field_code) AS values_with_data
        FROM rdm.catalog_attribute a JOIN rdm.catalog c ON c.catalog_sk = a.catalog_sk
        WHERE c.catalog_code = :c AND (:inc OR a.is_active) ORDER BY a.attribute_sk"""),
        {"c": catalog_code, "inc": include_inactive}).mappings().all()
    return [dict(r) for r in rows]


def create_attribute(session: Session, catalog_code: str, field_code: str, field_name: str, data_type: str,
                     is_required: bool, description: str | None, actor: str) -> dict:
    set_actor(session, actor)
    cat = get_catalog(session, catalog_code)
    if cat is None:
        raise LookupError(f"Catálogo {catalog_code} no existe")
    fcode = (field_code or "").strip()
    if not re.match(r"^[a-z][a-z0-9_]{1,59}$", fcode):
        raise ValueError("Campo personalizado: el código va en minúsculas con guion bajo (p. ej. validation_regex)")
    dt = (data_type or "TEXT").upper()
    if dt not in DATA_TYPES:
        raise ValueError(f"Tipo de dato inválido {data_type}; use {', '.join(DATA_TYPES)}")
    if session.execute(text("SELECT 1 FROM rdm.catalog_attribute WHERE catalog_sk=:c AND field_code=:f"),
                       {"c": cat["catalog_sk"], "f": fcode}).first():
        raise FileExistsError(f"El campo {fcode} ya está definido en {catalog_code} (retírelo y cree otro código si cambia de significado)")
    if is_required:
        missing = session.execute(text("""
            SELECT count(*) FROM rdm.reference_value v WHERE v.catalog_sk=:c AND v.is_active
              AND NOT EXISTS (SELECT 1 FROM rdm.reference_field_value f WHERE f.value_sk=v.value_sk AND f.field_code=:f)"""),
            {"c": cat["catalog_sk"], "f": fcode}).scalar_one()
        if missing:
            raise ValueError(f"No se puede exigir {fcode}: {missing} valores activos de {catalog_code} aún no lo tienen; cárguelo primero y luego márquelo obligatorio")
    sk = session.execute(text(
        "INSERT INTO rdm.catalog_attribute(catalog_sk, field_code, field_name, data_type, is_required, description) "
        "VALUES (:c, :f, :n, :t, :r, :d) RETURNING attribute_sk"),
        {"c": cat["catalog_sk"], "f": fcode, "n": field_name.strip(), "t": dt, "r": is_required, "d": (description or "").strip() or None}).scalar_one()
    return {"attribute_sk": sk, "catalog_code": catalog_code, "field_code": fcode, "field_name": field_name.strip(),
            "data_type": dt, "is_required": is_required, "description": description, "is_active": True, "values_with_data": 0}


def retire_attribute(session: Session, catalog_code: str, field_code: str, actor: str) -> dict:
    set_actor(session, actor)
    row = session.execute(text("""
        UPDATE rdm.catalog_attribute a SET is_active = FALSE, valid_to = now(), is_required = FALSE
        FROM rdm.catalog c WHERE c.catalog_sk = a.catalog_sk AND c.catalog_code = :c AND a.field_code = :f AND a.is_active
        RETURNING a.attribute_sk, a.field_code, a.valid_to"""), {"c": catalog_code, "f": field_code}).mappings().first()
    if row is None:
        raise LookupError(f"{catalog_code}.{field_code} no existe o ya está retirado")
    return dict(row) | {"is_active": False}


def _check_type(dt: str, value: str) -> bool:
    if dt == "NUMBER":
        return re.match(r"^-?\d+(\.\d+)?$", value) is not None
    if dt == "BOOLEAN":
        return value in ("true", "false")
    if dt == "DATE":
        try:
            date.fromisoformat(value); return True
        except ValueError:
            return False
    if dt == "REGEX":
        try:
            re.compile(value); return True
        except re.error:
            return False
    if dt == "CODE":
        return re.match(r"^[A-Z][A-Z0-9_]*$", value) is not None
    return True


def validate_attributes(session: Session, catalog_code: str, attributes: dict[str, str], *, for_new_value: bool) -> dict[str, str]:
    """Contrasta los atributos EAV con el diccionario del catálogo: tipo de dato y campos obligatorios (solo al
    crear un valor completo). Campos no definidos se aceptan como TEXT para no bloquear catálogos sin diccionario."""
    defs = {a["field_code"]: a for a in list_attributes(session, catalog_code)}
    out: dict[str, str] = {}
    for k, v in (attributes or {}).items():
        v = str(v).strip()
        if k in defs and not _check_type(defs[k]["data_type"], v):
            raise ValueError(f"El campo {k} es de tipo {defs[k]['data_type']} y recibió {v!r}")
        out[k] = v
    if for_new_value:
        missing = [k for k, a in defs.items() if a["is_required"] and not out.get(k)]
        if missing:
            raise ValueError(f"Faltan campos obligatorios de {catalog_code}: {', '.join(missing)}")
    return out


def set_value_attributes(session: Session, catalog_code: str, value_code: str, attributes: dict[str, str], actor: str) -> dict:
    """Los atributos describen al valor, no lo identifican: se pueden completar o corregir (el código y el nombre no,
    regla dura §3.7). Un valor vacío retira el atributo."""
    set_actor(session, actor)
    cat = get_catalog(session, catalog_code)
    if cat is None:
        raise LookupError(f"Catálogo {catalog_code} no existe")
    vsk = session.execute(text("SELECT value_sk FROM rdm.reference_value WHERE catalog_sk=:c AND value_code=:v"),
                          {"c": cat["catalog_sk"], "v": value_code}).scalar()
    if vsk is None:
        raise LookupError(f"{catalog_code}.{value_code} no existe")
    clean = validate_attributes(session, catalog_code, attributes, for_new_value=False)
    for k, v in clean.items():
        if v == "":
            session.execute(text("DELETE FROM rdm.reference_field_value WHERE value_sk=:v AND field_code=:f"), {"v": vsk, "f": k})
        else:
            session.execute(text("""
                INSERT INTO rdm.reference_field_value(value_sk, field_code, field_value) VALUES (:v, :f, :x)
                ON CONFLICT (value_sk, field_code) DO UPDATE SET field_value = EXCLUDED.field_value
                WHERE rdm.reference_field_value.field_value IS DISTINCT FROM EXCLUDED.field_value"""), {"v": vsk, "f": k, "x": v})
    current = dict(session.execute(text("SELECT field_code, field_value FROM rdm.reference_field_value WHERE value_sk=:v ORDER BY field_code"),
                                   {"v": vsk}).all())
    return {"catalog_code": catalog_code, "value_code": value_code, "value_sk": vsk, "attributes": current}


# ------------------------------------------------------------------ sistemas fuente e integraciones
def create_source_system(session: Session, code: str, name: str, data_owner: str | None, data_steward: str | None,
                         is_prototype_active: bool, actor: str) -> dict:
    set_actor(session, actor)
    code = _code(code, "Sistema fuente")
    if session.execute(text("SELECT 1 FROM rdm.source_system WHERE source_system_cd=:c"), {"c": code}).first():
        raise FileExistsError(f"El sistema fuente {code} ya está registrado")
    sk = session.execute(text(
        "INSERT INTO rdm.source_system(source_system_cd, name, is_prototype_active, data_owner, data_steward) "
        "VALUES (:c, :n, :a, :o, :s) RETURNING source_system_sk"),
        {"c": code, "n": name.strip(), "a": is_prototype_active, "o": (data_owner or "").strip() or None, "s": (data_steward or "").strip() or None}).scalar_one()
    return {"source_system_sk": sk, "source_system_cd": code, "name": name.strip(), "is_prototype_active": is_prototype_active,
            "data_owner": data_owner, "data_steward": data_steward}


def list_integrations(session: Session, catalog: str | None = None, system: str | None = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT i.integration_sk, d.domain_code, c.catalog_code, c.catalog_name, s.source_system_cd, s.name AS system_name, i.source_field,
               count(m.mapping_sk) FILTER (WHERE m.valid_to IS NULL) AS mappings_current,
               count(m.mapping_sk) FILTER (WHERE m.valid_to IS NOT NULL) AS mappings_closed
        FROM rdm.catalog_source_integration i
        JOIN rdm.catalog c ON c.catalog_sk = i.catalog_sk JOIN rdm.domain d ON d.domain_sk = c.domain_sk
        JOIN rdm.source_system s ON s.source_system_sk = i.source_system_sk
        LEFT JOIN rdm.source_value_mapping m ON m.integration_sk = i.integration_sk
        WHERE (CAST(:c AS TEXT) IS NULL OR c.catalog_code = :c) AND (CAST(:s AS TEXT) IS NULL OR s.source_system_cd = :s)
        GROUP BY i.integration_sk, d.domain_code, c.catalog_code, c.catalog_name, s.source_system_cd, s.name
        ORDER BY s.source_system_cd, c.catalog_code, i.source_field"""), {"c": catalog, "s": system}).mappings().all()
    return [dict(r) for r in rows]


def create_integration(session: Session, catalog: str, system: str, source_field: str, actor: str) -> dict:
    """Declara que un campo de un sistema fuente alimenta un catálogo (antes de homologar valor a valor)."""
    set_actor(session, actor)
    cat = get_catalog(session, catalog)
    if cat is None:
        raise LookupError(f"Catálogo {catalog} no existe")
    ssk = session.execute(text("SELECT source_system_sk FROM rdm.source_system WHERE source_system_cd=:s"), {"s": system}).scalar()
    if ssk is None:
        raise LookupError(f"El sistema fuente {system} no está registrado (regla dura §3.4): regístrelo primero")
    field = (source_field or "").strip()
    if not field:
        raise ValueError("Integración: el campo fuente es obligatorio")
    r = session.execute(text(
        "INSERT INTO rdm.catalog_source_integration(catalog_sk, source_system_sk, source_field) VALUES (:c, :s, :f) "
        "ON CONFLICT (catalog_sk, source_system_sk, source_field) DO NOTHING RETURNING integration_sk"),
        {"c": cat["catalog_sk"], "s": ssk, "f": field}).scalar()
    return {"created": r is not None, "catalog_code": catalog, "source_system_cd": system, "source_field": field}


def retire_mapping(session: Session, system: str, field: str, catalog: str, source_value: str, actor: str) -> dict:
    """Cierra la homologación vigente (valid_to = now()); el valor fuente volverá a caer en 0 = UNKNOWN hasta que
    exista otra. Nunca se borra: el histórico explica cómo se homologó cada carga."""
    set_actor(session, actor)
    row = session.execute(text("""
        UPDATE rdm.source_value_mapping m SET valid_to = now()
        FROM rdm.catalog_source_integration i, rdm.source_system s, rdm.catalog c
        WHERE m.integration_sk = i.integration_sk AND i.source_system_sk = s.source_system_sk AND i.catalog_sk = c.catalog_sk
          AND s.source_system_cd = :s AND i.source_field = :f AND c.catalog_code = :c AND m.source_value = :v AND m.valid_to IS NULL
        RETURNING m.mapping_sk, m.valid_to"""), {"s": system, "f": field, "c": catalog, "v": source_value}).mappings().first()
    if row is None:
        raise LookupError(f"No hay homologación vigente para {system}/{field}/{source_value} en {catalog}")
    return dict(row) | {"system": system, "field": field, "catalog": catalog, "source_value": source_value}


def mapping_history(session: Session, system: str, field: str, catalog: str, source_value: str | None = None) -> list[dict]:
    rows = session.execute(text("""
        SELECT m.mapping_sk, m.source_value, v.value_code, v.value_name, v.is_active AS value_active, m.valid_from, m.valid_to
        FROM rdm.source_value_mapping m
        JOIN rdm.catalog_source_integration i ON i.integration_sk = m.integration_sk
        JOIN rdm.source_system s ON s.source_system_sk = i.source_system_sk
        JOIN rdm.catalog c ON c.catalog_sk = i.catalog_sk
        JOIN rdm.reference_value v ON v.value_sk = m.value_sk
        WHERE s.source_system_cd = :s AND i.source_field = :f AND c.catalog_code = :c
          AND (CAST(:v AS TEXT) IS NULL OR m.source_value = :v)
        ORDER BY m.source_value, m.valid_from DESC"""), {"s": system, "f": field, "c": catalog, "v": source_value}).mappings().all()
    return [dict(r) for r in rows]


def audit_detail(session: Session, entity: str | None, limit: int) -> list[dict]:
    rows = session.execute(text("""
        SELECT audit_sk, entity, entity_sk, action, actor, occurred_at, old_value, new_value
        FROM rdm.rdm_audit_log WHERE (CAST(:e AS TEXT) IS NULL OR entity = :e)
        ORDER BY audit_sk DESC LIMIT :l"""), {"e": entity, "l": limit}).mappings().all()
    return [dict(r) for r in rows]
