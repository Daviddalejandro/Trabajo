"""Pruebas del metamodelo empresarial."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from bpmn_platform.core.metamodel import (
    Activity,
    Application,
    BpmnType,
    Command,
    EnterpriseModel,
    Process,
    Role,
)


def test_command_requires_application_id() -> None:
    with pytest.raises(ValidationError):
        Command(id="CMD-1", name="reconcile.py")  # type: ignore[call-arg]


def test_enterprise_model_detects_duplicate_ids() -> None:
    role = Role(id="R1", name="Operador")
    process = Process(id="P1", name="Conciliacion")
    activity_a = Activity(
        id="ACT-1",
        name="Generar reporte",
        bpmn_type=BpmnType.SERVICE_TASK,
        process_id="P1",
    )
    activity_b = Activity(
        id="ACT-1",  # duplicado intencional
        name="Generar reporte",
        bpmn_type=BpmnType.SERVICE_TASK,
        process_id="P1",
    )
    with pytest.raises(ValidationError):
        EnterpriseModel(
            roles=[role],
            processes=[process],
            activities=[activity_a, activity_b],
        )


def test_activity_application_command_chain_is_indexable() -> None:
    app = Application(id="APP-AIRFLOW", name="Airflow")
    cmd = Command(id="CMD-RECONCILE", name="reconcile.py", application_id=app.id)
    process = Process(id="P-1", name="Conciliacion")
    activity = Activity(
        id="ACT-1",
        name="Ejecutar conciliacion",
        bpmn_type=BpmnType.SERVICE_TASK,
        process_id=process.id,
        application_ids=[app.id],
    )
    model = EnterpriseModel(
        processes=[process],
        applications=[app],
        commands=[cmd],
        activities=[activity],
    )
    idx = model.index()
    assert idx["application"][app.id].name == "Airflow"
    assert idx["command"][cmd.id].application_id == app.id
    assert idx["activity"][activity.id].application_ids == [app.id]


def test_business_labels_map_known_types() -> None:
    labels = BpmnType.business_labels()
    assert labels["Inicio"] == BpmnType.START_EVENT
    assert labels["Fin"] == BpmnType.END_EVENT
    assert labels["Decision"] == BpmnType.EXCLUSIVE_GATEWAY
