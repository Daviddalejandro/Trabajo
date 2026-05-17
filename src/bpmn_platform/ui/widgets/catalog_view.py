"""Vista Catalogos: navegar y revisar los catalogos cargados."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.catalogs import CatalogBundle
from ...core.catalogs.loader import Catalog


class CatalogView(QWidget):
    def __init__(self, *, catalogs: CatalogBundle | None) -> None:
        super().__init__()
        self._catalogs = catalogs
        self.setStyleSheet("QWidget { background-color: #F4F6FA; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("Catalogos controlados")
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #1F3864;")
        subtitle = QLabel(
            "Estos catalogos alimentan los dropdowns del Excel oficial. "
            "Para modificarlos edite los archivos YAML en la carpeta 'catalogs/'."
        )
        subtitle.setStyleSheet("font-size: 10pt; color: #404040;")
        subtitle.setWordWrap(True)

        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        self._list.setStyleSheet(
            "QListWidget { background-color: white; border: 1px solid #D0D7E2; }"
            "QListWidget::item { padding: 8px 12px; }"
            "QListWidget::item:selected { background-color: #1F3864; color: white; }"
        )
        self._list.currentTextChanged.connect(self._on_catalog_selected)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Codigo", "Etiqueta", "Descripcion"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget { background-color: white; gridline-color: #D0D7E2; }"
            "QHeaderView::section { background-color: #1F3864; color: white; padding: 6px; border: 0; }"
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._list)
        splitter.addWidget(self._table)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(title)
        root.addWidget(subtitle)
        root.addWidget(splitter, 1)

        self.set_catalogs(catalogs)

    def set_catalogs(self, catalogs: CatalogBundle | None) -> None:
        self._catalogs = catalogs
        self._list.clear()
        self._table.setRowCount(0)
        if not catalogs:
            return
        for name in catalogs.all():
            self._list.addItem(name)
        self._list.setCurrentRow(0)

    def _on_catalog_selected(self, name: str) -> None:
        if not self._catalogs or not name:
            return
        catalog: Catalog | None = self._catalogs.all().get(name)
        if not catalog:
            return
        self._table.setRowCount(len(catalog.entries))
        for row, entry in enumerate(catalog.entries):
            self._table.setItem(row, 0, QTableWidgetItem(entry.code))
            self._table.setItem(row, 1, QTableWidgetItem(entry.label))
            self._table.setItem(row, 2, QTableWidgetItem(entry.description or ""))
