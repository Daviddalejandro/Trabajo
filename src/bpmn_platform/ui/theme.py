"""Paleta y tokens de diseño Colsubsidio.

Fuente: assets oficiales (`encabezado_colsubsidio.svg`, `pie_pagina_colsubsidio.svg`).
Marca: azul corporativo y amarillo geometrico.

Estos tokens se usan tanto en la UI PyQt6 como en el renderizador SVG BPMN.
"""
from __future__ import annotations

from pathlib import Path


# --- Marca Colsubsidio --------------------------------------------------- #

COLSUBSIDIO_AZUL = "#0067B1"
COLSUBSIDIO_AMARILLO = "#FFD000"

# Variantes derivadas (oscuro/claro) para estados hover/disabled.
AZUL_OSCURO = "#004F8C"     # hover sobre botones primarios
AZUL_CLARO = "#E8F1F9"      # background sutil tipo banner
AZUL_MUY_CLARO = "#F4F8FC"  # background general

AMARILLO_CLARO = "#FFF4B8"  # background sutil de avisos
AMARILLO_OSCURO = "#CC9C00"

# --- Neutros ------------------------------------------------------------- #

BLANCO = "#FFFFFF"
NEGRO = "#1A1A1A"
GRIS_TEXTO = "#404040"
GRIS_SECUNDARIO = "#6B6B6B"
GRIS_BORDE = "#CDD7E3"
GRIS_FONDO = "#F4F6FA"

# --- Semaforo de issues -------------------------------------------------- #

ERROR_BG = "#FFD6D6"
ERROR_FG = "#B71C1C"
WARNING_BG = "#FFF1C2"
WARNING_FG = "#CC8400"
INFO_BG = "#D9E5FF"
INFO_FG = "#1565C0"
OK_FG = "#2E7D32"


# --- Tipografia ---------------------------------------------------------- #

FONT_FAMILY = "Segoe UI, Roboto, sans-serif"


# --- Recursos de marca --------------------------------------------------- #

# Los SVG viven dentro del paquete (`ui/resources/`) para que PyInstaller
# los empaquete correctamente. En modo editable tambien funciona.
_RESOURCES_DIR = Path(__file__).resolve().parent / "resources"
ASSET_HEADER = _RESOURCES_DIR / "encabezado_colsubsidio.svg"
ASSET_FOOTER = _RESOURCES_DIR / "pie_pagina_colsubsidio.svg"


# --- Hojas de estilo Qt -------------------------------------------------- #

def main_window_qss() -> str:
    return f"""
        QMainWindow {{ background-color: {GRIS_FONDO}; }}
        QMenuBar {{
            background-color: {COLSUBSIDIO_AZUL};
            color: {BLANCO};
            font-family: {FONT_FAMILY};
            font-size: 11pt;
        }}
        QMenuBar::item:selected {{ background-color: {AZUL_OSCURO}; }}
        QMenu {{ background-color: {BLANCO}; color: {NEGRO}; border: 1px solid {GRIS_BORDE}; }}
        QMenu::item:selected {{ background-color: {COLSUBSIDIO_AZUL}; color: {BLANCO}; }}
        QStatusBar {{
            background-color: {BLANCO};
            color: {GRIS_TEXTO};
            border-top: 2px solid {COLSUBSIDIO_AMARILLO};
        }}
    """


def navigation_qss() -> str:
    return f"""
        QListWidget {{
            background-color: {COLSUBSIDIO_AZUL};
            color: {BLANCO};
            padding: 12px 0;
            border: none;
            font-family: {FONT_FAMILY};
            font-size: 12pt;
        }}
        QListWidget::item {{ padding: 12px 18px; }}
        QListWidget::item:selected {{
            background-color: {AZUL_OSCURO};
            border-left: 4px solid {COLSUBSIDIO_AMARILLO};
        }}
        QListWidget::item:hover {{ background-color: {AZUL_OSCURO}; }}
    """


def primary_button_qss() -> str:
    return f"""
        QPushButton {{
            background-color: {COLSUBSIDIO_AZUL};
            color: {BLANCO};
            font-weight: bold;
            padding: 8px 18px;
            border-radius: 6px;
            border: 0;
        }}
        QPushButton:hover {{ background-color: {AZUL_OSCURO}; }}
        QPushButton:disabled {{ background-color: {GRIS_BORDE}; color: {GRIS_SECUNDARIO}; }}
    """


def secondary_button_qss() -> str:
    return f"""
        QPushButton {{
            background-color: {BLANCO};
            color: {COLSUBSIDIO_AZUL};
            font-weight: bold;
            padding: 8px 18px;
            border: 1px solid {COLSUBSIDIO_AZUL};
            border-radius: 6px;
        }}
        QPushButton:hover {{ background-color: {AZUL_CLARO}; }}
    """


def accent_button_qss() -> str:
    """Boton de acento amarillo Colsubsidio (para llamados a la accion)."""
    return f"""
        QPushButton {{
            background-color: {COLSUBSIDIO_AMARILLO};
            color: {NEGRO};
            font-weight: bold;
            padding: 8px 18px;
            border-radius: 6px;
            border: 0;
        }}
        QPushButton:hover {{ background-color: {AMARILLO_OSCURO}; color: {BLANCO}; }}
    """


def table_qss() -> str:
    return f"""
        QTableWidget {{
            background-color: {BLANCO};
            gridline-color: {GRIS_BORDE};
            font-family: {FONT_FAMILY};
        }}
        QHeaderView::section {{
            background-color: {COLSUBSIDIO_AZUL};
            color: {BLANCO};
            padding: 6px;
            border: 0;
            font-weight: bold;
        }}
    """


def card_qss() -> str:
    return f"""
        QFrame {{
            background-color: {BLANCO};
            border: 1px solid {GRIS_BORDE};
            border-radius: 8px;
        }}
        QLabel#card-title {{ color: {COLSUBSIDIO_AZUL}; font-size: 12pt; font-weight: bold; }}
        QLabel#card-subtitle {{ color: {AZUL_OSCURO}; font-size: 11pt; font-weight: 600; }}
        QLabel#card-body {{ color: {GRIS_TEXTO}; font-size: 10pt; }}
    """
