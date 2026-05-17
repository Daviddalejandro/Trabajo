"""Ventana principal de la plataforma BPMN."""
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

from ..agents import AgentContext, Orchestrator, default_agents
from ..ai import OllamaClient
from ..bpmn import render_svg
from ..config import settings
from ..core.catalogs import CatalogBundle, load_catalogs
from ..excel.parser import ExcelParser
from ..excel.template_builder import build_template
from ..logging_config import get_logger
from . import theme
from .widgets.about_view import AboutView
from .widgets.bpmn_view import BpmnView
from .widgets.catalog_view import CatalogView
from .widgets.home_view import HomeView
from .widgets.issues_view import IssuesView

log = get_logger(__name__)


_NAV_ITEMS = ("Inicio", "Diagrama BPMN", "Resultados", "Catálogos", "Acerca de")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{settings.app_name} — v{settings.app_version}")
        self.resize(1300, 820)
        self.setStyleSheet(theme.main_window_qss())

        self._catalogs: CatalogBundle | None = None
        self._load_catalogs_safely()

        self._last_parse_result = None
        self._last_bpmn_result = None
        self._last_export_files: list[Path] = []

        self._build_actions()
        self._build_menu()
        self._build_central()
        self._build_status_bar()

        self._orchestrator = Orchestrator(agents=default_agents())

    # ------------------------------------------------------------------ #
    # Construccion UI
    # ------------------------------------------------------------------ #

    def _build_actions(self) -> None:
        self.act_generate_template = QAction("Generar plantilla Excel...", self)
        self.act_generate_template.setShortcut(QKeySequence("Ctrl+T"))
        self.act_generate_template.triggered.connect(self._on_generate_template)

        self.act_load_excel = QAction("Cargar Excel...", self)
        self.act_load_excel.setShortcut(QKeySequence.StandardKey.Open)
        self.act_load_excel.triggered.connect(self._on_load_excel)

        self.act_export_bpmn = QAction("Exportar BPMN / SVG / JSON...", self)
        self.act_export_bpmn.setShortcut(QKeySequence("Ctrl+E"))
        self.act_export_bpmn.triggered.connect(self._on_export_bpmn)
        self.act_export_bpmn.setEnabled(False)

        self.act_reload_catalogs = QAction("Recargar catálogos", self)
        self.act_reload_catalogs.setShortcut(QKeySequence("F5"))
        self.act_reload_catalogs.triggered.connect(self._on_reload_catalogs)

        self.act_check_ollama = QAction("Comprobar Ollama (IA local)", self)
        self.act_check_ollama.triggered.connect(self._on_check_ollama)

        self.act_quit = QAction("Salir", self)
        self.act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_quit.triggered.connect(self.close)

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        archivo = menubar.addMenu("&Archivo")
        archivo.addAction(self.act_load_excel)
        archivo.addAction(self.act_generate_template)
        archivo.addAction(self.act_export_bpmn)
        archivo.addSeparator()
        archivo.addAction(self.act_quit)

        herramientas = menubar.addMenu("&Herramientas")
        herramientas.addAction(self.act_reload_catalogs)
        herramientas.addAction(self.act_check_ollama)

    def _build_central(self) -> None:
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.nav = QListWidget()
        self.nav.setFixedWidth(220)
        self.nav.setStyleSheet(theme.navigation_qss())
        for name in _NAV_ITEMS:
            QListWidgetItem(name, self.nav)
        self.nav.currentRowChanged.connect(self._on_nav_changed)

        self.stack = QStackedWidget()
        self.home_view = HomeView(catalogs=self._catalogs)
        self.bpmn_view = BpmnView()
        self.issues_view = IssuesView()
        self.catalog_view = CatalogView(catalogs=self._catalogs)
        self.about_view = AboutView()

        for widget in (
            self.home_view,
            self.bpmn_view,
            self.issues_view,
            self.catalog_view,
            self.about_view,
        ):
            self.stack.addWidget(widget)

        self.home_view.generate_template_requested.connect(self._on_generate_template)
        self.home_view.check_ollama_requested.connect(self._on_check_ollama)
        self.home_view.load_excel_requested.connect(self._on_load_excel)

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
            self._catalog_status.setText("Catálogos: no cargados")
            return
        totals = sum(len(c.entries) for c in self._catalogs.all().values())
        self._catalog_status.setText(f"Catálogos OK ({totals} entradas)")

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
                "No se pueden generar plantillas sin catálogos cargados.",
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
        self._status_label.setText("Catálogos recargados.")

    def _on_check_ollama(self) -> None:
        status = OllamaClient().health()
        if status.available:
            models = ", ".join(status.models) or "(sin modelos descargados)"
            self._status_label.setText(f"Ollama OK — modelos: {models}")
            QMessageBox.information(
                self,
                "Ollama",
                f"Ollama está disponible en {status.base_url}.\nModelos: {models}",
            )
        else:
            self._status_label.setText("Ollama no disponible")
            QMessageBox.warning(
                self,
                "Ollama",
                (
                    f"Ollama NO está disponible en {status.base_url}.\n\n"
                    f"Detalle: {status.error}\n\n"
                    "Sugerencia: instalar Ollama y descargar un modelo, por ejemplo:\n"
                    f"  ollama pull {settings.ollama_model}"
                ),
            )

    def _on_load_excel(self) -> None:
        if not self._catalogs:
            QMessageBox.warning(
                self,
                "Cargar Excel",
                "No se pueden parsear plantillas sin catálogos cargados.",
            )
            return
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Cargar plantilla BPMN",
            str(settings.exports_dir),
            "Excel Workbook (*.xlsx)",
        )
        if not path_str:
            return
        try:
            parser = ExcelParser(catalogs=self._catalogs)
            result = parser.parse(Path(path_str))
        except Exception as exc:  # noqa: BLE001
            log.exception("Fallo parseando Excel.")
            QMessageBox.critical(self, "Cargar Excel", f"Error parseando:\n{exc}")
            return

        context = AgentContext()
        context.set("excel_path", path_str)
        context.set("parse_result", result)
        context.set("enterprise_model", result.model)
        pipeline_results = self._orchestrator.run(context)

        self._last_parse_result = result
        self._last_bpmn_result = context.get("bpmn_result")
        self._last_export_files = context.get("export_files") or []

        # Render diagrama por proceso.
        if self._last_bpmn_result:
            diagrams: dict[str, str] = {}
            labels: dict[str, str] = {}
            for process in result.model.processes:
                layout = self._last_bpmn_result.layouts.get(process.id)
                if layout:
                    diagrams[process.id] = render_svg(
                        result.model, layout, title=process.name
                    )
                    labels[process.id] = process.name
            self.bpmn_view.set_diagrams(diagrams, labels)
            self.act_export_bpmn.setEnabled(True)

        # Issues consolidados en la vista Resultados.
        self.issues_view.set_result(result)
        agent_lines: list[tuple[str, str]] = []
        for ar in pipeline_results:
            if ar.name == "parser":
                continue  # ya cubierto por ParseResult
            for line in ar.issues:
                agent_lines.append((ar.name, line))
        self.issues_view.append_agent_issues(agent_lines)

        quality_report = context.get("quality_report")
        score_txt = f"calidad {quality_report.score}/100" if quality_report else "sin score"
        if result.ok:
            self._status_label.setText(
                f"Excel cargado: {len(result.model.activities)} actividades, "
                f"{len(result.warnings)} advertencias, {score_txt}."
            )
        else:
            self._status_label.setText(
                f"Excel cargado con {len(result.errors)} errores ({score_txt})."
            )

        # Cambia a la vista del diagrama si hubo modelo.
        if self._last_bpmn_result:
            self.nav.setCurrentRow(_NAV_ITEMS.index("Diagrama BPMN"))
        else:
            self.nav.setCurrentRow(_NAV_ITEMS.index("Resultados"))

    def _on_export_bpmn(self) -> None:
        if not self._last_bpmn_result or not self._last_parse_result:
            QMessageBox.information(self, "Exportar BPMN", "Aún no hay BPMN generado.")
            return
        target_dir = QFileDialog.getExistingDirectory(
            self,
            "Carpeta destino para la exportación",
            str(settings.exports_dir),
        )
        if not target_dir:
            return
        from ..agents.export_agent import ExportAgent
        from ..agents.base import AgentContext as _Ctx

        ctx = _Ctx()
        ctx.set("parse_result", self._last_parse_result)
        ctx.set("bpmn_result", self._last_bpmn_result)
        ctx.set("export_dir", target_dir)
        result = ExportAgent().run(ctx)
        files = ctx.get("export_files") or []
        QMessageBox.information(
            self,
            "Exportar BPMN",
            f"{result.summary}\n\n" + "\n".join(str(f) for f in files),
        )
        self._status_label.setText(f"Exportados {len(files)} archivos en {target_dir}")


def create_main_window() -> MainWindow:
    window = MainWindow()
    window.setWindowState(window.windowState() & ~Qt.WindowState.WindowMinimized)
    return window
