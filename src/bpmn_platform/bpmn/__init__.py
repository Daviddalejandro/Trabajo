"""Capa BPMN: generador 2.0 XML, layout, validador de calidad, SVG y reporte HTML."""
from .export import render_svg
from .generator import BpmnGenerationResult, BpmnGenerator
from .layout import Layout, compute_layout
from .quality import QualityIssue, QualityReport, QualityValidator
from .report import render_report

__all__ = [
    "BpmnGenerator",
    "BpmnGenerationResult",
    "compute_layout",
    "Layout",
    "render_svg",
    "render_report",
    "QualityValidator",
    "QualityReport",
    "QualityIssue",
]
