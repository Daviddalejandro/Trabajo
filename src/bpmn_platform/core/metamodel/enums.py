"""Enumeraciones del metamodelo BPMN empresarial."""
from __future__ import annotations

from enum import Enum


class BpmnType(str, Enum):
    """Tipos BPMN permitidos en la plataforma (subset gobernado)."""

    START_EVENT = "StartEvent"
    USER_TASK = "UserTask"
    SERVICE_TASK = "ServiceTask"
    EXCLUSIVE_GATEWAY = "ExclusiveGateway"
    PARALLEL_GATEWAY = "ParallelGateway"
    END_EVENT = "EndEvent"
    INTERMEDIATE_CATCH_EVENT = "IntermediateCatchEvent"
    MESSAGE_EVENT = "MessageEvent"

    @classmethod
    def business_labels(cls) -> dict[str, "BpmnType"]:
        """Mapea etiquetas de negocio (las que ve el usuario en el Excel)."""
        return {
            "Inicio": cls.START_EVENT,
            "Actividad Humana": cls.USER_TASK,
            "Actividad Automatica": cls.SERVICE_TASK,
            "Actividad Automática": cls.SERVICE_TASK,
            "Decision": cls.EXCLUSIVE_GATEWAY,
            "Decisión": cls.EXCLUSIVE_GATEWAY,
            "Paralelo": cls.PARALLEL_GATEWAY,
            "Fin": cls.END_EVENT,
            "Espera": cls.INTERMEDIATE_CATCH_EVENT,
            "Mensaje": cls.MESSAGE_EVENT,
        }


class GatewayKind(str, Enum):
    EXCLUSIVE = "exclusive"
    PARALLEL = "parallel"
    INCLUSIVE = "inclusive"
    EVENT_BASED = "event_based"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AssetClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class AssetFlowDirection(str, Enum):
    CONSUMES = "consumes"
    PRODUCES = "produces"
