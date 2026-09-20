"""Siembra idempotente del RDM (SPEC §6). Puede ejecutarse N veces: crea lo que falta y
nunca edita un canónico publicado (regla dura §3.7): si un código existe, se conserva.
"""
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.rdm import seed_data as sd


@dataclass
class SeedReport:
    domains: int = 0
    catalogs: int = 0
    values: int = 0
    attributes: int = 0
    source_systems: int = 0
    integrations: int = 0
    mappings: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _set_actor(session: Session, actor: str) -> None:
    session.execute(text("SELECT set_config('app.actor', :a, true)"), {"a": actor})


def seed_rdm(session: Session, actor: str = "rdm-seed") -> SeedReport:
    rep = SeedReport()
    _set_actor(session, actor)

    # --- Dominios
    for code, name in sd.DOMAINS:
        r = session.execute(
            text("INSERT INTO rdm.domain(domain_code, domain_name) VALUES (:c, :n) "
                 "ON CONFLICT (domain_code) DO NOTHING"), {"c": code, "n": name})
        rep.domains += r.rowcount
    domain_sk = dict(session.execute(text("SELECT domain_code, domain_sk FROM rdm.domain")).all())

    # --- Catálogos y valores
    for cat_code, (domain, name, source, hierarchical, values) in sd.CATALOGS.items():
        r = session.execute(
            text("INSERT INTO rdm.catalog(domain_sk, catalog_code, catalog_name, official_source, is_hierarchical) "
                 "VALUES (:d, :c, :n, :s, :h) ON CONFLICT (catalog_code) DO NOTHING"),
            {"d": domain_sk[domain], "c": cat_code, "n": name, "s": source, "h": hierarchical})
        rep.catalogs += r.rowcount
        cat_sk = session.execute(text("SELECT catalog_sk FROM rdm.catalog WHERE catalog_code=:c"), {"c": cat_code}).scalar_one()
        existing = dict(session.execute(
            text("SELECT value_code, value_sk FROM rdm.reference_value WHERE catalog_sk=:c"), {"c": cat_sk}).all())
        for entry in values:
            code, vname = entry[0], entry[1]
            parent = entry[2] if len(entry) > 2 else None
            eav = entry[3] if len(entry) > 3 else {}
            if code not in existing:
                parent_sk = existing.get(parent) if parent else None
                if parent and parent_sk is None:
                    raise ValueError(f"{cat_code}: el padre {parent} de {code} debe declararse antes")
                vsk = session.execute(
                    text("INSERT INTO rdm.reference_value(catalog_sk, value_code, value_name, parent_value_sk) "
                         "VALUES (:c, :code, :n, :p) RETURNING value_sk"),
                    {"c": cat_sk, "code": code, "n": vname, "p": parent_sk}).scalar_one()
                existing[code] = vsk
                rep.values += 1
            for fcode, fval in eav.items():
                r = session.execute(
                    text("INSERT INTO rdm.reference_field_value(value_sk, field_code, field_value) "
                         "VALUES (:v, :f, :x) ON CONFLICT (value_sk, field_code) DO NOTHING"),
                    {"v": existing[code], "f": fcode, "x": str(fval)})
                rep.attributes += r.rowcount

    # --- Sistemas fuente
    for code, name, active, owner, steward in sd.SOURCE_SYSTEMS:
        r = session.execute(
            text("INSERT INTO rdm.source_system(source_system_cd, name, is_prototype_active, data_owner, data_steward) "
                 "VALUES (:c, :n, :a, :o, :s) ON CONFLICT (source_system_cd) DO NOTHING"),
            {"c": code, "n": name, "a": active, "o": owner, "s": steward})
        rep.source_systems += r.rowcount

    # --- Integraciones y homologaciones
    for system, field, catalog, source_value, canonical in sd.MAPPINGS:
        i_ok, m_ok = add_mapping(session, system, field, catalog, source_value, canonical)
        rep.integrations += i_ok
        rep.mappings += m_ok

    sync_attribute_dictionary(session)
    return rep


def sync_attribute_dictionary(session: Session) -> int:
    """Diccionario de campos personalizados (CATALOG_ATTRIBUTE) a partir del EAV sembrado: un campo por
    (catálogo, field_code) con el tipo inferido de sus valores y el nombre de negocio de ATTRIBUTE_NAMES.
    Idempotente: lo definido desde la consola no se toca."""
    rows = session.execute(text("""
        SELECT c.catalog_sk, f.field_code,
               CASE WHEN bool_and(f.field_value IN ('true', 'false')) THEN 'BOOLEAN'
                    WHEN bool_and(f.field_value ~ '^-?[0-9]+(\\.[0-9]+)?$') THEN 'NUMBER'
                    WHEN f.field_code ILIKE '%regex%' THEN 'REGEX'
                    WHEN bool_and(f.field_value ~ '^[A-Z][A-Z0-9_]*$') THEN 'CODE'
                    ELSE 'TEXT' END AS data_type
        FROM rdm.reference_field_value f
        JOIN rdm.reference_value v ON v.value_sk = f.value_sk
        JOIN rdm.catalog c ON c.catalog_sk = v.catalog_sk
        GROUP BY c.catalog_sk, f.field_code""")).all()
    n = 0
    for cat_sk, field_code, data_type in rows:
        r = session.execute(text(
            "INSERT INTO rdm.catalog_attribute(catalog_sk, field_code, field_name, data_type) VALUES (:c, :f, :n, :t) "
            "ON CONFLICT (catalog_sk, field_code) DO NOTHING"),
            {"c": cat_sk, "f": field_code, "n": sd.ATTRIBUTE_NAMES.get(field_code, field_code), "t": data_type})
        n += r.rowcount
    return n


def add_mapping(session: Session, system: str, field: str, catalog: str,
                source_value: str, canonical: str) -> tuple[int, int]:
    """Alta de homologación fuente→canónico. Devuelve (integraciones creadas, mapeos creados).
    Regla dura §3.4: el sistema debe existir tal cual en SOURCE_SYSTEM."""
    row = session.execute(text("""
        SELECT s.source_system_sk, c.catalog_sk, v.value_sk
        FROM rdm.source_system s, rdm.catalog c
        JOIN rdm.reference_value v ON v.catalog_sk = c.catalog_sk AND v.value_code = :vc AND v.is_active
        WHERE s.source_system_cd = :sys AND c.catalog_code = :cat
    """), {"sys": system, "cat": catalog, "vc": canonical}).first()
    if row is None:
        raise LookupError(f"Homologación inválida: sistema={system} catálogo={catalog} canónico={canonical} "
                          f"(el sistema debe estar registrado y el canónico activo)")
    sys_sk, cat_sk, val_sk = row
    r = session.execute(text(
        "INSERT INTO rdm.catalog_source_integration(catalog_sk, source_system_sk, source_field) "
        "VALUES (:c, :s, :f) ON CONFLICT (catalog_sk, source_system_sk, source_field) DO NOTHING"),
        {"c": cat_sk, "s": sys_sk, "f": field})
    i_created = r.rowcount
    int_sk = session.execute(text(
        "SELECT integration_sk FROM rdm.catalog_source_integration "
        "WHERE catalog_sk=:c AND source_system_sk=:s AND source_field=:f"),
        {"c": cat_sk, "s": sys_sk, "f": field}).scalar_one()
    current = session.execute(text(
        "SELECT mapping_sk, value_sk FROM rdm.source_value_mapping "
        "WHERE integration_sk=:i AND source_value=:v AND valid_to IS NULL"),
        {"i": int_sk, "v": source_value}).first()
    if current and current.value_sk == val_sk:
        return i_created, 0
    if current:  # el mapeo cambia: cerrar el vigente, nunca editarlo
        session.execute(text("UPDATE rdm.source_value_mapping SET valid_to = now() WHERE mapping_sk=:m"),
                        {"m": current.mapping_sk})
    session.execute(text(
        "INSERT INTO rdm.source_value_mapping(integration_sk, source_value, value_sk) VALUES (:i, :v, :k)"),
        {"i": int_sk, "v": source_value, "k": val_sk})
    return i_created, 1
