"""Agente de recomendaciones (Fase 11 — pendiente de profundizacion).

Resume los hallazgos previos y propone acciones priorizadas. Las
recomendaciones se inspiran en process mining cuando este disponible
(futuro); hoy las construye con reglas.
"""
from __future__ import annotations

from collections import Counter

from ..bpmn.quality import QualityReport
from ..core.governance import IssueSeverity
from ..excel.parser import ParseResult
from .base import Agent, AgentContext, AgentResult


class RecommendationAgent(Agent):
    name = "recommendation"

    def run(self, context: AgentContext) -> AgentResult:
        result: ParseResult | None = context.get("parse_result")
        report: QualityReport | None = context.get("quality_report")
        if not result and not report:
            return AgentResult(
                name=self.name, ok=True, summary="(skipped) sin contexto previo."
            )

        recommendations: list[str] = []

        if report:
            counter = Counter(i.code for i in report.issues)
            for code, count in counter.most_common(5):
                if count >= 2:
                    recommendations.append(
                        f"[{IssueSeverity.INFO.value}] REC-PATTERN: el hallazgo '{code}' "
                        f"aparece {count} veces. Considere una correccion masiva."
                    )
            if report.score < 80:
                recommendations.append(
                    f"[{IssueSeverity.WARNING.value}] REC-LOW-SCORE: "
                    f"score de calidad {report.score}/100. "
                    "Priorice corregir errores antes de exportar a BPM Suite."
                )

        if result and result.model.processes:
            recommendations.append(
                f"[{IssueSeverity.INFO.value}] REC-NEXT-PHASE: "
                "Cuando este satisfecho con el BPMN, exporte el XML a su "
                "BPM Suite (Camunda/Flowable) y conecte process mining."
            )

        return AgentResult(
            name=self.name,
            ok=True,
            summary=f"{len(recommendations)} recomendaciones propuestas.",
            issues=recommendations,
        )
