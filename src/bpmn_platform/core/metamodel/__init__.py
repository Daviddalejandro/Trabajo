"""Metamodelo empresarial BPMN (Fase 2).

Define las entidades minimas:
    Process, Activity, Role, Application, Command, API,
    InformationAsset, DataObject, Risk, Control, KPI, SLA,
    Event, Gateway.

Y las relaciones empresariales clave del modelo:
    Process       -> contiene -> Activity
    Activity      -> ejecutada_por -> Role
    Activity      -> usa -> Application
    Application   -> ejecuta -> Command
    Activity      -> consume / produce -> InformationAsset
    Activity      -> integrada_con -> API
    Activity      -> mitigada_por -> Control
    Activity      -> monitoreada_por -> KPI
"""
from .entities import (
    API,
    KPI,
    SLA,
    Activity,
    Application,
    Command,
    Control,
    DataObject,
    Event,
    Gateway,
    InformationAsset,
    Process,
    Risk,
    Role,
)
from .enums import (
    AssetClassification,
    BpmnType,
    GatewayKind,
    Severity,
)
from .relationships import (
    ActivityApplicationUse,
    ActivityAssetFlow,
    AssetFlowDirection,
    EnterpriseModel,
)

__all__ = [
    # Enums
    "BpmnType",
    "GatewayKind",
    "Severity",
    "AssetClassification",
    "AssetFlowDirection",
    # Entities
    "Process",
    "Activity",
    "Role",
    "Application",
    "Command",
    "API",
    "InformationAsset",
    "DataObject",
    "Risk",
    "Control",
    "KPI",
    "SLA",
    "Event",
    "Gateway",
    # Relationships / aggregate
    "ActivityApplicationUse",
    "ActivityAssetFlow",
    "EnterpriseModel",
]
