"""Vista Inicio: roadmap visible y acciones primarias."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from ...config import settings
from ...core.catalogs import CatalogBundle


_PHASES = [
    ("Fase 1", "Fundaciones del Proyecto", "Arquitectura, stack OSS, app Windows."),
    ("Fase 2", "Metamodelo Empresarial", "Entidades, relaciones, catalogos."),
    ("Fase 3", "Excel Empresarial", "Plantilla controlada con validaciones."),
    ("Fase 4", "Motor de Parsing", "Lectura Excel y normalizacion (siguiente)."),
    ("Fase 5", "Motor Semantico IA", "Inferencia BPMN con Ollama (siguiente)."),
    ("Fase 6", "Generador BPMN", "BPMN 2.0 XML (siguiente)."),
]


def _card(title: str, subtitle: str, body: str) -> QFrame:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setStyleSheet(
        "QFrame { background-color: white; border: 1px solid #D0D7E2; border-radius: 8px; }"
        "QLabel#title { color: #1F3864; font-size: 12pt; font-weight: bold; }"
        "QLabel#subtitle { color: #2E5AAB; font-size: 11pt; font-weight: 600; }"
        "QLabel#body { color: #444; font-size: 10pt; }"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(4)
    t = QLabel(title); t.setObjectName("title")
    s = QLabel(subtitle); s.setObjectName("subtitle")
    b = QLabel(body); b.setObjectName("body"); b.setWordWrap(True)
    layout.addWidget(t)
    layout.addWidget(s)
    layout.addWidget(b)
    return frame


class HomeView(QWidget):
    generate_template_requested = pyqtSignal()
    check_ollama_requested = pyqtSignal()

    def __init__(self, *, catalogs: CatalogBundle | None) -> None:
        super().__init__()
        self._catalogs = catalogs
        self.setStyleSheet("QWidget { background-color: #F4F6FA; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        header = QLabel(f"{settings.app_name}")
        header.setStyleSheet("font-size: 22pt; font-weight: bold; color: #1F3864;")
        subtitle = QLabel(
            "Plataforma BPMN inteligente, multiagente y 100% Open Source. "
            "Convierte Excels empresariales estructurados en BPMN 2.0 con gobierno."
        )
        subtitle.setStyleSheet("font-size: 11pt; color: #404040;")
        subtitle.setWordWrap(True)

        # Acciones
        actions = QHBoxLayout()
        actions.setSpacing(12)
        btn_template = QPushButton("Generar plantilla Excel oficial")
        btn_template.setMinimumHeight(40)
        btn_template.setStyleSheet(
            "QPushButton { background-color: #1F3864; color: white; font-weight: bold;"
            " padding: 8px 18px; border-radius: 6px; }"
            "QPushButton:hover { background-color: #2E5AAB; }"
        )
        btn_template.clicked.connect(self.generate_template_requested.emit)

        btn_ollama = QPushButton("Comprobar Ollama")
        btn_ollama.setMinimumHeight(40)
        btn_ollama.setStyleSheet(
            "QPushButton { background-color: white; color: #1F3864; font-weight: bold;"
            " padding: 8px 18px; border: 1px solid #1F3864; border-radius: 6px; }"
            "QPushButton:hover { background-color: #E8EEF7; }"
        )
        btn_ollama.clicked.connect(self.check_ollama_requested.emit)

        actions.addWidget(btn_template)
        actions.addWidget(btn_ollama)
        actions.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        # Roadmap en grid de tarjetas
        roadmap_title = QLabel("Roadmap de la plataforma")
        roadmap_title.setStyleSheet("font-size: 13pt; font-weight: bold; color: #1F3864;")

        grid = QGridLayout()
        grid.setSpacing(12)
        for index, (phase, name, body) in enumerate(_PHASES):
            row, col = divmod(index, 3)
            grid.addWidget(_card(phase, name, body), row, col)

        # Estado catalogos
        self._catalog_summary = QLabel()
        self._catalog_summary.setStyleSheet("font-size: 10pt; color: #404040;")
        self._refresh_catalog_summary()

        root.addWidget(header)
        root.addWidget(subtitle)
        root.addLayout(actions)
        root.addWidget(roadmap_title)
        root.addLayout(grid)
        root.addWidget(self._catalog_summary)
        root.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def set_catalogs(self, catalogs: CatalogBundle | None) -> None:
        self._catalogs = catalogs
        self._refresh_catalog_summary()

    def _refresh_catalog_summary(self) -> None:
        if not self._catalogs:
            self._catalog_summary.setText("Estado: catalogos NO cargados.")
            return
        pieces = [f"{name} ({len(c.entries)})" for name, c in self._catalogs.all().items()]
        self._catalog_summary.setText("Catalogos cargados: " + " | ".join(pieces))
