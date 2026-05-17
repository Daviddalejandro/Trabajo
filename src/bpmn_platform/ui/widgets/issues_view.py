"""Vista Resultados: muestra el resultado del parsing y validacion."""
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


_SEVERITY_COLOR = {
    IssueSeverity.ERROR: "#FFD6D6",
    IssueSeverity.WARNING: "#FFF1C2",
    IssueSeverity.INFO: "#D9E5FF",
}


def _metric_card(title: str, value: str, accent: str = "#1F3864") -> QWidget:
    card = QWidget()
    card.setStyleSheet(
        "QWidget { background-color: white; border: 1px solid #D0D7E2;"
        " border-radius: 8px; }"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(14, 10, 14, 10)
    layout.setSpacing(2)
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet("font-size: 10pt; color: #555;")
    value_lbl = QLabel(value)
    value_lbl.setStyleSheet(f"font-size: 18pt; font-weight: bold; color: {accent};")
    layout.addWidget(title_lbl)
    layout.addWidget(value_lbl)
    return card


class IssuesView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet("QWidget { background-color: #F4F6FA; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("Resultado del parsing")
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #1F3864;")
        self._hint = QLabel(
            "Aun no se ha cargado un Excel. Usa 'Archivo -> Cargar Excel...'."
        )
        self._hint.setStyleSheet("font-size: 10pt; color: #555;")

        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(10)

        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(
            ["Severidad", "Codigo", "Mensaje", "Ubicacion"]
        )
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setStyleSheet(
            "QTableWidget { background-color: white; gridline-color: #D0D7E2; }"
            "QHeaderView::section { background-color: #1F3864; color: white;"
            " padding: 6px; border: 0; }"
        )
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
                "Aun no se ha cargado un Excel. Usa 'Archivo -> Cargar Excel...'."
            )
            self._table.setRowCount(0)
            return

        model = result.model
        if result.ok:
            self._hint.setText("Parsing completado sin errores criticos.")
            self._hint.setStyleSheet("font-size: 10pt; color: #2E7D32;")
        else:
            self._hint.setText(
                f"Parsing completado con {len(result.errors)} errores. Revisa la tabla."
            )
            self._hint.setStyleSheet("font-size: 10pt; color: #C62828;")

        metrics = [
            ("Procesos", str(len(model.processes)), "#1F3864"),
            ("Actividades", str(len(model.activities)), "#1F3864"),
            ("Eventos", str(len(model.events)), "#1F3864"),
            ("Gateways", str(len(model.gateways)), "#1F3864"),
            ("Comandos", str(len(model.commands)), "#1F3864"),
            ("Activos", str(len(model.information_assets)), "#1F3864"),
            ("Errores", str(len(result.errors)), "#C62828"),
            ("Warnings", str(len(result.warnings)), "#E65100"),
            ("Info", str(len(result.infos)), "#1565C0"),
        ]
        for label, value, accent in metrics:
            self._metrics_row.addWidget(_metric_card(label, value, accent))

        self._table.setRowCount(len(result.issues))
        for row, issue in enumerate(result.issues):
            color = QColor(_SEVERITY_COLOR.get(issue.severity, "#FFFFFF"))
            cells = (issue.severity.value, issue.code, issue.message, issue.location)
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
