"""Endpoints de cumplimiento (SPEC §11): contactabilidad, contactos y finalidades, consentimientos,
preferencias, ARCO, RNE, audiencias, purga simulada y feed de cambios."""
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.compliance import service
from app.compliance.eligibility import contactability
from app.core.db import get_session

router = APIRouter(tags=["compliance"])


def actor_header(x_actor: str = Header(default="anonimo", alias="X-Actor")) -> str:
    return x_actor[:120]


class PurposeIn(BaseModel):
    purpose: str
    allowed: bool
    frequency: str | None = None
    origin: str | None = None


class ChannelPrefIn(PurposeIn):
    channel: str


class ConfirmationIn(BaseModel):
    status: str = Field(pattern="^(CONFIRMED_BY_TITULAR|CONFIRMED_BY_CONTACT|UNCONFIRMED|WRONG_PERSON|INVALID)$")
    evidence: str | None = None


class ConsentIn(BaseModel):
    consent_type: str
    status: str = Field(pattern="^(GRANTED|DENIED|REVOKED|EXPIRED|PENDING)$")
    evidence_ref: str | None = None


class ArcoIn(BaseModel):
    arco_type: str = Field(pattern="^(ACCESS|RECTIFICATION|CANCELLATION|OPPOSITION)$")
    channel_received: str | None = None
    requested_at: datetime | None = Field(default=None, description="Solo para simulación (datos sintéticos): fecha de radicación en el pasado")
    note: str | None = None


class ArcoUpdateIn(BaseModel):
    status: str = Field(pattern="^(RESOLVED|REJECTED|IN_PROGRESS)$")
    note: str | None = None


class RneIn(BaseModel):
    file: str = "data/synth/rne_sample.csv"


def _run(session: Session, fn, *a, **kw):
    try:
        out = fn(session, *a, **kw)
        session.commit()
        return out
    except LookupError as e:
        session.rollback(); raise HTTPException(404, str(e))
    except ValueError as e:
        session.rollback(); raise HTTPException(409, str(e))


@router.get("/parties/{party_sk}/contactability", summary="Elegibilidad por contacto y finalidad (12 precedencias, §10.3)")
def get_contactability(party_sk: int, contact_point_sk: int | None = None, purpose: str | None = None, session: Session = Depends(get_session)):
    try:
        return contactability(session, party_sk, contact_point_sk, purpose)
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/parties/{party_sk}/contacts", summary="Vínculos de contacto filtrables (lista de trabajo)")
def get_contacts(party_sk: int, purpose: str | None = None, confirmation: str | None = None, origin: str | None = None, usage_role: str | None = None,
                 session: Session = Depends(get_session)):
    return service.list_contacts(session, party_sk, purpose, confirmation, origin, usage_role)


@router.put("/parties/{party_sk}/contacts/{party_contact_sk}/purposes", summary="Finalidades del contacto (una fila por finalidad; nunca borra el histórico)")
def put_contact_purposes(party_sk: int, party_contact_sk: int, body: list[PurposeIn], actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    return _run(session, service.set_preferences, party_sk, [b.model_dump() for b in body], actor, party_contact_sk)


@router.post("/parties/{party_sk}/contacts/{party_contact_sk}/confirmation", summary="Confirmación del contacto desde la gestión")
def post_confirmation(party_sk: int, party_contact_sk: int, body: ConfirmationIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    return _run(session, service.set_confirmation, party_sk, party_contact_sk, body.status, actor, body.evidence)


@router.post("/parties/{party_sk}/consents", status_code=201, summary="Alta o cambio de autorización por tipo (crea fila nueva, cierra la anterior)")
def post_consent(party_sk: int, body: ConsentIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    return _run(session, service.set_consent, party_sk, body.consent_type, body.status, actor, body.evidence_ref)


@router.put("/parties/{party_sk}/preferences", summary="Preferencias de canal (party_contact_sk nulo)")
def put_preferences(party_sk: int, body: list[ChannelPrefIn], actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    return _run(session, service.set_preferences, party_sk, [b.model_dump() for b in body], actor, None)


@router.post("/parties/{party_sk}/arco", status_code=201, summary="Solicitud ARCO con due_at en días hábiles (Ley 1581/2012 arts. 14 y 15)")
def post_arco(party_sk: int, body: ArcoIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    return _run(session, service.create_arco_request, party_sk, body.arco_type, actor, body.channel_received, body.requested_at, body.note)


@router.get("/arco/requests", summary="Solicitudes ARCO con estado de SLA derivado")
def get_arco(sla: str | None = Query(None, pattern="^(OVERDUE|DUE_SOON|ON_TRACK|RESOLVED|OPEN|ALL)$"), party_sk: int | None = None,
             session: Session = Depends(get_session)):
    return service.list_arco_requests(session, sla, party_sk)


@router.patch("/arco/requests/{request_sk}", summary="Cierre o avance de una solicitud ARCO")
def patch_arco(request_sk: int, body: ArcoUpdateIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    return _run(session, service.resolve_arco_request, request_sk, body.status, actor, body.note)


@router.post("/rne/sync", summary="Sincroniza el RNE simulado (solo afecta la finalidad COMMERCIAL)")
def post_rne(body: RneIn, actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    try:
        out = service.rne_sync(session, body.file, actor); session.commit(); return out
    except FileNotFoundError as e:
        session.rollback(); raise HTTPException(404, f"Archivo no encontrado: {e}")


@router.get("/audiences", summary="Audiencia elegible por finalidad y canal (§10.4); toda ejecución se audita")
def get_audience(purpose: str, channel: str, role: str | None = None, segment: str | None = None, service_: str | None = Query(None, alias="service"),
                 enrollment_status: str | None = None, limit: int = Query(500, ge=1, le=5000), actor: str = Depends(actor_header),
                 session: Session = Depends(get_session)):
    out = service.audience(session, purpose, channel, actor, role, segment, service_, enrollment_status, limit)
    session.commit()
    return out


@router.get("/retention/purge-candidates", summary="Purga simulada (§10.5): nunca borra")
def get_purge(actor: str = Depends(actor_header), session: Session = Depends(get_session)):
    out = service.purge_candidates(session, actor, dry_run=True)
    session.commit()
    return out


@router.get("/changes", summary="Feed de cambios del golden para consumidores (SAP CDP, campañas, analítica)")
def get_changes(since: datetime | None = None, entity: str | None = None, limit: int = Query(200, ge=1, le=2000), cursor: int = Query(0, ge=0),
                session: Session = Depends(get_session)):
    return service.changes(session, since, entity, limit, cursor)
