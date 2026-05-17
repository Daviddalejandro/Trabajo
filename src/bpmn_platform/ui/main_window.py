"""Ventana principal de la plataforma BPMN (Fase 1)."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..agents import Orchestrator, default_agents
from ..ai import OllamaClient
from ..config import settings
from ..core.catalogs import CatalogBundle, load_catalogs
from ..excel.template_builder import build_template
from ..logging_config import get_logger
from .widgets.about_view import AboutView
from .widgets.catalog_view import CatalogView
from .widgets.home_view import HomeView

log = get_logger(__name__)


_NAV_ITEMS = ("Inicio", "Catalogos", "Acerca de")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{settings.app_name} - v{settings.app_version}")
        self.resize(1180, 760)

        self._catalogs: CatalogBundle | None = None
        self._load_catalogs_safely()

        self._build_actions()
        self._build_menu()
        self._build_central()
        self._build_status_bar()

        # Multiagente disponible desde el dia 1 (esqueleto).
        self._orchestrator = Orchestrator(agents=default_agents())

    # ------------------------------------------------------------------ #
    # Construccion UI
    # ------------------------------------------------------------------ #

    def _build_actions(self) -> None:
        self.act_generate_template = QAction("Generar plantilla Excel...", self)
        self.act_generate_template.setShortcut(QKeySequence("Ctrl+T"))
        self.act_generate_template.triggered.connect(self._on_generate_template)

        self.act_reload_catalogs = QAction("Recargar catalogos", self)
        self.act_reload_catalogs.setShortcut(QKeySequence("F5"))
        self.act_reload_catalogs.triggered.connect(self._on_reload_catalogs)

        self.act_check_ollama = QAction("Comprobar Ollama", self)
        self.act_check_ollama.triggered.connect(self._on_check_ollama)

        self.act_run_pipeline = QAction("Ejecutar pipeline (dry-run)", self)
        self.act_run_pipeline.triggered.connect(self._on_run_pipeline)

        self.act_quit = QAction("Salir", self)
        self.act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_quit.triggered.connect(self.close)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        archivo = menubar.addMenu("&Archivo")
        archivo.addAction(self.act_generate_template)
        archivo.addSeparator()
        archivo.addAction(self.act_quit)

        herramientas = menubar.addMenu("&Herramientas")
        herramientas.addAction(self.act_reload_catalogs)
        herramientas.addAction(self.act_check_ollama)
        herramientas.addAction(self.act_run_pipeline)

    def _build_central(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setFixedWidth(220)
        self.nav.setStyleSheet(
            "QListWidget { background-color: #1F3864; color: white; padding: 12px 0; "
            "border: none; font-size: 14px; }"
            "QListWidget::item { padding: 12px 18px; }"
            "QListWidget::item:selected { background-color: #2E5AAB; }"
        )
        for name in _NAV_ITEMS:
            QListWidgetItem(name, self.nav)
        self.nav.currentRowChanged.connect(self._on_nav_changed)

        self.stack = QStackedWidget()
        self.home_view = HomeView(catalogs=self._catalogs)
        self.catalog_view = CatalogView(catalogs=self._catalogs)
        self.about_view = AboutView()

        self.stack.addWidget(self.home_view)
        self.stack.addWidget(self.catalog_view)
        self.stack.addWidget(self.about_view)

        self.home_view.generate_template_requested.connect(self._on_generate_template)
        self.home_view.check_ollama_requested.connect(self._on_check_ollama)

        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.nav.setCurrentRow(0)

    def _build_status_bar(self) -> None:
        bar = QStatusBar()
        self.setStatusBar(bar)
        self._status_label = QLabel("Listo.")
        bar.addWidget(self._status_label, 1)
        self._catalog_status = QLabel()
        bar.addPermanentWidget(self._catalog_status)
        self._refresh_catalog_status_label()

    # ------------------------------------------------------------------ #
    # Catalogos
    # ------------------------------------------------------------------ #

    def _load_catalogs_safely(self) -> None:
        try:
            self._catalogs = load_catalogs()
            log.info(
                "Catalogos cargados: {}",
                {name: len(c.entries) for name, c in self._catalogs.all().items()},
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("No se pudieron cargar los catalogos.")
            self._catalogs = None
            QMessageBox.warning(
                self,
                "Catalogos",
                f"No se pudieron cargar los catalogos:\n{exc}",
            )

    def _refresh_catalog_status_label(self) -> None:
        if not self._catalogs:
            self._catalog_status.setText("Catalogos: no cargados")
            return
        totals = sum(len(c.entries) for c in self._catalogs.all().values())
        self._catalog_status.setText(f"Catalogos OK ({totals} entradas)")

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #

    def _on_nav_changed(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)

    def _on_generate_template(self) -> None:
        if not self._catalogs:
            QMessageBox.warning(
                self,
                "Plantilla Excel",
                "No se pueden generar plantillas sin catalogos cargados.",
            )
            return

        settings.ensure_dirs()
        default_path = settings.exports_dir / "plantilla_bpmn.xlsx"
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar plantilla BPMN",
            str(default_path),
            "Excel Workbook (*.xlsx)",
        )
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix.lower() != ".xlsx":
            path = path.with_suffix(".xlsx")
        try:
            build_template(path, catalogs=self._catalogs)
        except Exception as exc:  # noqa: BLE001
            log.exception("Fallo generando plantilla.")
            QMessageBox.critical(self, "Plantilla Excel", f"Error generando plantilla:\n{exc}")
            return
        self._status_label.setText(f"Plantilla generada: {path}")
        QMessageBox.information(self, "Plantilla Excel", f"Plantilla creada en:\n{path}")

    def _on_reload_catalogs(self) -> None:
        self._load_catalogs_safely()
        self.home_view.set_catalogs(self._catalogs)
        self.catalog_view.set_catalogs(self._catalogs)
        self._refresh_catalog_status_label()
        self._status_label.setText("Catalogos recargados.")

    def _on_check_ollama(self) -> None:
        status = OllamaClient().health()
        if status.available:
            models = ", ".join(status.models) or "(sin modelos descargados)"
            self._status_label.setText(f"Ollama OK - modelos: {models}")
            QMessageBox.information(
                self,
                "Ollama",
                f"Ollama esta disponible en {status.base_url}.\nModelos: {models}",
            )
        else:
            self._status_label.setText("Ollama no disponible")
            QMessageBox.warning(
                self,
                "Ollama",
                (
                    f"Ollama NO esta disponible en {status.base_url}.\n\n"
                    f"Detalle: {status.error}\n\n"
                    "Sugerencia: instalar Ollama y descargar un modelo, por ejemplo:\n"
                    f"  ollama pull {settings.ollama_model}"
                ),
            )

    def _on_run_pipeline(self) -> None:
        results = self._orchestrator.run()
        ok = sum(1 for r in results if r.ok)
        self._status_label.setText(f"Pipeline ejecutado ({ok}/{len(results)} agentes ok).")
        QMessageBox.information(
            self,
            "Pipeline multiagente (dry-run)",
            "\n".join(f"- [{'OK' if r.ok else 'ERR'}] {r.name}: {r.summary}" for r in results),
        )


def create_main_window() -> MainWindow:
    window = MainWindow()
    window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
    return window
