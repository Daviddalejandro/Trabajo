"""Endpoints RDM (SPEC §11). Prefijo /api/v1/rdm. El actor de auditoría llega en la
cabecera X-Actor (sin SSO en el prototipo, SPEC §2)."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.rdm import service
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
        out = service.create_value(session, code, body.value_code, body.value_name,
                                   body.parent_value_code, body.attributes, actor)
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
def homologate(system: str, field: str, value: str, session: Session = Depends(get_session)):
    out = service.homologate(session, system, field, value)
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


@router.post("/rehomologate", summary="Reprocesa los UNKNOWN de un catálogo (§7.2)")
def rehomologate(catalog: str):
    raise HTTPException(501, "Disponible a partir de la Fase 2: requiere staging y mdm (SPEC §14).")


@router.get("/source-systems", summary="Sistemas fuente registrados (owner y steward)")
def source_systems(session: Session = Depends(get_session)):
    return service.list_source_systems(session)


@router.get("/audit", summary="Últimos cambios de referencia (RDM_AUDIT_LOG)")
def audit(entity: str | None = None, limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    return service.audit_tail(session, entity, limit)
