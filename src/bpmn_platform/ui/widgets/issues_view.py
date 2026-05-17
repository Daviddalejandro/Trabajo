"""Vista Resultados: muestra el resultado del parsing y la validación."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.governance import IssueSeverity
from ...excel.parser import ParseResult
from .. import theme


_SEVERITY_BG = {
    IssueSeverity.ERROR: theme.ERROR_BG,
    IssueSeverity.WARNING: theme.WARNING_BG,
    IssueSeverity.INFO: theme.INFO_BG,
}
_SEVERITY_LABEL = {
    IssueSeverity.ERROR: "Error",
    IssueSeverity.WARNING: "Advertencia",
    IssueSeverity.INFO: "Información",
}


def _metric_card(title: str, value: str, accent: str | None = None) -> QWidget:
    accent_color = accent or theme.COLSUBSIDIO_AZUL
    card = QWidget()
    card.setStyleSheet(
        f"QWidget {{ background-color: {theme.BLANCO}; border: 1px solid {theme.GRIS_BORDE};"
        f" border-radius: 8px; }}"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 10, 14, 10)
    layout.setSpacing(2)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"font-family: {theme.FONT_FAMILY}; font-size: 10pt; color: {theme.GRIS_SECUNDARIO};"
    )
    value_lbl = QLabel(value)
    value_lbl.setStyleSheet(
        f"font-family: {theme.FONT_FAMILY}; font-size: 18pt; font-weight: bold; color: {accent_color};"
    )
    layout.addWidget(title_lbl)
    layout.addWidget(value_lbl)
    return card


class IssuesView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(f"QWidget {{ background-color: {theme.GRIS_FONDO}; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("Resultado del análisis")
        title.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 18pt; font-weight: bold;"
            f" color: {theme.COLSUBSIDIO_AZUL};"
        )
        self._hint = QLabel(
            "Aún no se ha cargado un Excel. Usa 'Archivo → Cargar Excel...'."
        )
        self._hint.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 10pt; color: {theme.GRIS_SECUNDARIO};"
        )

        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(10)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            ["Severidad", "Código", "Mensaje", "Ubicación"]
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(theme.table_qss())
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        root.addWidget(title)
        root.addWidget(self._hint)
        root.addLayout(self._metrics_row)
        root.addWidget(self._table, 1)

    def set_result(self, result: ParseResult | None) -> None:
        while self._metrics_row.count():
            item = self._metrics_row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        if not result:
            self._hint.setText(
                "Aún no se ha cargado un Excel. Usa 'Archivo → Cargar Excel...'."
            )
            self._table.setRowCount(0)
            return

        model = result.model
        if result.ok:
            self._hint.setText("Análisis completado sin errores críticos.")
            self._hint.setStyleSheet(
                f"font-family: {theme.FONT_FAMILY}; font-size: 10pt; color: {theme.OK_FG};"
            )
        else:
            self._hint.setText(
                f"Análisis completado con {len(result.errors)} errores. Revisa la tabla."
            )
            self._hint.setStyleSheet(
                f"font-family: {theme.FONT_FAMILY}; font-size: 10pt; color: {theme.ERROR_FG};"
            )

        metrics = [
            ("Procesos", str(len(model.processes)), theme.COLSUBSIDIO_AZUL),
            ("Actividades", str(len(model.activities)), theme.COLSUBSIDIO_AZUL),
            ("Eventos", str(len(model.events)), theme.COLSUBSIDIO_AZUL),
            ("Compuertas", str(len(model.gateways)), theme.COLSUBSIDIO_AZUL),
            ("Comandos", str(len(model.commands)), theme.COLSUBSIDIO_AZUL),
            ("Activos", str(len(model.information_assets)), theme.COLSUBSIDIO_AZUL),
            ("Errores", str(len(result.errors)), theme.ERROR_FG),
            ("Advertencias", str(len(result.warnings)), theme.WARNING_FG),
            ("Información", str(len(result.infos)), theme.INFO_FG),
        ]
        for label, value, accent in metrics:
            self._metrics_row.addWidget(_metric_card(label, value, accent))

        self._table.setRowCount(len(result.issues))
        for row, issue in enumerate(result.issues):
            color = QColor(_SEVERITY_BG.get(issue.severity, theme.BLANCO))
            cells = (
                _SEVERITY_LABEL.get(issue.severity, issue.severity.value),
                issue.code,
                issue.message,
                issue.location,
            )
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(color)
                if col == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, item)
        self._table.resizeColumnsToContents()
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )

    def append_agent_issues(self, lines: list[tuple[str, str]]) -> None:
        """Añade hallazgos extra producidos por otros agentes.

        Cada item es (agent_name, line) donde line tiene el formato
        '[severity] CODE: mensaje'.
        """
        if not lines:
            return
        start = self._table.rowCount()
        self._table.setRowCount(start + len(lines))
        for offset, (agent_name, line) in enumerate(lines):
            severity = IssueSeverity.INFO
            for s in (IssueSeverity.ERROR, IssueSeverity.WARNING, IssueSeverity.INFO):
                if f"[{s.value}]" in line:
                    severity = s
                    break
            _, _, rest = line.partition("]")
            code, _, message = rest.strip().partition(":")
            color = QColor(_SEVERITY_BG.get(severity, theme.BLANCO))
            cells = (
                _SEVERITY_LABEL.get(severity, severity.value),
                code.strip(),
                message.strip(),
                f"agente:{agent_name}",
            )
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setBackground(color)
                if col == 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(start + offset, col, item)
