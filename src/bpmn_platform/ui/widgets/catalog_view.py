"""Vista Catálogos: navegar y revisar los catálogos cargados."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
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
from .. import theme


class CatalogView(QWidget):
    def __init__(self, *, catalogs: CatalogBundle | None) -> None:
        super().__init__()
        self._catalogs = catalogs
        self.setStyleSheet(f"QWidget {{ background-color: {theme.GRIS_FONDO}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("Catálogos controlados")
        title.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 18pt; font-weight: bold;"
            f" color: {theme.COLSUBSIDIO_AZUL};"
        )
        subtitle = QLabel(
            "Estos catálogos alimentan los dropdowns del Excel oficial. "
            "Para modificarlos edite los archivos YAML en la carpeta 'catalogs/'."
        )
        subtitle.setStyleSheet(
            f"font-family: {theme.FONT_FAMILY}; font-size: 10pt; color: {theme.GRIS_TEXTO};"
        )
        subtitle.setWordWrap(True)

        self._list = QListWidget()
        self._list.setMinimumWidth(220)
        self._list.setStyleSheet(
            f"QListWidget {{ background-color: {theme.BLANCO}; border: 1px solid {theme.GRIS_BORDE}; }}"
            f"QListWidget::item {{ padding: 8px 12px; font-family: {theme.FONT_FAMILY}; }}"
            f"QListWidget::item:selected {{ background-color: {theme.COLSUBSIDIO_AZUL};"
            f" color: {theme.BLANCO}; }}"
            f"QListWidget::item:hover {{ background-color: {theme.AZUL_CLARO}; }}"
        )
        self._list.currentTextChanged.connect(self._on_catalog_selected)

        self._table = QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["Código", "Etiqueta", "Descripción"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(theme.table_qss())
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
