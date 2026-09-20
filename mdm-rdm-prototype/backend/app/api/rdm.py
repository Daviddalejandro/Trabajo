"""Endpoints RDM (SPEC §11). Prefijo /api/v1/rdm. El actor de auditoría llega en la
cabecera X-Actor (sin SSO en el prototipo, SPEC §2)."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.rdm import console, service
from app.rdm.seed import add_mapping

router = APIRouter(prefix="/rdm", tags=["rdm"])


def actor_header(x_actor: str = Header(default="anonimo", alias="X-Actor")) -> str:
    return x_actor[:120]


class ValueIn(BaseModel):
    value_code: str = Field(min_length=1, max_length=60, pattern=r"^[A-Z0-9_.\-]+$")
    value_name: str = Field(min_length=1, max_length=200)
    parent_value_code: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)


class MappingIn(BaseModel):
    system: str
    field: str
    catalog: str
    source_value: str
    value_code: str


class MappingRef(BaseModel):
    system: str
    field: str
    catalog: str
    source_value: str


class DomainIn(BaseModel):
    domain_code: str = Field(min_length=2, max_length=40)
    domain_name: str = Field(min_length=1, max_length=120)


class CatalogIn(BaseModel):
    catalog_code: str = Field(min_length=4, max_length=60)
    catalog_name: str = Field(min_length=1, max_length=160)
    domain_code: str
    official_source: str | None = None
    is_hierarchical: bool = False


class AttributeIn(BaseModel):
    field_code: str = Field(min_length=2, max_length=60)
    field_name: str = Field(min_length=1, max_length=160)
    data_type: str = "TEXT"
    is_required: bool = False
    description: str | None = None


class AttributesIn(BaseModel):
    attributes: dict[str, str]


class SourceSystemIn(BaseModel):
    source_system_cd: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=160)
    data_owner: str | None = None
    data_steward: str | None = None
    is_prototype_active: bool = True


class IntegrationIn(BaseModel):
    catalog: str
    system: str
    source_field: str = Field(min_length=1, max_length=60)


def _handle(fn):
    """Traduce las excepciones de dominio a HTTP: no existe → 404, ya existe → 409, inválido → 422."""
    try:
        return fn()
    except LookupError as e:
        raise HTTPException(404, str(e))
    except FileExistsError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/labels", summary="Nombres en español de todos los códigos canónicos (consola): {catálogo: {código: nombre}}")
def labels(session: Session = Depends(get_session)):
    return service.labels(session)


@router.get("/domains", summary="Dominios de referencia")
def domains(session: Session = Depends(get_session)):
    return service.list_domains(session)


@router.get("/catalogs", summary="Catálogos (opcionalmente por dominio)")
def catalogs(domain: str | None = None, session: Session = Depends(get_session)):
    return service.list_catalogs(session, domain)


@router.get("/catalogs/{code}/values", summary="Valores canónicos de un catálogo (paginado)")
def values(code: str, include_inactive: bool = False, limit: int = Query(200, ge=1, le=1000),
           cursor: int = Query(0, ge=0), session: Session = Depends(get_session)):
    if service.get_catalog(session, code) is None:
        raise HTTPException(404, f"Catálogo {code} no existe")
    items, next_cursor = service.list_values(session, code, include_inactive, limit, cursor)
    return {"catalog_code": code, "items": items, "next_cursor": next_cursor}


@router.post("/catalogs/{code}/values", status_code=201, summary="Alta de valor canónico (nunca edita publicados)")
def create_value(code: str, body: ValueIn, actor: str = Depends(actor_header),
                 session: Session = Depends(get_session)):
    try:
        attributes = console.validate_attributes(session, code, body.attributes, for_new_value=True) if service.get_catalog(session, code) else body.attributes
        out = service.create_value(session, code, body.value_code, body.value_name,
                                   body.parent_value_code, attributes, actor)
        session.commit()
        return out
    except LookupError as e:
        session.rollback(); raise HTTPException(404, str(e))
    except ValueError as e:
        session.rollback(); raise HTTPException(409, str(e))


@router.post("/catalogs/{code}/values/{value_code}/deprecate", summary="Deprecación (inmutabilidad §3.7)")
def deprecate(code: str, value_code: str, actor: str = Depends(actor_header),
              session: Session = Depends(get_session)):
    try:
        out = service.deprecate_value(session, code, value_code, actor)
        session.commit()
        return out
    except LookupError as e:
        session.rollback(); raise HTTPException(404, str(e))


@router.get("/homologate", summary="Código fuente → canónico (prueba canónica del RDM)")
def homologate(system: str, field: str, value: str, catalog: str | None = None, session: Session = Depends(get_session)):
    out = service.homologate(session, system, field, value, catalog)
    if out is None:
        raise HTTPException(404, {"mensaje": "Sin homologación: el campo quedará en 0 = UNKNOWN y generará un "
                                              "hallazgo VALIDITY", "system": system, "field": field, "value": value})
    return out


@router.get("/crosswalk", summary="Fuente A → fuente B por valor canónico")
def crosswalk(from_system: str, field: str, value: str, to_system: str | None = None,
              session: Session = Depends(get_session)):
    return service.crosswalk(session, from_system, field, value, to_system)


@router.get("/mappings", summary="Homologaciones vigentes")
def mappings(system: str | None = None, catalog: str | None = None, session: Session = Depends(get_session)):
    return service.list_mappings(session, system, catalog)


@router.post("/mappings", status_code=201, summary="Alta de homologación fuente→canónico")
def create_mapping(body: MappingIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    try:
        service.set_actor(session, actor)
        _, created = add_mapping(session, body.system, body.field, body.catalog, body.source_value, body.value_code)
        session.commit()
        return {"created": bool(created), **body.model_dump()}
    except LookupError as e:
        session.rollback(); raise HTTPException(404, str(e))
    except IntegrityError as e:
        session.rollback(); raise HTTPException(409, str(e.orig))


@router.get("/source-systems", summary="Sistemas fuente registrados (owner y steward)")
def source_systems(session: Session = Depends(get_session)):
    return service.list_source_systems(session)


@router.get("/audit", summary="Últimos cambios de referencia (RDM_AUDIT_LOG)")
def audit(entity: str | None = None, limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    return service.audit_tail(session, entity, limit)


# ------------------------------------------------------------------ Consola RDM: las cinco capas desde la interfaz
@router.get("/overview", summary="Consola RDM · conteos por capa (dominios, catálogos, valores, campos, sistemas, integraciones, mapeos, auditoría)")
def overview(session: Session = Depends(get_session)):
    return console.overview(session)


@router.post("/domains", status_code=201, summary="Consola RDM · alta de dominio")
def create_domain(body: DomainIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    def go():
        out = console.create_domain(session, body.domain_code, body.domain_name, actor); session.commit(); return out
    try:
        return _handle(go)
    except HTTPException:
        session.rollback(); raise


@router.post("/catalogs", status_code=201, summary="Consola RDM · alta de catálogo en un dominio")
def create_catalog(body: CatalogIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    def go():
        out = console.create_catalog(session, body.catalog_code, body.catalog_name, body.domain_code, body.official_source, body.is_hierarchical, actor)
        session.commit(); return out
    try:
        return _handle(go)
    except HTTPException:
        session.rollback(); raise


@router.get("/catalogs/{code}/detail", summary="Consola RDM · ficha del catálogo: conteos, campos personalizados e integraciones")
def catalog_detail(code: str, session: Session = Depends(get_session)):
    out = console.catalog_detail(session, code)
    if out is None:
        raise HTTPException(404, f"Catálogo {code} no existe")
    return out


@router.get("/catalogs/{code}/attributes", summary="Consola RDM · campos personalizados (diccionario del EAV) de un catálogo")
def attributes(code: str, include_inactive: bool = False, session: Session = Depends(get_session)):
    if service.get_catalog(session, code) is None:
        raise HTTPException(404, f"Catálogo {code} no existe")
    return console.list_attributes(session, code, include_inactive)


@router.post("/catalogs/{code}/attributes", status_code=201, summary="Consola RDM · definir un campo personalizado")
def create_attribute(code: str, body: AttributeIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    def go():
        out = console.create_attribute(session, code, body.field_code, body.field_name, body.data_type, body.is_required, body.description, actor)
        session.commit(); return out
    try:
        return _handle(go)
    except HTTPException:
        session.rollback(); raise


@router.post("/catalogs/{code}/attributes/{field_code}/retire", summary="Consola RDM · retirar un campo personalizado (los datos EAV se conservan)")
def retire_attribute(code: str, field_code: str, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    def go():
        out = console.retire_attribute(session, code, field_code, actor); session.commit(); return out
    try:
        return _handle(go)
    except HTTPException:
        session.rollback(); raise


@router.put("/catalogs/{code}/values/{value_code}/attributes", summary="Consola RDM · completar o corregir los atributos de un valor (código y nombre siguen inmutables)")
def set_value_attributes(code: str, value_code: str, body: AttributesIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    def go():
        out = console.set_value_attributes(session, code, value_code, body.attributes, actor); session.commit(); return out
    try:
        return _handle(go)
    except HTTPException:
        session.rollback(); raise


@router.post("/source-systems", status_code=201, summary="Consola RDM · registrar un sistema fuente (owner y steward)")
def create_source_system(body: SourceSystemIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    def go():
        out = console.create_source_system(session, body.source_system_cd, body.name, body.data_owner, body.data_steward, body.is_prototype_active, actor)
        session.commit(); return out
    try:
        return _handle(go)
    except HTTPException:
        session.rollback(); raise


@router.get("/integrations", summary="Consola RDM · qué campo de qué sistema alimenta cada catálogo")
def integrations(catalog: str | None = None, system: str | None = None, session: Session = Depends(get_session)):
    return console.list_integrations(session, catalog, system)


@router.post("/integrations", status_code=201, summary="Consola RDM · declarar una integración campo fuente → catálogo")
def create_integration(body: IntegrationIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    def go():
        out = console.create_integration(session, body.catalog, body.system, body.source_field, actor); session.commit(); return out
    try:
        return _handle(go)
    except HTTPException:
        session.rollback(); raise


@router.post("/mappings/retire", summary="Consola RDM · cerrar la homologación vigente (queda en el histórico)")
def retire_mapping(body: MappingRef, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    def go():
        out = console.retire_mapping(session, body.system, body.field, body.catalog, body.source_value, actor); session.commit(); return out
    try:
        return _handle(go)
    except HTTPException:
        session.rollback(); raise


@router.get("/mappings/history", summary="Consola RDM · versiones de una homologación (vigente y cerradas)")
def mapping_history(system: str, field: str, catalog: str, source_value: str | None = None, session: Session = Depends(get_session)):
    return console.mapping_history(session, system, field, catalog, source_value)


@router.get("/audit/detail", summary="Consola RDM · auditoría con el antes y el después de cada cambio")
def audit_detail(entity: str | None = None, limit: int = Query(30, ge=1, le=200), session: Session = Depends(get_session)):
    return console.audit_detail(session, entity, limit)

