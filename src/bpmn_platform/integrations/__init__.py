"""Capacidades futuras (Fase 11): puntos de extension hacia process mining,
RPA, DMN, IA generativa, Neo4j, simulacion, event-driven, etc.

En esta version solo dejamos las interfaces declaradas para que las
proximas iteraciones puedan colgar implementaciones reales sin romper
la arquitectura existente.
"""
from .stubs import (
    DmnEngineStub,
    EventDrivenStub,
    GenerativeAiStub,
    GraphStoreStub,
    ProcessMiningStub,
    RpaStub,
    SimulationStub,
)

__all__ = [
    "DmnEngineStub",
    "EventDrivenStub",
    "GenerativeAiStub",
    "GraphStoreStub",
    "ProcessMiningStub",
    "RpaStub",
    "SimulationStub",
]
