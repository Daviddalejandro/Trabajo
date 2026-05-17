"""Reglas de gobierno y validacion semantica reusables.

En esta fase (1-3) solo materializamos las validaciones que ya son utiles
para el Excel oficial (nomenclatura, IDs unicos, valores contra catalogos).
Las validaciones BPMN profundas (conectividad, gateways balanceados, etc.)
se construiran en la Fase 8.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class IssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class GovernanceIssue:
    code: str
    severity: IssueSeverity
    message: str
    location: str | None = None


# Verbos en infinitivo aceptados (no exhaustivo: se amplia con uso real).
_VERB_PATTERN = re.compile(
    r"^(?:[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]+)"  # primera palabra capitalizada
    r"(?:ar|er|ir)\b",                       # terminacion infinitivo en espanol
    re.UNICODE,
)


def validate_activity_name(name: str, location: str | None = None) -> list[GovernanceIssue]:
    """Aplica la regla de nomenclatura `Verbo + Objeto [+ Contexto]`."""
    issues: list[GovernanceIssue] = []
    cleaned = (name or "").strip()
    if not cleaned:
        issues.append(
            GovernanceIssue(
                code="NAME-EMPTY",
                severity=IssueSeverity.ERROR,
                message="El nombre de la actividad esta vacio.",
                location=location,
            )
        )
        return issues

    tokens = cleaned.split()
    if len(tokens) < 2:
        issues.append(
            GovernanceIssue(
                code="NAME-TOO-SHORT",
                severity=IssueSeverity.ERROR,
                message=(
                    "El nombre debe seguir el formato 'Verbo + Objeto [+ Contexto]' "
                    "(minimo 2 palabras)."
                ),
                location=location,
            )
        )
        return issues

    if not _VERB_PATTERN.match(cleaned):
        issues.append(
            GovernanceIssue(
                code="NAME-NO-VERB",
                severity=IssueSeverity.WARNING,
                message=(
                    "El nombre deberia iniciar con un verbo en infinitivo "
                    "(ej. 'Validar identidad cliente')."
                ),
                location=location,
            )
        )

    if cleaned[0].islower():
        issues.append(
            GovernanceIssue(
                code="NAME-CAPITALIZATION",
                severity=IssueSeverity.WARNING,
                message="El nombre deberia comenzar con mayuscula.",
                location=location,
            )
        )

    return issues
