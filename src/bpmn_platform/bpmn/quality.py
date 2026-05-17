"""Validador de calidad BPMN (Fase 8).

Sobre un `EnterpriseModel` con SequenceFlows ya construidos, aplica las
validaciones empresariales y estructurales canonicas y emite un
`QualityReport` con score 0-100.

Reglas implementadas (las profundas — formal verification, simulacion —
quedan para fases ulteriores):

  * Cada proceso debe tener al menos un StartEvent y un EndEvent.
  * Todo nodo debe ser alcanzable desde un StartEvent.
  * No deben existir tareas/eventos huerfanos (sin in/out salvo start/end).
  * Los gateways deben tener al menos 2 salidas (split) o 2 entradas (join).
  * UserTask debe tener responsable.
  * ServiceTask debe tener sistema (Application) declarado.
  * Toda actividad con riesgo declarado debe tener control declarado.
  * Cada flujo debe referenciar nodos existentes (validado al construir).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from ..core.governance import IssueSeverity
from ..core.metamodel import BpmnType, EnterpriseModel


@dataclass
class QualityIssue:
    severity: IssueSeverity
    code: str
    message: str
    process_id: str | None = None
    element_id: str | None = None


@dataclass
class QualityReport:
    score: int  # 0-100
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.ERROR]

    @property
    def warnings(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.WARNING]

    @property
    def infos(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.severity == IssueSeverity.INFO]

    @property
    def ok(self) -> bool:
        return not self.errors


_WEIGHT = {
    IssueSeverity.ERROR: 12,
    IssueSeverity.WARNING: 3,
    IssueSeverity.INFO: 1,
}


class QualityValidator:
    def validate(self, model: EnterpriseModel) -> QualityReport:
        issues: list[QualityIssue] = []
        for process in model.processes:
            self._validate_process(model, process.id, issues)
        score = self._score(issues)
        return QualityReport(score=score, issues=issues)

    # ------------------------------------------------------------------ #
    # Por proceso
    # ------------------------------------------------------------------ #

    def _validate_process(
        self, model: EnterpriseModel, process_id: str, issues: list[QualityIssue]
    ) -> None:
        related_ids, flows = model.related_to_process(process_id)
        activities = [a for a in model.activities if a.process_id == process_id]
        events = [e for e in model.events if e.id in related_ids]
        gateways = [g for g in model.gateways if g.id in related_ids]

        starts = [e for e in events if e.is_start]
        ends = [e for e in events if e.is_end]

        if not starts:
            issues.append(
                QualityIssue(
                    severity=IssueSeverity.ERROR,
                    code="Q-NO-START",
                    message="El proceso no tiene un StartEvent.",
                    process_id=process_id,
                )
            )
        if not ends:
            issues.append(
                QualityIssue(
                    severity=IssueSeverity.ERROR,
                    code="Q-NO-END",
                    message="El proceso no tiene un EndEvent.",
                    process_id=process_id,
                )
            )

        # Conectividad: BFS desde los starts.
        outgoing: dict[str, list[str]] = defaultdict(list)
        incoming: dict[str, list[str]] = defaultdict(list)
        for flow in flows:
            outgoing[flow.source_id].append(flow.target_id)
            incoming[flow.target_id].append(flow.source_id)

        reachable: set[str] = set()
        queue: deque[str] = deque(s.id for s in starts)
        for s in starts:
            reachable.add(s.id)
        while queue:
            node = queue.popleft()
            for nxt in outgoing[node]:
                if nxt not in reachable:
                    reachable.add(nxt)
                    queue.append(nxt)

        for node_id in related_ids:
            if node_id not in reachable:
                issues.append(
                    QualityIssue(
                        severity=IssueSeverity.ERROR,
                        code="Q-UNREACHABLE",
                        message=f"Nodo '{node_id}' no es alcanzable desde un StartEvent.",
                        process_id=process_id,
                        element_id=node_id,
                    )
                )

        # Huerfanos (sin in/out, excepto start sin in y end sin out).
        for node_id in related_ids:
            ins = incoming[node_id]
            outs = outgoing[node_id]
            is_start = any(e.id == node_id and e.is_start for e in events)
            is_end = any(e.id == node_id and e.is_end for e in events)
            if not ins and not is_start:
                issues.append(
                    QualityIssue(
                        severity=IssueSeverity.WARNING,
                        code="Q-NO-IN",
                        message=f"Nodo '{node_id}' no tiene predecesor.",
                        process_id=process_id,
                        element_id=node_id,
                    )
                )
            if not outs and not is_end:
                issues.append(
                    QualityIssue(
                        severity=IssueSeverity.WARNING,
                        code="Q-NO-OUT",
                        message=f"Nodo '{node_id}' no tiene sucesor.",
                        process_id=process_id,
                        element_id=node_id,
                    )
                )

        # Gateways: deben fork-o-join (al menos 2 in o 2 out).
        for gw in gateways:
            if len(outgoing[gw.id]) < 2 and len(incoming[gw.id]) < 2:
                issues.append(
                    QualityIssue(
                        severity=IssueSeverity.WARNING,
                        code="Q-GATEWAY-NOOP",
                        message=(
                            f"Compuerta '{gw.id}' no se comporta como split ni "
                            "como join (1 entrada, 1 salida)."
                        ),
                        process_id=process_id,
                        element_id=gw.id,
                    )
                )

        # Empresariales por actividad.
        for activity in activities:
            if activity.bpmn_type == BpmnType.USER_TASK and not activity.role_id:
                issues.append(
                    QualityIssue(
                        severity=IssueSeverity.WARNING,
                        code="Q-USERTASK-NO-ROLE",
                        message=f"UserTask '{activity.id}' sin Responsable.",
                        process_id=process_id,
                        element_id=activity.id,
                    )
                )
            if activity.bpmn_type == BpmnType.SERVICE_TASK and not activity.application_ids:
                issues.append(
                    QualityIssue(
                        severity=IssueSeverity.WARNING,
                        code="Q-SERVICETASK-NO-SYSTEM",
                        message=f"ServiceTask '{activity.id}' sin Sistema.",
                        process_id=process_id,
                        element_id=activity.id,
                    )
                )
            if activity.risk_ids and not activity.control_ids:
                issues.append(
                    QualityIssue(
                        severity=IssueSeverity.WARNING,
                        code="Q-RISK-NO-CONTROL",
                        message=(
                            f"Actividad '{activity.id}' declara riesgos sin control declarado."
                        ),
                        process_id=process_id,
                        element_id=activity.id,
                    )
                )

    # ------------------------------------------------------------------ #
    # Score
    # ------------------------------------------------------------------ #

    @staticmethod
    def _score(issues: list[QualityIssue]) -> int:
        penalty = sum(_WEIGHT[i.severity] for i in issues)
        return max(0, 100 - penalty)
