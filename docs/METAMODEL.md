# Metamodelo Empresarial (Fase 2)

## Entidades

| Entidad             | Modulo                                  | Notas |
| ------------------- | --------------------------------------- | ----- |
| `Process`           | `core.metamodel.entities`               | Raiz de un proceso de negocio. |
| `Activity`          | `core.metamodel.entities`               | Actividad BPMN; referencia `application_ids`. |
| `Role`              | `core.metamodel.entities`               | Responsable / rol organizacional. |
| `Application`       | `core.metamodel.entities`               | Sistema corporativo. Agregador de Commands y APIs. |
| `Command`           | `core.metamodel.entities`               | Script/comando. `application_id` obligatorio. |
| `API`               | `core.metamodel.entities`               | Integracion tecnica. |
| `InformationAsset`  | `core.metamodel.entities`               | Activo de informacion. |
| `DataObject`        | `core.metamodel.entities`               | Entrada/salida BPMN, opcionalmente vinculada a un activo. |
| `Risk`              | `core.metamodel.entities`               | Riesgo gobernado. |
| `Control`           | `core.metamodel.entities`               | Control que mitiga riesgos. |
| `KPI`               | `core.metamodel.entities`               | Indicador. |
| `SLA`               | `core.metamodel.entities`               | Acuerdo de tiempo objetivo. |
| `Event`             | `core.metamodel.entities`               | Evento BPMN. |
| `Gateway`           | `core.metamodel.entities`               | Compuerta BPMN. |
| `EnterpriseModel`   | `core.metamodel.relationships`          | Agregado raiz; valida unicidad de IDs y expone indices. |

## Relaciones empresariales

```
Process       --contains-->         Activity
Activity      --executed_by-->      Role
Activity      --uses-->             Application
Application   --executes-->         Command          (Command.application_id)
Activity      --consumes/produces-->InformationAsset (ActivityAssetFlow)
Activity      --integrated_with-->  API
Activity      --mitigated_by-->     Control
Activity      --monitored_by-->     KPI
Activity      --bound_to-->         SLA
```

## Regla clave: comandos pertenecen a sistemas

> Los comandos NO pertenecen directamente a la actividad.
> La relacion correcta es: **Actividad -> Sistema -> Comando**.

En el codigo, esto se garantiza porque:

- `Command.application_id: str` es obligatorio.
- `Activity` solo expone `application_ids: list[str]`, NO `command_ids`.
- Para declarar que comandos concretos de un sistema se invocan en una
  actividad, se usa `ActivityApplicationUse(activity_id, application_id,
  command_ids=[...])` en `EnterpriseModel.activity_application_uses`.

## Validaciones integradas

- Unicidad global de `id` por coleccion (validador en `EnterpriseModel`).
- `Command.application_id` obligatorio.
- `Activity.bpmn_type` debe ser un `BpmnType` del subset gobernado.
- `SLA.duration` acepta `timedelta`, numero (horas) o cadena con sufijo
  (`"2h"`, `"30m"`, `"1d"`, `"45s"`).
