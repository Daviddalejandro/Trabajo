"""Tests del generador BPMN 2.0 XML (Fase 6)."""
from __future__ import annotations

from lxml import etree

from bpmn_platform.bpmn import BpmnGenerator, compute_layout, render_svg
from bpmn_platform.core.metamodel import (
    Activity,
    BpmnType,
    EnterpriseModel,
    Event,
    Gateway,
    GatewayKind,
    Process,
    SequenceFlow,
)


def _linear_model() -> EnterpriseModel:
    process = Process(id="PROC-001", name="Onboarding clientes")
    start = Event(id="EVT-START", name="Iniciar", bpmn_type=BpmnType.START_EVENT, is_start=True)
    end = Event(id="EVT-END", name="Finalizar", bpmn_type=BpmnType.END_EVENT, is_end=True)
    task = Activity(
        id="ACT-1",
        name="Validar identidad cliente",
        bpmn_type=BpmnType.USER_TASK,
        process_id=process.id,
    )
    flows = [
        SequenceFlow(id="F1", name="-", source_id="EVT-START", target_id="ACT-1"),
        SequenceFlow(id="F2", name="-", source_id="ACT-1", target_id="EVT-END"),
    ]
    return EnterpriseModel(
        processes=[process],
        events=[start, end],
        activities=[task],
        sequence_flows=flows,
    )


def test_generator_produces_bpmn2_namespace() -> None:
    result = BpmnGenerator().generate(_linear_model())
    root = etree.fromstring(result.xml)
    assert root.tag == "{http://www.omg.org/spec/BPMN/20100524/MODEL}definitions"
    assert root.findall(".//{http://www.omg.org/spec/BPMN/20100524/MODEL}process")


def test_generator_includes_bpmndi_shapes_and_edges() -> None:
    model = _linear_model()
    result = BpmnGenerator().generate(model)
    xml = result.text()
    assert "BPMNDiagram" in xml
    assert "BPMNShape" in xml
    assert "BPMNEdge" in xml
    # Shape por cada nodo (3) + edge por cada flujo (2)
    root = etree.fromstring(result.xml)
    ns = {"bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI"}
    assert len(root.findall(".//bpmndi:BPMNShape", ns)) == 3
    assert len(root.findall(".//bpmndi:BPMNEdge", ns)) == 2


def test_generator_handles_gateways() -> None:
    process = Process(id="P", name="Branchy")
    start = Event(id="S", name="Inicio", bpmn_type=BpmnType.START_EVENT, is_start=True)
    end = Event(id="E", name="Fin", bpmn_type=BpmnType.END_EVENT, is_end=True)
    gw = Gateway(id="GW", name="aprobado?", kind=GatewayKind.EXCLUSIVE)
    a1 = Activity(id="A1", name="Aprobar credito", bpmn_type=BpmnType.USER_TASK, process_id="P")
    a2 = Activity(id="A2", name="Rechazar credito", bpmn_type=BpmnType.USER_TASK, process_id="P")
    flows = [
        SequenceFlow(id="f1", name="-", source_id="S", target_id="GW"),
        SequenceFlow(id="f2", name="si", source_id="GW", target_id="A1"),
        SequenceFlow(id="f3", name="no", source_id="GW", target_id="A2"),
        SequenceFlow(id="f4", name="-", source_id="A1", target_id="E"),
        SequenceFlow(id="f5", name="-", source_id="A2", target_id="E"),
    ]
    model = EnterpriseModel(
        processes=[process],
        events=[start, end],
        gateways=[gw],
        activities=[a1, a2],
        sequence_flows=flows,
    )
    result = BpmnGenerator().generate(model)
    xml = result.text()
    assert "exclusiveGateway" in xml
    assert xml.count("sequenceFlow") >= 5


def test_layout_is_left_to_right() -> None:
    layout = compute_layout(_linear_model(), "PROC-001")
    coords = sorted(layout.nodes.values(), key=lambda b: b.x)
    # Sequencia: start (x menor) < task < end
    assert coords[0].x < coords[1].x < coords[2].x


def test_render_svg_contains_arrows_and_labels() -> None:
    model = _linear_model()
    layout = compute_layout(model, "PROC-001")
    svg = render_svg(model, layout, title="Onboarding clientes")
    assert svg.startswith("<svg")
    assert "marker-end" in svg
    assert "Onboarding clientes" in svg
    assert "Validar" in svg
