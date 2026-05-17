"""Stubs de integracion declarativos para la Fase 11.

Cada stub define el contrato esperado y lanza NotImplementedError. El
objetivo es que cuando alguien quiera implementar una integracion
concreta (Camunda, Celonis, Power Automate, Neo4j, etc.) tenga el
contrato listo y los tests pueden mockearlos con seguridad.
"""
from __future__ import annotations

from typing import Any, Protocol


class ProcessMiningStub(Protocol):
    """Adapter futuro hacia process mining (Celonis, Disco, ProM, ...)."""

    def ingest_event_log(self, source: Any) -> None: ...
    def discover_process(self) -> Any: ...
    def compare_with(self, model: Any) -> Any: ...


class RpaStub(Protocol):
    """Adapter futuro hacia RPA (UiPath, Power Automate, Robocorp, ...)."""

    def map_activity_to_bot(self, activity_id: str, bot_ref: str) -> None: ...
    def trigger(self, activity_id: str, payload: dict[str, Any]) -> Any: ...


class DmnEngineStub(Protocol):
    """Adapter futuro hacia un motor DMN (Camunda DMN, OpenRules, ...)."""

    def evaluate(self, decision_id: str, inputs: dict[str, Any]) -> Any: ...


class GenerativeAiStub(Protocol):
    """Adapter futuro hacia IA generativa avanzada (mas alla de Ollama local)."""

    def explain(self, model: Any) -> str: ...
    def propose_subprocess(self, activities: list[Any]) -> Any: ...


class GraphStoreStub(Protocol):
    """Adapter futuro hacia un graph store (Neo4j, JanusGraph, ...)."""

    def upsert_model(self, model: Any) -> None: ...
    def query(self, cypher: str) -> Any: ...


class SimulationStub(Protocol):
    """Adapter futuro hacia simulacion BPMN (Bizagi Modeler, BIMP, ...)."""

    def simulate(self, model: Any, scenario: dict[str, Any]) -> Any: ...


class EventDrivenStub(Protocol):
    """Adapter futuro hacia event-driven architecture (Kafka, NATS, ...)."""

    def publish(self, topic: str, event: dict[str, Any]) -> None: ...
    def subscribe(self, topic: str, handler: Any) -> None: ...
