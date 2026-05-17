"""Vista Inicio: roadmap visible y acciones primarias."""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtSvgWidgets import QSvgWidget
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
from .. import theme


_FASES = [
    ("Fase 1", "Fundaciones", "App PyQt6, multiagente, logging y scripts Windows."),
    ("Fase 2", "Metamodelo Empresarial", "Entidades, relaciones y catálogos controlados."),
    ("Fase 3", "Excel Empresarial", "Plantilla con dropdowns y validaciones."),
    ("Fase 4", "Motor de Parsing", "Excel → EnterpriseModel con detección de issues."),
    ("Fase 5", "Motor Semántico IA", "Inferencias por reglas + Ollama opcional."),
    ("Fase 6", "Generador BPMN 2.0", "XML estándar con BPMNDI y auto-layout."),
    ("Fase 7", "Sistema → Comando", "Trazabilidad tecnológica obligatoria."),
    ("Fase 8", "Validador de Calidad", "Score 0-100 con criterios estructurales."),
    ("Fase 9", "Visualización", "Diagrama SVG con zoom/pan + exportación."),
    ("Fase 10", "Gobierno", "Auditoría JSONL y métricas."),
    ("Fase 11", "Capacidades Futuras", "Process mining, RPA, DMN, Neo4j (stubs)."),
]


def _card(title: str, subtitle: str, body: str) -> QFrame:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setStyleSheet(theme.card_qss())
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(4)
    t = QLabel(title)
    t.setObjectName("card-title")
    s = QLabel(subtitle)
    s.setObjectName("card-subtitle")
    b = QLabel(body)
    b.setObjectName("card-body")
    b.setWordWrap(True)
    layout.addWidget(t)
    layout.addWidget(s)
    layout.addWidget(b)
    return frame


class HomeView(QWidget):
    generate_template_requested = pyqtSignal()
    check_ollama_requested = pyqtSignal()
    load_excel_requested = pyqtSignal()

    def __init__(self, *, catalogs: CatalogBundle | None) -> None:
        super().__init__()
        self._catalogs = catalogs
        self.setStyleSheet(f"QWidget {{ background-color: {theme.GRIS_FONDO}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        # ----- Cabecera con logo Colsubsidio ----- #
        header_bar = QHBoxLayout()
        header_bar.setSpacing(16)
        if theme.ASSET_HEADER.exists():
            logo = QSvgWidget(str(theme.ASSET_HEADER))
            logo.setFixedSize(220, 44)
            header_bar.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel(settings.app_name)
        title.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 22pt; font-weight: bold;"
            f" color: {theme.COLSUBSIDIO_AZUL};"
        )
        subtitle = QLabel(
            "Plataforma BPMN inteligente, multiagente y 100% Open Source. "
            "Convierte Excels empresariales en BPMN 2.0 con gobierno y trazabilidad."
        )
        subtitle.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 11pt; color: {theme.GRIS_TEXTO};"
        )
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_bar.addLayout(title_box, 1)

        # ----- Botonera ----- #
        actions = QHBoxLayout()
        actions.setSpacing(12)

        btn_load = QPushButton("Cargar Excel...")
        btn_load.setMinimumHeight(40)
        btn_load.setStyleSheet(theme.primary_button_qss())
        btn_load.clicked.connect(self.load_excel_requested.emit)

        btn_template = QPushButton("Generar plantilla Excel oficial")
        btn_template.setMinimumHeight(40)
        btn_template.setStyleSheet(theme.secondary_button_qss())
        btn_template.clicked.connect(self.generate_template_requested.emit)

        btn_ollama = QPushButton("Comprobar Ollama (IA local)")
        btn_ollama.setMinimumHeight(40)
        btn_ollama.setStyleSheet(theme.secondary_button_qss())
        btn_ollama.clicked.connect(self.check_ollama_requested.emit)

        actions.addWidget(btn_load)
        actions.addWidget(btn_template)
        actions.addWidget(btn_ollama)
        actions.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        # ----- Roadmap ----- #
        roadmap_title = QLabel("Hoja de ruta de la plataforma")
        roadmap_title.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 13pt; font-weight: bold;"
            f" color: {theme.COLSUBSIDIO_AZUL};"
        )

        grid = QGridLayout()
        grid.setSpacing(12)
        for index, (phase, name, body) in enumerate(_FASES):
            row, col = divmod(index, 3)
            grid.addWidget(_card(phase, name, body), row, col)

        # ----- Estado de catalogos ----- #
        self._catalog_summary = QLabel()
        self._catalog_summary.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 10pt; color: {theme.GRIS_TEXTO};"
        )
        self._refresh_catalog_summary()

        root.addLayout(header_bar)
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
            self._catalog_summary.setText("Estado: catálogos NO cargados.")
            return
        pieces = [f"{name} ({len(c.entries)})" for name, c in self._catalogs.all().items()]
        self._catalog_summary.setText("Catálogos cargados: " + " | ".join(pieces))
