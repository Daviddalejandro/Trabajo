"""Registro de los agentes definidos por el documento maestro.

En fases 1-3 cada agente se implementa como `PlannedAgent`, que documenta
su rol y devuelve `ok=True` sin trabajo real. La firma estable evita que
las fases superiores tengan que cambiar el orquestador despues.
"""
from __future__ import annotations

from .base import Agent, AgentContext, AgentResult


class PlannedAgent(Agent):
    """Agente placeholder con descripcion textual de su funcion futura."""

    def __init__(self, name: str, mission: str) -> None:
        self.name = name
        self.mission = mission

    def run(self, context: AgentContext) -> AgentResult:  # noqa: ARG002
        return AgentResult(
            name=self.name,
            ok=True,
            summary=f"[planned] {self.mission}",
        )


def default_agents() -> list[Agent]:
    """Lista canonica de agentes (segun el documento maestro)."""
    from .parser_agent import ParserAgent
    from .validation_agent import ValidationAgent

    return [
        ParserAgent(),
        ValidationAgent(),
        PlannedAgent("semantic",        "Interpretar negocio e inferir BPMN."),
        PlannedAgent("bpmn",            "Construir BPMN 2.0 XML valido."),
        PlannedAgent("governance",      "Aplicar riesgos, controles y SLA."),
        PlannedAgent("metadata",        "Relacionar entidades empresariales."),
        PlannedAgent("quality",         "Validar calidad BPMN."),
        PlannedAgent("export",          "Generar XML/PNG/SVG/PDF."),
        PlannedAgent("recommendation",  "Proponer mejoras y simplificaciones."),
    ]
