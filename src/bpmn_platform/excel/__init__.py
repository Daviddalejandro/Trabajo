"""Capa Excel: plantilla oficial estructurada y parser (Fases 3 y 4)."""
from .parser import ExcelParser, ParseIssue, ParseResult
from .schema import ColumnSpec, ExcelSchema, build_default_schema
from .template_builder import build_template

__all__ = [
    "ColumnSpec",
    "ExcelSchema",
    "build_default_schema",
    "build_template",
    "ExcelParser",
    "ParseIssue",
    "ParseResult",
]
