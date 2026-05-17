"""Interfaces base de la arquitectura multiagente."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentContext:
    """Estado compartido entre agentes."""

    payload: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        self.payload[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.payload.get(key, default)


@dataclass
class AgentResult:
    name: str
    ok: bool
    summary: str
    issues: list[str] = field(default_factory=list)


class Agent(ABC):
    """Contrato comun a todos los agentes especializados."""

    name: str = "agent"

    @abstractmethod
    def run(self, context: AgentContext) -> AgentResult: ...
