"""Agente semantico (Fase 5).

Aplica heuristicas e inferencias sobre el `EnterpriseModel` recien
parseado. Si Ollama esta disponible y `BPMN_OLLAMA_ENABLED=true`, anade
sugerencias generadas por el LLM local. En caso contrario degrada con
gracia a reglas.

No modifica el modelo: produce sugerencias como issues `[info]`/`[warning]`.
"""
from __future__ import annotations

from ..ai import OllamaClient
from ..config import settings
from ..core.governance import IssueSeverity
from ..core.metamodel import BpmnType
from ..excel.parser import ParseResult
from ..logging_config import get_logger
from .base import Agent, AgentContext, AgentResult

log = get_logger(__name__)


_INFERENCE_PROMPT = """Eres un experto BPMN 2.0. Analiza la siguiente lista de actividades de un proceso y responde con sugerencias breves en espanol, una por linea, con el formato:
ID_ACTIVIDAD: sugerencia.

Actividades:
{activities}

Sugerencias (maximo 5):"""


class SemanticAgent(Agent):
    name = "semantic"

    def __init__(self, ollama: OllamaClient | None = None) -> None:
        self._ollama = ollama

    def run(self, context: AgentContext) -> AgentResult:
        result: ParseResult | None = context.get("parse_result")
        if not result or not result.model.activities:
            return AgentResult(
                name=self.name, ok=True, summary="(skipped) sin actividades parseadas."
            )

        model = result.model
        findings: list[str] = []

        # Regla 1: actividades automaticas con verbo dudoso (revisar, validar ...).
        for activity in model.activities:
            if activity.bpmn_type == BpmnType.SERVICE_TASK and activity.name.lower().startswith(
                ("revisar", "validar", "aprobar", "decidir")
            ):
                findings.append(
                    f"[{IssueSeverity.WARNING.value}] SEM-SERVICE-HUMAN-VERB: "
                    f"ServiceTask '{activity.id}' usa un verbo tipicamente humano "
                    f"('{activity.name}'). Confirmar si deberia ser UserTask."
                )
            if activity.bpmn_type == BpmnType.USER_TASK and any(
                token in activity.name.lower()
                for token in ("ejecutar batch", "correr script", "generar archivo")
            ):
                findings.append(
                    f"[{IssueSeverity.WARNING.value}] SEM-USER-AUTO-VERB: "
                    f"UserTask '{activity.id}' parece automatizable: '{activity.name}'."
                )

        # Regla 2: actividades sin entrada ni salida declarada (input/output).
        flows_in = {f.target_id for f in model.sequence_flows}
        flows_out = {f.source_id for f in model.sequence_flows}
        for activity in model.activities:
            if activity.id not in flows_in and activity.id not in flows_out:
                findings.append(
                    f"[{IssueSeverity.WARNING.value}] SEM-ORPHAN: "
                    f"Actividad '{activity.id}' sin secuencia hacia/desde otros nodos."
                )

        # Regla 3: detectar potenciales bottlenecks por proceso (mas de 1 ServiceTask
        # consecutiva apunta a posible automatizacion total = subprocess).
        from collections import defaultdict

        by_process: dict[str, list] = defaultdict(list)
        for activity in model.activities:
            by_process[activity.process_id].append(activity)
        for proc_id, acts in by_process.items():
            servicios = sum(1 for a in acts if a.bpmn_type == BpmnType.SERVICE_TASK)
            if len(acts) >= 3 and servicios == len(acts):
                findings.append(
                    f"[{IssueSeverity.INFO.value}] SEM-FULL-AUTO: "
                    f"Proceso '{proc_id}' es 100% automatico. "
                    "Considera modelarlo como subprocess."
                )

        # Regla 4 (opcional): consulta Ollama si esta habilitado.
        if settings.ollama_enabled:
            llm_lines = self._ollama_suggestions(model)
            findings.extend(llm_lines)

        return AgentResult(
            name=self.name,
            ok=True,
            summary=f"Inferencias semanticas: {len(findings)} hallazgos.",
            issues=findings,
        )

    # ------------------------------------------------------------------ #
    # Ollama (opcional)
    # ------------------------------------------------------------------ #

    def _ollama_suggestions(self, model) -> list[str]:
        client = self._ollama or OllamaClient()
        status = client.health()
        if not status.available:
            log.info("Ollama no disponible; se omiten sugerencias LLM.")
            return []
        activities_lines = "\n".join(
            f"- {a.id} [{a.bpmn_type.value}]: {a.name}" for a in model.activities[:30]
        )
        try:
            response = client.generate(
                _INFERENCE_PROMPT.format(activities=activities_lines),
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Ollama fallo: {}", exc)
            return []
        out: list[str] = []
        for line in (response or "").splitlines():
            line = line.strip("-• \t")
            if not line:
                continue
            out.append(f"[{IssueSeverity.INFO.value}] SEM-LLM: {line}")
            if len(out) >= 5:
                break
        return out
