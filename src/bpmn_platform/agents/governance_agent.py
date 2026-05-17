"""Agente de gobierno (Fase 7 + 10 integrados).

Persiste eventos de auditoria con el resumen del corrida actual y emite
hallazgos cuando faltan controles para riesgos en uso.
"""
from __future__ import annotations

from ..core.governance import IssueSeverity
from ..excel.parser import ParseResult
from ..governance.audit import audit_log
from .base import Agent, AgentContext, AgentResult


class GovernanceAgent(Agent):
    name = "governance"

    def run(self, context: AgentContext) -> AgentResult:
        result: ParseResult | None = context.get("parse_result")
        if not result:
            return AgentResult(
                name=self.name, ok=True, summary="(skipped) sin contexto."
            )
        model = result.model
        findings: list[str] = []

        # Cobertura riesgo->control
        risks_in_use = {r for a in model.activities for r in a.risk_ids}
        controls_in_use = {c for a in model.activities for c in a.control_ids}
        controls_by_id = {c.id: c for c in model.controls}
        for risk_id in risks_in_use:
            covered = False
            for ctrl_id in controls_in_use:
                ctrl = controls_by_id.get(ctrl_id)
                if ctrl and risk_id in ctrl.mitigates_risk_ids:
                    covered = True
                    break
            if not covered:
                findings.append(
                    f"[{IssueSeverity.WARNING.value}] GOV-RISK-UNCOVERED: "
                    f"Riesgo '{risk_id}' no tiene control declarado que lo mitigue."
                )

        # Trazabilidad Actividad -> Sistema -> Comando
        cmds_by_app: dict[str, list[str]] = {}
        for cmd in model.commands:
            cmds_by_app.setdefault(cmd.application_id, []).append(cmd.id)
        for use in model.activity_application_uses:
            if not use.command_ids and use.application_id in cmds_by_app:
                findings.append(
                    f"[{IssueSeverity.INFO.value}] GOV-SYS-NO-CMD: "
                    f"Actividad '{use.activity_id}' usa '{use.application_id}' "
                    "sin comando explicito (existen comandos catalogados)."
                )

        audit_log(
            event="pipeline_run",
            payload={
                "processes": [p.id for p in model.processes],
                "activities": len(model.activities),
                "findings": len(findings),
            },
        )

        return AgentResult(
            name=self.name,
            ok=True,
            summary=f"Gobierno empresarial: {len(findings)} hallazgos.",
            issues=findings,
        )
