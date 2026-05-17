"""Registro canonico de agentes (todos reales tras Fases 5-9)."""
from __future__ import annotations

from .base import Agent


def default_agents() -> list[Agent]:
    """Pipeline canonico: parser -> validation -> semantic -> bpmn ->
    quality -> governance -> metadata -> export -> recommendation."""
    from .bpmn_agent import BpmnAgent
    from .export_agent import ExportAgent
    from .governance_agent import GovernanceAgent
    from .metadata_agent import MetadataAgent
    from .parser_agent import ParserAgent
    from .quality_agent import QualityAgent
    from .recommendation_agent import RecommendationAgent
    from .semantic_agent import SemanticAgent
    from .validation_agent import ValidationAgent

    return [
        ParserAgent(),
        ValidationAgent(),
        SemanticAgent(),
        BpmnAgent(),
        QualityAgent(),
        GovernanceAgent(),
        MetadataAgent(),
        ExportAgent(),
        RecommendationAgent(),
    ]
