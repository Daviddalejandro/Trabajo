"""Agente de parsing (Fase 4): convierte un Excel en EnterpriseModel."""
from __future__ import annotations

from pathlib import Path

from ..core.catalogs import CatalogBundle
from ..excel.parser import ExcelParser
from ..logging_config import get_logger
from .base import Agent, AgentContext, AgentResult

log = get_logger(__name__)


class ParserAgent(Agent):
    name = "parser"

    def __init__(
        self,
        catalogs: CatalogBundle | None = None,
        parser: ExcelParser | None = None,
    ) -> None:
        self._parser = parser or ExcelParser(catalogs=catalogs)

    def run(self, context: AgentContext) -> AgentResult:
        excel_path = context.get("excel_path")
        if not excel_path:
            return AgentResult(
                name=self.name,
                ok=True,
                summary="(skipped) No se proporciono 'excel_path' en el contexto.",
            )
        result = self._parser.parse(Path(excel_path))
        context.set("parse_result", result)
        context.set("enterprise_model", result.model)

        model = result.model
        summary = (
            f"Procesos: {len(model.processes)}, "
            f"Actividades: {len(model.activities)}, "
            f"Eventos: {len(model.events)}, "
            f"Gateways: {len(model.gateways)}. "
            f"Errores: {len(result.errors)}, "
            f"Warnings: {len(result.warnings)}."
        )
        issues = [
            f"[{issue.severity.value}] {issue.code}: {issue.message} ({issue.location})"
            for issue in result.issues
        ]
        return AgentResult(name=self.name, ok=result.ok, summary=summary, issues=issues)
