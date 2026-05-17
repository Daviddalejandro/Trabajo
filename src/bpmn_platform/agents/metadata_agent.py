"""Agente de metadata (Fase 6/10): resumen estructurado del modelo."""
from __future__ import annotations

from ..excel.parser import ParseResult
from .base import Agent, AgentContext, AgentResult


class MetadataAgent(Agent):
    name = "metadata"

    def run(self, context: AgentContext) -> AgentResult:
        result: ParseResult | None = context.get("parse_result")
        if not result:
            return AgentResult(name=self.name, ok=True, summary="(skipped) sin contexto.")
        model = result.model

        metadata = {
            "processes": [
                {
                    "id": p.id,
                    "name": p.name,
                    "domain": p.domain,
                    "owner_role": p.owner_role_id,
                    "version": p.version,
                    "activities": [a.id for a in model.activities if a.process_id == p.id],
                }
                for p in model.processes
            ],
            "totals": {
                "processes": len(model.processes),
                "activities": len(model.activities),
                "events": len(model.events),
                "gateways": len(model.gateways),
                "commands": len(model.commands),
                "information_assets": len(model.information_assets),
                "risks_in_use": len({r for a in model.activities for r in a.risk_ids}),
                "controls_in_use": len({c for a in model.activities for c in a.control_ids}),
                "kpis": len(model.kpis),
                "slas": len(model.slas),
            },
        }
        context.set("model_metadata", metadata)
        return AgentResult(
            name=self.name,
            ok=True,
            summary=(
                f"Metadata empresarial: {metadata['totals']['activities']} actividades "
                f"en {metadata['totals']['processes']} procesos."
            ),
        )
