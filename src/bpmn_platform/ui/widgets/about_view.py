"""Vista 'Acerca de': informacion del proyecto y stack."""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget

from ...config import settings


_STACK = (
    "* PyQt6 (UI desktop Windows).",
    "* openpyxl (plantilla Excel oficial con dropdowns).",
    "* pydantic v2 (metamodelo empresarial).",
    "* PyYAML (catalogos controlados).",
    "* loguru (logging + observabilidad).",
    "* Ollama + httpx (motor IA local, offline-first).",
    "* lxml (BPMN 2.0 XML, fase 6).",
)


class AboutView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet("QWidget { background-color: #F4F6FA; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel(f"{settings.app_name}")
        title.setStyleSheet("font-size: 22pt; font-weight: bold; color: #1F3864;")
        version = QLabel(f"Version {settings.app_version}")
        version.setStyleSheet("font-size: 11pt; color: #404040;")

        description = QLabel(
            "Plataforma BPMN inteligente, multiagente y 100% Open Source.\n\n"
            "Esta version implementa las Fases 1-3 del documento maestro:\n"
            "  - Fundaciones (stack, logging, multiagente, app Windows).\n"
            "  - Metamodelo empresarial (Pydantic, catalogos YAML).\n"
            "  - Plantilla Excel oficial con validaciones y dropdowns.\n"
        )
        description.setStyleSheet("font-size: 11pt; color: #303030;")
        description.setWordWrap(True)

        stack_title = QLabel("Stack tecnologico")
        stack_title.setStyleSheet("font-size: 13pt; font-weight: bold; color: #1F3864;")

        stack = QLabel("\n".join(_STACK))
        stack.setStyleSheet("font-size: 11pt; color: #303030;")

        root.addWidget(title)
        root.addWidget(version)
        root.addWidget(description)
        root.addWidget(stack_title)
        root.addWidget(stack)
        root.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
