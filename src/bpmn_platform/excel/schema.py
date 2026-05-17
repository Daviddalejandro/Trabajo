"""Definicion declarativa del Excel oficial.

El archivo Excel NO admite texto libre arbitrario: cada columna tiene un
tipo, un help text, y opcionalmente una fuente de valores (catalogo).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CellKind(str, Enum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    ID = "id"
    DROPDOWN = "dropdown"
    DURATION = "duration"
    NUMBER = "number"
    LIST = "list"  # valores separados por ';'


@dataclass(frozen=True)
class ColumnSpec:
    key: str                       # nombre interno (snake_case)
    header: str                    # encabezado visible
    kind: CellKind
    required: bool = False
    catalog: str | None = None     # nombre del catalogo (si kind=DROPDOWN/LIST)
    help_text: str = ""
    width: int = 22


@dataclass(frozen=True)
class ExcelSchema:
    process_sheet: str
    activities_sheet: str
    catalogs_sheet: str
    instructions_sheet: str
    process_columns: tuple[ColumnSpec, ...]
    activity_columns: tuple[ColumnSpec, ...]


def build_default_schema() -> ExcelSchema:
    """Schema canonico del Excel oficial."""

    process_columns = (
        ColumnSpec(
            key="process_id",
            header="ID Proceso",
            kind=CellKind.ID,
            required=True,
            help_text="Identificador unico del proceso (ej. PROC-001).",
            width=14,
        ),
        ColumnSpec(
            key="process_name",
            header="Nombre del Proceso",
            kind=CellKind.TEXT,
            required=True,
            help_text="Nombre legible (ej. 'Onboarding de clientes').",
            width=36,
        ),
        ColumnSpec(
            key="domain",
            header="Dominio",
            kind=CellKind.TEXT,
            help_text="Dominio o area de negocio (ej. 'Riesgos', 'Operaciones').",
            width=22,
        ),
        ColumnSpec(
            key="owner_role",
            header="Owner (Rol)",
            kind=CellKind.DROPDOWN,
            catalog="roles",
            help_text="Rol responsable del proceso (catalogo Roles).",
            width=24,
        ),
        ColumnSpec(
            key="version",
            header="Version",
            kind=CellKind.TEXT,
            help_text="Version del proceso (ej. 1.0.0).",
            width=12,
        ),
        ColumnSpec(
            key="description",
            header="Descripcion",
            kind=CellKind.LONG_TEXT,
            help_text="Resumen ejecutivo del proceso.",
            width=60,
        ),
    )

    activity_columns = (
        ColumnSpec(
            key="activity_id",
            header="ID",
            kind=CellKind.ID,
            required=True,
            help_text="ID unico (ej. ACT-001). No se permiten duplicados.",
            width=12,
        ),
        ColumnSpec(
            key="process_id",
            header="ID Proceso",
            kind=CellKind.ID,
            required=True,
            help_text="ID del proceso al que pertenece la actividad.",
            width=14,
        ),
        ColumnSpec(
            key="bpmn_type",
            header="Tipo BPMN",
            kind=CellKind.DROPDOWN,
            catalog="bpmn_types",
            required=True,
            help_text="Tipo BPMN (catalogo controlado).",
            width=22,
        ),
        ColumnSpec(
            key="activity_name",
            header="Actividad",
            kind=CellKind.TEXT,
            required=True,
            help_text="Verbo + Objeto [+ Contexto]. Ej. 'Validar identidad cliente'.",
            width=38,
        ),
        ColumnSpec(
            key="role",
            header="Responsable",
            kind=CellKind.DROPDOWN,
            catalog="roles",
            help_text="Rol responsable de la actividad (catalogo Roles).",
            width=24,
        ),
        ColumnSpec(
            key="system",
            header="Sistema",
            kind=CellKind.DROPDOWN,
            catalog="systems",
            help_text="Sistema/aplicacion (catalogo). Regla: Actividad -> Sistema -> Comando.",
            width=22,
        ),
        ColumnSpec(
            key="command",
            header="Comando",
            kind=CellKind.TEXT,
            help_text=(
                "Comando/script ejecutado por el Sistema (ej. 'python reconcile.py')."
                " Debe pertenecer al Sistema indicado."
            ),
            width=32,
        ),
        ColumnSpec(
            key="api",
            header="API",
            kind=CellKind.TEXT,
            help_text="Identificador o endpoint de la API si aplica.",
            width=28,
        ),
        ColumnSpec(
            key="input",
            header="Entrada",
            kind=CellKind.TEXT,
            help_text="Insumo de la actividad (DataObject / activo de informacion).",
            width=26,
        ),
        ColumnSpec(
            key="output",
            header="Salida",
            kind=CellKind.TEXT,
            help_text="Resultado producido por la actividad.",
            width=26,
        ),
        ColumnSpec(
            key="information_asset",
            header="Activo Informacion",
            kind=CellKind.TEXT,
            help_text="Activo de informacion principal asociado.",
            width=26,
        ),
        ColumnSpec(
            key="risk",
            header="Riesgo",
            kind=CellKind.DROPDOWN,
            catalog="risks",
            help_text="Riesgo principal (catalogo Riesgos).",
            width=28,
        ),
        ColumnSpec(
            key="control",
            header="Control",
            kind=CellKind.DROPDOWN,
            catalog="controls",
            help_text="Control que mitiga el riesgo (catalogo Controles).",
            width=28,
        ),
        ColumnSpec(
            key="sla",
            header="SLA",
            kind=CellKind.DURATION,
            help_text="SLA objetivo (ej. '2h', '30m', '1d').",
            width=10,
        ),
        ColumnSpec(
            key="kpi",
            header="KPI",
            kind=CellKind.TEXT,
            help_text="KPI asociado a la actividad.",
            width=24,
        ),
        ColumnSpec(
            key="observations",
            header="Observaciones",
            kind=CellKind.LONG_TEXT,
            help_text="Notas adicionales para el agente semantico.",
            width=44,
        ),
        ColumnSpec(
            key="predecessors",
            header="Predecesor",
            kind=CellKind.TEXT,
            help_text=(
                "ID(s) del/los nodo(s) que preceden a este. Separe varios con ';'. "
                "Si se deja vacio, se asume la fila anterior del mismo proceso."
            ),
            width=20,
        ),
    )

    return ExcelSchema(
        process_sheet="Proceso",
        activities_sheet="Actividades",
        catalogs_sheet="Catalogos",
        instructions_sheet="Instrucciones",
        process_columns=process_columns,
        activity_columns=activity_columns,
    )
