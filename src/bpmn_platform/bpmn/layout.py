"""Auto-layout BPMN simple (flujo izquierda -> derecha por columnas).

Devuelve coordenadas y dimensiones para cada nodo y waypoints para cada
flujo. La salida alimenta tanto el BPMNDI del XML (Fase 6) como el
renderer SVG (Fase 9).
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from ..core.metamodel import (
    Activity,
    BpmnType,
    EnterpriseModel,
    Event,
    Gateway,
    SequenceFlow,
)

# Dimensiones canonicas (px, similares a Camunda).
_TASK_SIZE = (110, 80)
_EVENT_SIZE = (36, 36)
_GATEWAY_SIZE = (50, 50)

_COLUMN_WIDTH = 160
_LANE_HEIGHT = 120
_TOP_MARGIN = 60
_LEFT_MARGIN = 60


def _size_for(bpmn_type: BpmnType) -> tuple[int, int]:
    if bpmn_type in (BpmnType.USER_TASK, BpmnType.SERVICE_TASK):
        return _TASK_SIZE
    if bpmn_type in (BpmnType.EXCLUSIVE_GATEWAY, BpmnType.PARALLEL_GATEWAY):
        return _GATEWAY_SIZE
    return _EVENT_SIZE


@dataclass
class NodeBounds:
    x: float
    y: float
    width: float
    height: float

    @property
    def cx(self) -> float:
        return self.x + self.width / 2

    @property
    def cy(self) -> float:
        return self.y + self.height / 2

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass
class EdgeWaypoints:
    points: list[tuple[float, float]] = field(default_factory=list)


@dataclass
class Layout:
    process_id: str
    nodes: dict[str, NodeBounds] = field(default_factory=dict)
    edges: dict[str, EdgeWaypoints] = field(default_factory=dict)
    width: float = 0
    height: float = 0


def _columns_for_process(node_ids: list[str], flows: list[SequenceFlow]) -> dict[str, int]:
    """Asigna columna a cada nodo via BFS desde los nodos sin predecesores."""
    incoming = defaultdict(list)
    outgoing = defaultdict(list)
    for flow in flows:
        incoming[flow.target_id].append(flow.source_id)
        outgoing[flow.source_id].append(flow.target_id)

    columns: dict[str, int] = {}
    roots = [nid for nid in node_ids if not incoming[nid]]
    if not roots:
        # Grafo ciclico o sin start: usa el primer nodo como raiz.
        roots = node_ids[:1]
    queue: deque[str] = deque()
    for root in roots:
        columns[root] = 0
        queue.append(root)
    while queue:
        node = queue.popleft()
        for nxt in outgoing[node]:
            new_col = columns[node] + 1
            if columns.get(nxt, -1) < new_col:
                columns[nxt] = new_col
                queue.append(nxt)
    # Nodos no alcanzados: les damos columna 0 (se renderizaran arriba a la izquierda).
    for nid in node_ids:
        columns.setdefault(nid, 0)
    return columns


def _row_for_node(
    node_id: str,
    columns: dict[str, int],
    flows: list[SequenceFlow],
    assigned: dict[int, list[str]],
) -> int:
    """Asigna fila (carril) a un nodo respetando que no choque con otros de su columna."""
    column = columns[node_id]
    same_column = assigned.setdefault(column, [])
    row = len(same_column)
    same_column.append(node_id)
    return row


def compute_layout(model: EnterpriseModel, process_id: str) -> Layout:
    """Calcula posiciones para todos los nodos de un proceso."""
    related_ids, flows = model.related_to_process(process_id)
    activities = [a for a in model.activities if a.process_id == process_id]
    activity_ids = {a.id for a in activities}
    events_by_id = {e.id: e for e in model.events if e.id in related_ids}
    gateways_by_id = {g.id: g for g in model.gateways if g.id in related_ids}

    ordered_ids: list[str] = []
    ordered_ids.extend(a.id for a in activities)
    ordered_ids.extend(eid for eid in events_by_id if eid not in activity_ids)
    ordered_ids.extend(gid for gid in gateways_by_id if gid not in activity_ids)

    columns = _columns_for_process(ordered_ids, flows)
    assigned_rows: dict[int, list[str]] = {}
    layout = Layout(process_id=process_id)

    type_for: dict[str, BpmnType] = {}
    for a in activities:
        type_for[a.id] = a.bpmn_type
    for eid, ev in events_by_id.items():
        type_for[eid] = ev.bpmn_type
    for gid, gw in gateways_by_id.items():
        type_for[gid] = (
            BpmnType.EXCLUSIVE_GATEWAY
            if gw.kind.value == "exclusive"
            else BpmnType.PARALLEL_GATEWAY
        )

    # Asigna nodos por columna.
    for nid in sorted(ordered_ids, key=lambda x: (columns[x], ordered_ids.index(x))):
        col = columns[nid]
        row = _row_for_node(nid, columns, flows, assigned_rows)
        width, height = _size_for(type_for.get(nid, BpmnType.USER_TASK))
        column_center_x = _LEFT_MARGIN + col * _COLUMN_WIDTH + _COLUMN_WIDTH / 2
        row_center_y = _TOP_MARGIN + row * _LANE_HEIGHT + _LANE_HEIGHT / 2
        layout.nodes[nid] = NodeBounds(
            x=column_center_x - width / 2,
            y=row_center_y - height / 2,
            width=width,
            height=height,
        )

    # Calcula waypoints: salida derecha del origen -> entrada izquierda del destino,
    # con una recta horizontal cuando estan en la misma fila o un codo en otro caso.
    for flow in flows:
        src = layout.nodes.get(flow.source_id)
        tgt = layout.nodes.get(flow.target_id)
        if not src or not tgt:
            continue
        start = (src.right, src.cy)
        end = (tgt.x, tgt.cy)
        if abs(src.cy - tgt.cy) < 1:
            points = [start, end]
        else:
            mid_x = (src.right + tgt.x) / 2
            points = [start, (mid_x, src.cy), (mid_x, tgt.cy), end]
        layout.edges[flow.id] = EdgeWaypoints(points=points)

    # Dimensiones globales.
    if layout.nodes:
        layout.width = max(b.right for b in layout.nodes.values()) + _LEFT_MARGIN
        layout.height = max(b.bottom for b in layout.nodes.values()) + _TOP_MARGIN
    return layout
