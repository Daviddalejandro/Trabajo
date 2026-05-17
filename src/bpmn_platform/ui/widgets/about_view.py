"""Vista 'Acerca de': información del proyecto y stack."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ...config import settings
from .. import theme


_STACK = (
    "• PyQt6 — UI de escritorio Windows.",
    "• openpyxl — plantilla Excel oficial con dropdowns.",
    "• Pydantic v2 — metamodelo empresarial.",
    "• PyYAML — catálogos controlados.",
    "• loguru — logging y observabilidad.",
    "• Ollama + httpx — motor IA local (offline-first).",
    "• lxml — generador BPMN 2.0 XML.",
)


class AboutView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"QWidget {{ background-color: {theme.GRIS_FONDO}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        header_bar = QHBoxLayout()
        header_bar.setSpacing(16)
        if theme.ASSET_HEADER.exists():
            logo = QSvgWidget(str(theme.ASSET_HEADER))
            logo.setFixedSize(260, 52)
            header_bar.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        title_box = QVBoxLayout()
        title = QLabel(settings.app_name)
        title.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 22pt; font-weight: bold;"
            f" color: {theme.COLSUBSIDIO_AZUL};"
        )
        version = QLabel(f"Versión {settings.app_version}")
        version.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 11pt; color: {theme.GRIS_TEXTO};"
        )
        title_box.addWidget(title)
        title_box.addWidget(version)
        header_bar.addLayout(title_box, 1)

        description = QLabel(
            "Plataforma BPMN inteligente, multiagente y 100% Open Source.\n\n"
            "Esta versión implementa las 11 fases del documento maestro:\n"
            "  • Fundaciones, metamodelo y Excel oficial.\n"
            "  • Parser, motor semántico y generador BPMN 2.0.\n"
            "  • Validador de calidad, visualización SVG y exportación.\n"
            "  • Gobierno con auditoría y stubs de integraciones futuras."
        )
        description.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 11pt; color: {theme.NEGRO};"
        )
        description.setWordWrap(True)

        stack_title = QLabel("Stack tecnológico (Open Source)")
        stack_title.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 13pt; font-weight: bold;"
            f" color: {theme.COLSUBSIDIO_AZUL};"
        )

        stack = QLabel("\n".join(_STACK))
        stack.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 11pt; color: {theme.NEGRO};"
        )

        footer_bar = QHBoxLayout()
        if theme.ASSET_FOOTER.exists():
            footer = QSvgWidget(str(theme.ASSET_FOOTER))
            footer.setFixedHeight(48)
            footer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            footer_bar.addWidget(footer)

        root.addLayout(header_bar)
        root.addWidget(description)
        root.addWidget(stack_title)
        root.addWidget(stack)
        root.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        root.addLayout(footer_bar)
