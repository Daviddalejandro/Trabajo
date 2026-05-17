# Parser Excel (Fase 4)

`bpmn_platform.excel.parser.ExcelParser` lee un .xlsx generado con
`build_template` y devuelve un `ParseResult` con:

- `model`: `EnterpriseModel` validado por Pydantic.
- `issues`: lista de `ParseIssue` con severidad, codigo, mensaje y ubicacion.

## Uso programatico

```python
from bpmn_platform.excel.parser import ExcelParser

result = ExcelParser().parse("plantilla.xlsx")
if not result.ok:
    for issue in result.errors:
        print(issue.code, issue.message, issue.location)

model = result.model
print(len(model.activities), "actividades")
```

## Uso desde la UI

`Archivo -> Cargar Excel...` (Ctrl+O) o boton **Cargar Excel...** en la
pantalla **Inicio**. La app:

1. Parsea el archivo.
2. Ejecuta el `Orchestrator` con `ParserAgent` + `ValidationAgent`.
3. Conmuta a la vista **Resultados** mostrando metricas e issues.

## Codigos de issues (parser)

| Codigo                | Severidad | Significado |
| --------------------- | --------- | ----------- |
| `SHEET-MISSING`       | error     | Falta una hoja obligatoria del template. |
| `PROC-ID-MISSING`     | error     | Fila de proceso sin ID. |
| `PROC-ID-DUPLICATE`   | error     | ID de proceso repetido. |
| `PROC-NAME-MISSING`   | error     | Proceso sin nombre. |
| `PROC-ROLE-UNKNOWN`   | warning   | Owner del proceso no esta en catalogo de roles. |
| `PROC-EMPTY`          | error     | Hoja Proceso sin datos. |
| `ACT-ID-MISSING`      | error     | Fila de actividad sin ID. |
| `ACT-ID-DUPLICATE`    | error     | ID de actividad repetido. |
| `ACT-PROC-MISSING`    | error     | Actividad sin proceso asociado. |
| `ACT-PROC-UNKNOWN`    | error     | Actividad referencia proceso inexistente. |
| `ACT-NAME-MISSING`    | error     | Actividad sin nombre. |
| `ACT-EMPTY`           | error     | Hoja Actividades sin datos. |
| `BPMN-TYPE-MISSING`   | error     | Falta el tipo BPMN. |
| `BPMN-TYPE-INVALID`   | error     | Tipo BPMN fuera del subset gobernado. |
| `ACT-ROLE-UNKNOWN`    | warning   | Responsable no esta en catalogo. |
| `ACT-SYSTEM-UNKNOWN`  | warning   | Sistema no esta en catalogo. |
| `ACT-RISK-UNKNOWN`    | warning   | Riesgo no esta en catalogo. |
| `ACT-CONTROL-UNKNOWN` | warning   | Control no esta en catalogo. |
| `CMD-ORPHAN`          | error     | Comando sin Sistema (rompe regla Actividad->Sistema->Comando). |
| `CTRL-RISK-MISMATCH`  | info      | El control elegido no declara mitigacion del riesgo de la fila. |
| `SLA-INVALID`         | error     | SLA con formato no parseable. |
| `MODEL-INVALID`       | error     | Construccion final del `EnterpriseModel` fallo (validacion Pydantic). |
| `NAME-EMPTY`          | error     | (regla nomenclatura) nombre vacio. |
| `NAME-TOO-SHORT`      | error     | (regla nomenclatura) menos de 2 palabras. |
| `NAME-NO-VERB`        | warning   | (regla nomenclatura) no inicia con verbo en infinitivo. |
| `NAME-CAPITALIZATION` | warning   | (regla nomenclatura) no inicia con mayuscula. |

## Codigos de issues (validation agent)

| Codigo            | Severidad | Significado |
| ----------------- | --------- | ----------- |
| `ACT-NO-ROLE`     | warning   | UserTask sin Responsable. |
| `ACT-NO-SYSTEM`   | warning   | ServiceTask sin Sistema. |
| `PROC-NO-ACT`     | warning   | Proceso sin actividades. |
| `RISK-NO-CONTROL` | info      | Riesgo usado sin control declarado. |

## Tolerancia

El parser acepta tanto **codigos** como **etiquetas de negocio** en los
campos con dropdown. Ejemplo: para Tipo BPMN, "StartEvent" y "Inicio"
son equivalentes. Esto facilita la migracion de Excels existentes que
fueron diligenciados antes de homologar los catalogos.

## Reglas estructurales que NO valida (todavia)

Estas validaciones llegan en la Fase 8 (`quality_agent`):

- Conectividad BPMN (todo nodo tiene predecesor y sucesor).
- Gateways balanceados (cada split tiene su join).
- Cobertura inicio/fin por proceso (cada proceso debe tener al menos un
  StartEvent y un EndEvent).
- Deteccion de tareas huerfanas.
