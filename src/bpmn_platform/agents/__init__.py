"""Esqueleto de la arquitectura multiagente (Fase 1).

Cada agente especializado se registra contra el `Orchestrator`, el cual
ejecuta una pipeline ordenada y propaga un `AgentContext` compartido.

Las implementaciones reales se completan en fases posteriores
(parser fase 4, semantico fase 5, BPMN fase 6, etc.); aqui solo dejamos
las interfaces y un orquestador funcional para mantener consistencia
arquitectonica desde el dia 1.
"""
from .base import Agent, AgentContext, AgentResult
from .orchestrator import Orchestrator
from .registry import default_agents

__all__ = ["Agent", "AgentContext", "AgentResult", "Orchestrator", "default_agents"]
