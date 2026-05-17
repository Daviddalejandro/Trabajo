"""Agente de calidad BPMN (Fase 8)."""
from __future__ import annotations

from ..bpmn import QualityValidator
from ..excel.parser import ParseResult
from .base import Agent, AgentContext, AgentResult


class QualityAgent(Agent):
    name = "quality"

    def __init__(self, validator: QualityValidator | None = None) -> None:
        self._validator = validator or QualityValidator()

    def run(self, context: AgentContext) -> AgentResult:
        result: ParseResult | None = context.get("parse_result")
        if not result or not result.model.processes:
            return AgentResult(
                name=self.name, ok=True, summary="(skipped) sin modelo para validar."
            )
        report = self._validator.validate(result.model)
        context.set("quality_report", report)
        return AgentResult(
            name=self.name,
            ok=report.ok,
            summary=(
                f"Calidad BPMN: score {report.score}/100 - "
                f"{len(report.errors)} errores, {len(report.warnings)} warnings, "
                f"{len(report.infos)} infos."
            ),
            issues=[
                f"[{i.severity.value}] {i.code}: {i.message}"
                for i in report.issues
            ],
        )
