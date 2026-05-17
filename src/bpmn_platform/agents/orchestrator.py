"""Orquestador secuencial de agentes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..logging_config import get_logger
from .base import Agent, AgentContext, AgentResult

log = get_logger(__name__)


@dataclass
class Orchestrator:
    agents: list[Agent] = field(default_factory=list)
    stop_on_error: bool = False

    def register(self, agent: Agent) -> None:
        self.agents.append(agent)

    def register_all(self, agents: Iterable[Agent]) -> None:
        for agent in agents:
            self.register(agent)

    def run(self, context: AgentContext | None = None) -> list[AgentResult]:
        context = context or AgentContext()
        results: list[AgentResult] = []
        for agent in self.agents:
            log.info("Ejecutando agente: {}", agent.name)
            try:
                result = agent.run(context)
            except Exception as exc:  # noqa: BLE001
                log.exception("Agente '{}' fallo", agent.name)
                result = AgentResult(name=agent.name, ok=False, summary=str(exc))
            results.append(result)
            context.issues.extend(result.issues)
            if not result.ok and self.stop_on_error:
                log.warning("Pipeline detenido por error en {}", agent.name)
                break
        return results
