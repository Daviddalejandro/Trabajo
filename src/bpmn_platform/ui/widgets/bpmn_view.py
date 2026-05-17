"""Visor BPMN basado en SVG (Fase 9).

Renderiza el SVG producido por `bpmn.export.render_svg` dentro de un
QGraphicsView con zoom/pan. No requiere QtWebEngine ni JavaScript.
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPainter, QWheelEvent
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import (
    QComboBox,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _ZoomGraphicsView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.scale(factor, factor)
        else:
            super().wheelEvent(event)


class BpmnView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet("QWidget { background-color: #F4F6FA; }")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(10)

        title = QLabel("Visualizacion BPMN")
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #1F3864;")

        controls = QHBoxLayout()
        controls.setSpacing(8)
        self._process_selector = QComboBox()
        self._process_selector.setMinimumWidth(280)
        self._process_selector.currentIndexChanged.connect(self._on_process_changed)

        btn_fit = QPushButton("Ajustar a ventana")
        btn_fit.clicked.connect(self._fit_view)
        btn_zoom_in = QPushButton("+")
        btn_zoom_in.setFixedWidth(36)
        btn_zoom_in.clicked.connect(lambda: self._view.scale(1.2, 1.2))
        btn_zoom_out = QPushButton("-")
        btn_zoom_out.setFixedWidth(36)
        btn_zoom_out.clicked.connect(lambda: self._view.scale(1 / 1.2, 1 / 1.2))

        controls.addWidget(QLabel("Proceso:"))
        controls.addWidget(self._process_selector)
        controls.addWidget(btn_fit)
        controls.addWidget(btn_zoom_in)
        controls.addWidget(btn_zoom_out)
        controls.addStretch(1)

        self._scene = QGraphicsScene()
        self._view = _ZoomGraphicsView()
        self._view.setScene(self._scene)
        self._view.setStyleSheet(
            "QGraphicsView { background-color: white; border: 1px solid #D0D7E2; }"
        )

        self._placeholder = QLabel(
            "Aun no se ha generado un BPMN. Cargue un Excel desde 'Archivo -> Cargar Excel...'"
        )
        self._placeholder.setStyleSheet("color: #555; font-size: 11pt;")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)

        root.addWidget(title)
        root.addLayout(controls)
        root.addWidget(self._view, 1)
        root.addWidget(self._placeholder)

        self._svgs: dict[str, str] = {}
        self._labels: dict[str, str] = {}
        self._show_placeholder(True)

    def set_diagrams(self, diagrams: dict[str, str], labels: dict[str, str]) -> None:
        """diagrams: process_id -> SVG markup; labels: process_id -> nombre."""
        self._svgs = dict(diagrams)
        self._labels = dict(labels)
        self._process_selector.blockSignals(True)
        self._process_selector.clear()
        for pid, svg in self._svgs.items():
            self._process_selector.addItem(self._labels.get(pid, pid), pid)
        self._process_selector.blockSignals(False)
        if self._svgs:
            self._process_selector.setCurrentIndex(0)
            self._on_process_changed(0)
        else:
            self._show_placeholder(True)

    def _show_placeholder(self, show: bool) -> None:
        self._placeholder.setVisible(show)
        self._view.setVisible(not show)

    def _on_process_changed(self, index: int) -> None:
        if index < 0:
            self._show_placeholder(True)
            return
        pid = self._process_selector.itemData(index)
        svg = self._svgs.get(pid)
        if not svg:
            self._show_placeholder(True)
            return
        renderer = QSvgRenderer()
        renderer.load(svg.encode("utf-8"))
        self._scene.clear()
        item = QGraphicsSvgItem()
        item.setSharedRenderer(renderer)
        item.setPos(QPointF(0, 0))
        self._scene.addItem(item)
        self._scene.setSceneRect(renderer.viewBoxF())
        self._show_placeholder(False)
        self._fit_view()

    def _fit_view(self) -> None:
        if not self._scene.items():
            return
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
