"""Export visual: SVG generado desde el layout BPMN (Fase 9).

Produce un SVG renderizable en cualquier navegador o widget Qt sin
depender de Javascript / bpmn-js.  Mantiene los mismos coordinates que
el BPMNDI, asi que el diagrama es identico al que veria un BPMN modeler
profesional.
"""
from __future__ import annotations

from html import escape

from ..core.metamodel import (
    Activity,
    BpmnType,
    EnterpriseModel,
    Event,
    Gateway,
)
from .layout import Layout, NodeBounds


# Paleta Colsubsidio (azul #0067B1, amarillo #FFD000) aplicada al BPMN.
# Se conservan verde/rojo en eventos start/end por convencion BPMN 2.0.
_STYLE = """
.bpmn-task { fill: #FFFFFF; stroke: #0067B1; stroke-width: 2; rx: 10; ry: 10; }
.bpmn-service { fill: #E8F1F9; stroke: #004F8C; stroke-width: 2; rx: 10; ry: 10; }
.bpmn-event-start { fill: #C8E6C9; stroke: #2E7D32; stroke-width: 2; }
.bpmn-event-end { fill: #FFCDD2; stroke: #C62828; stroke-width: 3; }
.bpmn-event { fill: #FFFFFF; stroke: #6B6B6B; stroke-width: 2; }
.bpmn-gateway { fill: #FFD000; stroke: #CC9C00; stroke-width: 2; }
.bpmn-edge { fill: none; stroke: #303030; stroke-width: 1.6; }
.bpmn-label { font-family: Segoe UI, Roboto, sans-serif; font-size: 11px; fill: #1A1A1A; text-anchor: middle; }
.bpmn-label-small { font-family: Segoe UI, Roboto, sans-serif; font-size: 9px; fill: #404040; text-anchor: middle; }
.bpmn-title { font-family: Segoe UI, Roboto, sans-serif; font-size: 16px; font-weight: bold; fill: #0067B1; }
.bpmn-frame { fill: none; stroke: #0067B1; stroke-width: 1; }
.bpmn-accent { fill: #FFD000; }
"""


def _wrap(text: str, width: int = 14) -> list[str]:
    """Reparte un texto en hasta 3 lineas para que quepa en el shape."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = (" ".join(current + [word])).strip()
        if len(candidate) > width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
        if len(lines) == 2:
            break
    if current:
        rest = " ".join(current + words[len(" ".join(lines).split()) + len(current):])
        # Truncar la ultima linea si es muy larga.
        if len(rest) > width + 4:
            rest = rest[: width + 1] + "..."
        lines.append(rest)
    return lines[:3]


def _label_text(node_id: str, bounds: NodeBounds, name: str) -> str:
    lines = _wrap(name, width=14 if bounds.width >= 80 else 10)
    line_height = 12
    total = len(lines) * line_height
    base_y = bounds.cy - total / 2 + line_height - 2
    out = []
    for idx, line in enumerate(lines):
        out.append(
            f'<text class="bpmn-label" x="{bounds.cx:.1f}" '
            f'y="{base_y + idx * line_height:.1f}">{escape(line)}</text>'
        )
    return "\n".join(out)


def _node_shape(
    node_id: str,
    bpmn_type: BpmnType,
    bounds: NodeBounds,
    *,
    name: str,
    is_start: bool = False,
    is_end: bool = False,
) -> str:
    if bpmn_type in (BpmnType.USER_TASK, BpmnType.SERVICE_TASK):
        cls = "bpmn-task" if bpmn_type == BpmnType.USER_TASK else "bpmn-service"
        return (
            f'<rect class="{cls}" x="{bounds.x:.1f}" y="{bounds.y:.1f}" '
            f'width="{bounds.width:.1f}" height="{bounds.height:.1f}"/>'
            + _label_text(node_id, bounds, name)
        )
    if bpmn_type in (BpmnType.EXCLUSIVE_GATEWAY, BpmnType.PARALLEL_GATEWAY):
        cx, cy = bounds.cx, bounds.cy
        d = bounds.width / 2
        points = f"{cx},{cy - d} {cx + d},{cy} {cx},{cy + d} {cx - d},{cy}"
        marker = "x" if bpmn_type == BpmnType.EXCLUSIVE_GATEWAY else "+"
        return (
            f'<polygon class="bpmn-gateway" points="{points}"/>'
            f'<text class="bpmn-label" x="{cx:.1f}" y="{cy + 4:.1f}" '
            f'style="font-size: 16px; font-weight: bold;">{marker}</text>'
            f'<text class="bpmn-label-small" x="{cx:.1f}" y="{cy + d + 14:.1f}">{escape(name)}</text>'
        )
    # Eventos -> circulos
    cls = "bpmn-event"
    if is_start:
        cls = "bpmn-event-start"
    elif is_end:
        cls = "bpmn-event-end"
    return (
        f'<circle class="{cls}" cx="{bounds.cx:.1f}" cy="{bounds.cy:.1f}" r="{bounds.width / 2:.1f}"/>'
        f'<text class="bpmn-label-small" x="{bounds.cx:.1f}" y="{bounds.bottom + 12:.1f}">{escape(name)}</text>'
    )


def _arrow_marker_defs() -> str:
    return (
        '<defs>'
        '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="10" '
        'markerHeight="10" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#303030"/>'
        '</marker>'
        '</defs>'
    )


def render_svg(model: EnterpriseModel, layout: Layout, *, title: str | None = None) -> str:
    activity_by_id: dict[str, Activity] = {a.id: a for a in model.activities}
    event_by_id: dict[str, Event] = {e.id: e for e in model.events}
    gateway_by_id: dict[str, Gateway] = {g.id: g for g in model.gateways}
    process = next((p for p in model.processes if p.id == layout.process_id), None)
    title_text = title or (process.name if process else layout.process_id)

    width = max(layout.width, 480)
    height = max(layout.height, 240)

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" '
        f'width="{width:.0f}" height="{height:.0f}">'
    )
    parts.append(f"<style>{_STYLE}</style>")
    parts.append(_arrow_marker_defs())
    # Banda superior Colsubsidio (azul con franja amarilla).
    parts.append(
        f'<rect x="0" y="0" width="{width:.0f}" height="36" fill="#0067B1"/>'
        f'<rect x="0" y="36" width="{width:.0f}" height="4" fill="#FFD000"/>'
        f'<text class="bpmn-title" x="20" y="24" fill="#FFFFFF">{escape(title_text)}</text>'
    )

    for flow_id, edge in layout.edges.items():
        if len(edge.points) < 2:
            continue
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in edge.points)
        parts.append(
            f'<polyline class="bpmn-edge" points="{points}" marker-end="url(#arrow)"/>'
        )

    for node_id, bounds in layout.nodes.items():
        activity = activity_by_id.get(node_id)
        event = event_by_id.get(node_id)
        gateway = gateway_by_id.get(node_id)
        if activity:
            parts.append(
                _node_shape(node_id, activity.bpmn_type, bounds, name=activity.name)
            )
        elif event:
            parts.append(
                _node_shape(
                    node_id,
                    event.bpmn_type,
                    bounds,
                    name=event.name,
                    is_start=event.is_start,
                    is_end=event.is_end,
                )
            )
        elif gateway:
            bpmn_type = (
                BpmnType.EXCLUSIVE_GATEWAY
                if gateway.kind.value == "exclusive"
                else BpmnType.PARALLEL_GATEWAY
            )
            parts.append(_node_shape(node_id, bpmn_type, bounds, name=gateway.name))

    parts.append("</svg>")
    return "\n".join(parts)
