"""Entidades del metamodelo empresarial BPMN.

Todas las entidades son Pydantic v2 models. Cada entidad lleva un identificador
unico y, donde aplica, codigos referenciables desde catalogos controlados.

Importante (regla del documento maestro):

    Los comandos NO pertenecen directamente a la actividad.
    La relacion correcta es:  Actividad -> Sistema (Application) -> Command

Por ello `Command.application_id` es obligatorio y `Activity` no referencia
comandos directamente, sino aplicaciones (vease `relationships.py`).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import AssetClassification, BpmnType, GatewayKind, Severity


class _Entity(BaseModel):
    """Base comun para todas las entidades."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(..., min_length=1, description="Identificador unico (ej. PROC-001).")
    name: str = Field(..., min_length=1, description="Nombre legible para negocio.")
    description: str | None = None
    tags: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Capa de organizacion
# --------------------------------------------------------------------------- #

class Role(_Entity):
    """Responsable / rol organizacional ejecutor de actividades."""

    area: str | None = None
    is_human: bool = True


class Application(_Entity):
    """Aplicacion / sistema corporativo.

    Una aplicacion agrega `Command`s y `API`s.  Las actividades NUNCA referencian
    comandos directamente: pasan por la aplicacion (regla del modelo).
    """

    vendor: str | None = None
    environment: str | None = Field(default=None, description="prod|qa|dev|...")
    owner_role_id: str | None = None


class Command(_Entity):
    """Comando, script o batch ejecutable dentro de una aplicacion."""

    application_id: str = Field(..., description="Application duena del comando.")
    invocation: str | None = Field(
        default=None,
        description="Cadena tecnica de invocacion (ej. 'python reconcile.py').",
    )
    parameters: dict[str, Any] = Field(default_factory=dict)


class API(_Entity):
    """Integracion / contrato tecnico expuesto o consumido."""

    application_id: str | None = None
    method: str | None = None
    endpoint: str | None = None
    protocol: str = "https"


# --------------------------------------------------------------------------- #
# Capa de informacion
# --------------------------------------------------------------------------- #

class InformationAsset(_Entity):
    """Activo de informacion (documento, dataset, registro)."""

    classification: AssetClassification = AssetClassification.INTERNAL
    owner_role_id: str | None = None
    storage_application_id: str | None = None


class DataObject(_Entity):
    """Objeto de datos BPMN (entrada/salida de actividades)."""

    asset_id: str | None = Field(
        default=None,
        description="Vinculo opcional con InformationAsset del catalogo.",
    )


# --------------------------------------------------------------------------- #
# Capa de gobierno
# --------------------------------------------------------------------------- #

class Risk(_Entity):
    severity: Severity = Severity.MEDIUM
    category: str | None = None


class Control(_Entity):
    mitigates_risk_ids: list[str] = Field(default_factory=list)
    type: str | None = Field(default=None, description="preventive|detective|corrective")
    automated: bool = False


class KPI(_Entity):
    unit: str | None = None
    target: float | None = None
    direction: str | None = Field(default=None, description="higher_is_better|lower_is_better")


class SLA(_Entity):
    duration: timedelta
    measurement: str | None = None

    @field_validator("duration", mode="before")
    @classmethod
    def _coerce_duration(cls, value: Any) -> Any:
        if isinstance(value, (int, float)):
            return timedelta(hours=float(value))
        if isinstance(value, str):
            text = value.strip().lower()
            for suffix, factor in (("h", 3600), ("m", 60), ("s", 1), ("d", 86400)):
                if text.endswith(suffix):
                    try:
                        return timedelta(seconds=float(text[:-1]) * factor)
                    except ValueError:
                        break
        return value


# --------------------------------------------------------------------------- #
# Capa BPMN (proceso, actividades, eventos, compuertas)
# --------------------------------------------------------------------------- #

class Event(_Entity):
    bpmn_type: BpmnType
    is_start: bool = False
    is_end: bool = False


class Gateway(_Entity):
    kind: GatewayKind = GatewayKind.EXCLUSIVE
    condition: str | None = None


class Activity(_Entity):
    """Actividad BPMN.

    Reglas:
      * El nombre debe respetar 'Verbo + Objeto [+ Contexto]'  (se valida en
        capa semantica, no aqui, para permitir importacion permisiva).
      * `application_ids` lista los sistemas usados; los comandos viven dentro
        de cada aplicacion.
    """

    bpmn_type: BpmnType
    process_id: str
    role_id: str | None = None
    application_ids: list[str] = Field(default_factory=list)
    api_ids: list[str] = Field(default_factory=list)
    risk_ids: list[str] = Field(default_factory=list)
    control_ids: list[str] = Field(default_factory=list)
    kpi_ids: list[str] = Field(default_factory=list)
    sla_id: str | None = None
    observations: str | None = None


class Process(_Entity):
    """Proceso de negocio raiz, contiene actividades/eventos/compuertas."""

    domain: str | None = None
    owner_role_id: str | None = None
    version: str = "1.0.0"
