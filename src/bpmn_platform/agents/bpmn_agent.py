"""Agente generador BPMN (Fase 6)."""
from __future__ import annotations

from ..bpmn import BpmnGenerator
from ..excel.parser import ParseResult
from .base import Agent, AgentContext, AgentResult


class BpmnAgent(Agent):
    name = "bpmn"

    def __init__(self, generator: BpmnGenerator | None = None) -> None:
        self._generator = generator or BpmnGenerator()

    def run(self, context: AgentContext) -> AgentResult:
        result: ParseResult | None = context.get("parse_result")
        if not result or not result.model.processes:
            return AgentResult(
                name=self.name, ok=True, summary="(skipped) sin procesos para generar BPMN."
            )
        bpmn_result = self._generator.generate(result.model)
        context.set("bpmn_result", bpmn_result)
        return AgentResult(
            name=self.name,
            ok=True,
            summary=(
                f"BPMN XML generado ({len(bpmn_result.xml)} bytes, "
                f"{len(bpmn_result.layouts)} diagramas)."
            ),
        )
