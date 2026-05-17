"""Agente de validacion empresarial (Fase 4 inicial).

Toma el `parse_result` producido por `ParserAgent` y aplica un primer
conjunto de reglas cruzadas entre entidades. Las validaciones BPMN
profundas (conectividad, gateways balanceados) se completan en la Fase 8.
"""
from __future__ import annotations

from ..core.governance import IssueSeverity
from ..core.metamodel import BpmnType
from ..excel.parser import ParseResult
from .base import Agent, AgentContext, AgentResult


class ValidationAgent(Agent):
    name = "validation"

    def run(self, context: AgentContext) -> AgentResult:
        result: ParseResult | None = context.get("parse_result")
        if not result:
            return AgentResult(
                name=self.name,
                ok=True,
                summary="(skipped) No hay resultado de parsing previo.",
            )

        model = result.model
        findings: list[str] = []

        for activity in model.activities:
            if activity.bpmn_type == BpmnType.USER_TASK and not activity.role_id:
                findings.append(
                    f"[{IssueSeverity.WARNING.value}] ACT-NO-ROLE: "
                    f"UserTask '{activity.id}' sin Responsable asignado."
                )
            if activity.bpmn_type == BpmnType.SERVICE_TASK and not activity.application_ids:
                findings.append(
                    f"[{IssueSeverity.WARNING.value}] ACT-NO-SYSTEM: "
                    f"ServiceTask '{activity.id}' sin Sistema asignado."
                )

        process_ids_with_activity = {a.process_id for a in model.activities}
        for process in model.processes:
            if process.id not in process_ids_with_activity:
                findings.append(
                    f"[{IssueSeverity.WARNING.value}] PROC-NO-ACT: "
                    f"Proceso '{process.id}' no tiene actividades."
                )

        risks_with_control: set[str] = set()
        risks_in_use: set[str] = set()
        for activity in model.activities:
            risks_in_use.update(activity.risk_ids)
            if activity.risk_ids and activity.control_ids:
                risks_with_control.update(activity.risk_ids)
        for risk_id in risks_in_use - risks_with_control:
            findings.append(
                f"[{IssueSeverity.INFO.value}] RISK-NO-CONTROL: "
                f"Riesgo '{risk_id}' usado en alguna actividad sin control declarado."
            )

        # Cobertura de inicio/fin por proceso
        starts_by_process: dict[str, int] = {}
        ends_by_process: dict[str, int] = {}
        for event in model.events:
            owner = next(
                (a.process_id for a in model.activities if a.id == event.id),
                None,
            )
            target_map = starts_by_process if event.is_start else (
                ends_by_process if event.is_end else None
            )
            if target_map is None:
                continue
            key = owner or "<sin proceso>"
            target_map[key] = target_map.get(key, 0) + 1

        return AgentResult(
            name=self.name,
            ok=True,
            summary=f"Validaciones empresariales: {len(findings)} hallazgos.",
            issues=findings,
        )
