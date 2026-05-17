"""Tests del validador de calidad BPMN (Fase 8)."""
from __future__ import annotations

from bpmn_platform.bpmn import QualityValidator
from bpmn_platform.core.metamodel import (
    Activity,
    BpmnType,
    EnterpriseModel,
    Event,
    Process,
    SequenceFlow,
)


def _make_linear_model(*, with_start=True, with_end=True) -> EnterpriseModel:
    process = Process(id="P", name="Demo")
    events: list[Event] = []
    if with_start:
        events.append(
            Event(id="S", name="Inicio", bpmn_type=BpmnType.START_EVENT, is_start=True)
        )
    if with_end:
        events.append(
            Event(id="E", name="Fin", bpmn_type=BpmnType.END_EVENT, is_end=True)
        )
    a = Activity(
        id="A1",
        name="Validar identidad",
        bpmn_type=BpmnType.USER_TASK,
        process_id="P",
        role_id="ANALISTA_RIESGO",
    )
    flows = []
    if with_start:
        flows.append(SequenceFlow(id="f1", name="-", source_id="S", target_id="A1"))
    if with_end:
        flows.append(SequenceFlow(id="f2", name="-", source_id="A1", target_id="E"))
    return EnterpriseModel(
        processes=[process], events=events, activities=[a], sequence_flows=flows
    )


def test_quality_full_score_for_complete_process() -> None:
    report = QualityValidator().validate(_make_linear_model())
    assert report.ok
    assert report.score == 100, [
        f"{i.code}: {i.message}" for i in report.issues
    ]


def test_quality_flags_missing_start() -> None:
    report = QualityValidator().validate(_make_linear_model(with_start=False))
    codes = {i.code for i in report.issues}
    assert "Q-NO-START" in codes
    assert report.score < 100


def test_quality_flags_unreachable_node() -> None:
    process = Process(id="P", name="Demo")
    start = Event(id="S", name="Inicio", bpmn_type=BpmnType.START_EVENT, is_start=True)
    end = Event(id="E", name="Fin", bpmn_type=BpmnType.END_EVENT, is_end=True)
    a = Activity(id="A1", name="Validar identidad", bpmn_type=BpmnType.USER_TASK, process_id="P", role_id="X")
    orphan = Activity(id="A2", name="Tarea suelta", bpmn_type=BpmnType.USER_TASK, process_id="P", role_id="X")
    flows = [
        SequenceFlow(id="f1", name="-", source_id="S", target_id="A1"),
        SequenceFlow(id="f2", name="-", source_id="A1", target_id="E"),
    ]
    model = EnterpriseModel(
        processes=[process], events=[start, end], activities=[a, orphan], sequence_flows=flows
    )
    report = QualityValidator().validate(model)
    codes = {i.code for i in report.issues}
    assert "Q-UNREACHABLE" in codes


def test_quality_score_decreases_with_warnings() -> None:
    # ServiceTask sin sistema -> Q-SERVICETASK-NO-SYSTEM (warning, peso 3).
    process = Process(id="P", name="Demo")
    start = Event(id="S", name="Inicio", bpmn_type=BpmnType.START_EVENT, is_start=True)
    end = Event(id="E", name="Fin", bpmn_type=BpmnType.END_EVENT, is_end=True)
    a = Activity(id="A1", name="Generar reporte", bpmn_type=BpmnType.SERVICE_TASK, process_id="P")
    flows = [
        SequenceFlow(id="f1", name="-", source_id="S", target_id="A1"),
        SequenceFlow(id="f2", name="-", source_id="A1", target_id="E"),
    ]
    model = EnterpriseModel(
        processes=[process], events=[start, end], activities=[a], sequence_flows=flows
    )
    report = QualityValidator().validate(model)
    assert report.score == 97  # 100 - 3 (warning)
