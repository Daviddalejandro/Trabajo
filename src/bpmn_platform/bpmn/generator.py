"""Generador BPMN 2.0 XML (Fase 6).

Convierte un `EnterpriseModel` en un documento BPMN 2.0 XML estandar,
incluyendo la informacion de diagrama (BPMNDI) calculada por `layout.py`.

El XML resultante puede abrirse en Camunda Modeler, bpmn.io, Signavio, etc.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from lxml import etree

from ..core.metamodel import BpmnType, EnterpriseModel, Process
from ..logging_config import get_logger
from .layout import Layout, compute_layout

log = get_logger(__name__)


# Namespaces BPMN 2.0
_NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}


def _q(prefix: str, local: str) -> str:
    return f"{{{_NS[prefix]}}}{local}"


@dataclass
class BpmnGenerationResult:
    xml: bytes
    layouts: dict[str, Layout] = field(default_factory=dict)
    target_namespace: str = ""
    definitions_id: str = ""

    def text(self) -> str:
        return self.xml.decode("utf-8")


class BpmnGenerator:
    """Genera BPMN 2.0 XML completo (proceso + diagrama)."""

    def generate(self, model: EnterpriseModel) -> BpmnGenerationResult:
        if not model.processes:
            raise ValueError("El EnterpriseModel no contiene procesos para generar BPMN.")

        defs_id = self._stable_id("Definitions", model)
        target_ns = "https://bpmn-platform.local/bpmn"
        definitions = etree.Element(
            _q("bpmn", "definitions"),
            nsmap=_NS,
            attrib={
                "id": defs_id,
                "targetNamespace": target_ns,
                "exporter": "BPMN Platform (Open Source)",
                "exporterVersion": "0.1.0",
            },
        )
        # `xsi` namespace requiere declaracion explicita.
        etree.SubElement(definitions, _q("bpmn", "import"))  # placeholder removible
        definitions.remove(definitions[0])

        layouts: dict[str, Layout] = {}
        for process in model.processes:
            layout = compute_layout(model, process.id)
            layouts[process.id] = layout
            self._render_process(definitions, process, model)
            self._render_diagram(definitions, process, layout)

        xml_bytes = etree.tostring(
            definitions,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8",
        )
        log.info(
            "BPMN generado: {} procesos, {} bytes",
            len(model.processes),
            len(xml_bytes),
        )
        return BpmnGenerationResult(
            xml=xml_bytes,
            layouts=layouts,
            target_namespace=target_ns,
            definitions_id=defs_id,
        )

    # ------------------------------------------------------------------ #
    # Elementos de proceso
    # ------------------------------------------------------------------ #

    def _render_process(
        self,
        definitions: etree._Element,
        process: Process,
        model: EnterpriseModel,
    ) -> None:
        process_el = etree.SubElement(
            definitions,
            _q("bpmn", "process"),
            attrib={
                "id": process.id,
                "name": process.name,
                "isExecutable": "false",
            },
        )
        if process.description:
            doc = etree.SubElement(process_el, _q("bpmn", "documentation"))
            doc.text = process.description

        related_ids, flows = model.related_to_process(process.id)
        activities = [a for a in model.activities if a.process_id == process.id]
        events = [e for e in model.events if e.id in related_ids]
        gateways = [g for g in model.gateways if g.id in related_ids]

        # Eventos
        for event in events:
            tag = self._bpmn_event_tag(event.bpmn_type)
            etree.SubElement(
                process_el,
                _q("bpmn", tag),
                attrib={"id": event.id, "name": event.name},
            )

        # Gateways
        for gateway in gateways:
            tag = (
                "exclusiveGateway"
                if gateway.kind.value == "exclusive"
                else "parallelGateway"
            )
            etree.SubElement(
                process_el,
                _q("bpmn", tag),
                attrib={"id": gateway.id, "name": gateway.name},
            )

        # Tasks
        for activity in activities:
            tag = "userTask" if activity.bpmn_type == BpmnType.USER_TASK else "serviceTask"
            attrs: dict[str, str] = {"id": activity.id, "name": activity.name}
            task_el = etree.SubElement(process_el, _q("bpmn", tag), attrib=attrs)
            if activity.observations:
                doc = etree.SubElement(task_el, _q("bpmn", "documentation"))
                doc.text = activity.observations

        # Sequence flows
        for flow in flows:
            etree.SubElement(
                process_el,
                _q("bpmn", "sequenceFlow"),
                attrib={
                    "id": flow.id,
                    "sourceRef": flow.source_id,
                    "targetRef": flow.target_id,
                },
            )

    # ------------------------------------------------------------------ #
    # BPMNDI
    # ------------------------------------------------------------------ #

    def _render_diagram(
        self,
        definitions: etree._Element,
        process: Process,
        layout: Layout,
    ) -> None:
        diagram = etree.SubElement(
            definitions,
            _q("bpmndi", "BPMNDiagram"),
            attrib={"id": f"Diagram_{process.id}"},
        )
        plane = etree.SubElement(
            diagram,
            _q("bpmndi", "BPMNPlane"),
            attrib={"id": f"Plane_{process.id}", "bpmnElement": process.id},
        )
        for node_id, bounds in layout.nodes.items():
            shape = etree.SubElement(
                plane,
                _q("bpmndi", "BPMNShape"),
                attrib={
                    "id": f"Shape_{node_id}",
                    "bpmnElement": node_id,
                },
            )
            etree.SubElement(
                shape,
                _q("dc", "Bounds"),
                attrib={
                    "x": f"{bounds.x:.0f}",
                    "y": f"{bounds.y:.0f}",
                    "width": f"{bounds.width:.0f}",
                    "height": f"{bounds.height:.0f}",
                },
            )
        for flow_id, edge in layout.edges.items():
            bpmn_edge = etree.SubElement(
                plane,
                _q("bpmndi", "BPMNEdge"),
                attrib={
                    "id": f"Edge_{flow_id}",
                    "bpmnElement": flow_id,
                },
            )
            for x, y in edge.points:
                etree.SubElement(
                    bpmn_edge,
                    _q("di", "waypoint"),
                    attrib={"x": f"{x:.0f}", "y": f"{y:.0f}"},
                )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _bpmn_event_tag(bpmn_type: BpmnType) -> str:
        return {
            BpmnType.START_EVENT: "startEvent",
            BpmnType.END_EVENT: "endEvent",
            BpmnType.INTERMEDIATE_CATCH_EVENT: "intermediateCatchEvent",
            BpmnType.MESSAGE_EVENT: "intermediateThrowEvent",
        }.get(bpmn_type, "intermediateCatchEvent")

    @staticmethod
    def _stable_id(prefix: str, model: EnterpriseModel) -> str:
        """ID deterministico para `Definitions` (basado en contenido del modelo)."""
        payload = "|".join(
            [
                *(p.id for p in model.processes),
                *(a.id for a in model.activities),
                *(f.id for f in model.sequence_flows),
                datetime.now(timezone.utc).strftime("%Y%m%d"),
            ]
        )
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
        return f"{prefix}_{digest}"
