"""Relaciones empresariales y modelo agregado raiz.

`EnterpriseModel` es el contenedor que mantiene la coherencia referencial
entre catalogos y procesos. Se usa para validar el corpus completo antes
de generar BPMN XML (fases 6+).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
from .enums import AssetFlowDirection


class ActivityApplicationUse(BaseModel):
    """Vinculo Actividad -> Aplicacion -> Comandos invocados.

    Materializa la regla 'Actividad -> Sistema -> Comando' permitiendo
    declarar que comandos concretos se invocan dentro de esa app para esa
    actividad.
    """

    model_config = ConfigDict(extra="forbid")

    activity_id: str
    application_id: str
    command_ids: list[str] = Field(default_factory=list)


class ActivityAssetFlow(BaseModel):
    """Flujo de informacion: actividad consume/produce activos."""

    model_config = ConfigDict(extra="forbid")

    activity_id: str
    asset_id: str
    direction: AssetFlowDirection


class EnterpriseModel(BaseModel):
    """Modelo agregado de la plataforma (catalogos + procesos + relaciones)."""

    model_config = ConfigDict(extra="forbid")

    # Catalogos
    roles: list[Role] = Field(default_factory=list)
    applications: list[Application] = Field(default_factory=list)
    commands: list[Command] = Field(default_factory=list)
    apis: list[API] = Field(default_factory=list)
    information_assets: list[InformationAsset] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    controls: list[Control] = Field(default_factory=list)
    kpis: list[KPI] = Field(default_factory=list)
    slas: list[SLA] = Field(default_factory=list)

    # BPMN
    processes: list[Process] = Field(default_factory=list)
    activities: list[Activity] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    gateways: list[Gateway] = Field(default_factory=list)
    data_objects: list[DataObject] = Field(default_factory=list)

    # Relaciones materializadas
    activity_application_uses: list[ActivityApplicationUse] = Field(default_factory=list)
    activity_asset_flows: list[ActivityAssetFlow] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_unique_ids(self) -> "EnterpriseModel":
        for collection_name in (
            "roles",
            "applications",
            "commands",
            "apis",
            "information_assets",
            "risks",
            "controls",
            "kpis",
            "slas",
            "processes",
            "activities",
            "events",
            "gateways",
            "data_objects",
        ):
            items = getattr(self, collection_name)
            ids = [item.id for item in items]
            duplicated = {i for i in ids if ids.count(i) > 1}
            if duplicated:
                raise ValueError(
                    f"IDs duplicados en '{collection_name}': {sorted(duplicated)}"
                )
        return self

    def index(self) -> dict[str, dict[str, object]]:
        """Indices por id para lookup rapido."""
        return {
            "role": {r.id: r for r in self.roles},
            "application": {a.id: a for a in self.applications},
            "command": {c.id: c for c in self.commands},
            "api": {a.id: a for a in self.apis},
            "asset": {a.id: a for a in self.information_assets},
            "risk": {r.id: r for r in self.risks},
            "control": {c.id: c for c in self.controls},
            "kpi": {k.id: k for k in self.kpis},
            "sla": {s.id: s for s in self.slas},
            "process": {p.id: p for p in self.processes},
            "activity": {a.id: a for a in self.activities},
        }
