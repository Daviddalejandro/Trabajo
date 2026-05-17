# Demo end-to-end — Onboarding de clientes

Ejemplo completo que ejecuta las 11 fases sobre un Excel ya diligenciado:

```
Excel (Onboarding clientes)
    -> parser
    -> validation
    -> semantic (Ollama opcional, fallback reglas)
    -> bpmn (XML 2.0 + BPMNDI)
    -> quality (score 0-100)
    -> governance (audit log + cobertura riesgo->control)
    -> metadata (JSON estructurado)
    -> export (BPMN, SVG, JSON metadata)
    -> recommendation
```

## Ejecutar

Desde la raiz del proyecto, con `.venv` activado:

```powershell
# 1) Generar Excel de muestra + procesar end-to-end
python -m examples.onboarding_demo

# Cambiar carpeta destino
python -m examples.onboarding_demo -o C:\bpmn\salida
```

El script imprime el resumen por agente, los issues y la lista de
artefactos generados.

## Artefactos producidos

| Archivo                              | Tipo       | Uso                              |
| ------------------------------------ | ---------- | -------------------------------- |
| `sample_onboarding.xlsx`             | Excel      | Modelo fuente (editable).        |
| `bpmn_<timestamp>.bpmn`              | BPMN 2.0   | Abrible en Camunda Modeler, bpmn.io, Signavio. |
| `bpmn_<proceso>_<timestamp>.svg`     | SVG        | Diagrama BPMN renderizable en navegador / Qt. |
| `bpmn_metadata_<timestamp>.json`     | JSON       | Resumen estructurado + score de calidad. |

Adicionalmente, en `logs/audit/audit_YYYYMMDD.jsonl` queda registrado el
evento `pipeline_run` con su payload (procesos, # actividades, # hallazgos).

## Probar la app

```powershell
bpmn-platform
```

1. **Archivo -> Cargar Excel...** (Ctrl+O) y selecciona el .xlsx generado.
2. La aplicacion conmuta automaticamente a la vista **Diagrama BPMN** y
   muestra el SVG con zoom/pan.
3. La pestana **Resultados** lista issues del parser, validation,
   semantic, quality, governance y recommendation.
4. **Archivo -> Exportar BPMN/SVG/JSON...** (Ctrl+E) para volver a
   generar artefactos en la carpeta que prefieras.

## Editar el Excel y ver el impacto

1. Abre el Excel y modifica una actividad: cambia su Sistema, agrega un
   Riesgo, etc.
2. Vuelve a cargar el archivo desde la app (`Ctrl+O`).
3. El SVG, el BPMN XML y el score de calidad se regeneran al instante.

## Activar IA local (opcional)

Con Ollama instalado y un modelo descargado:

```powershell
$env:BPMN_OLLAMA_ENABLED = "true"
$env:BPMN_OLLAMA_MODEL = "llama3.1:8b"
python -m examples.onboarding_demo
```

El `SemanticAgent` aumentara los hallazgos con sugerencias generadas
por el LLM (codigo `SEM-LLM`). Si Ollama no esta disponible, degrada con
gracia y la pipeline continua sin perder funcionalidad.
