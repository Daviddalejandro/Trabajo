"""Capa Excel: plantilla oficial estructurada (Fase 3)."""
from .schema import ColumnSpec, ExcelSchema, build_default_schema
from .template_builder import build_template

__all__ = ["ColumnSpec", "ExcelSchema", "build_default_schema", "build_template"]
