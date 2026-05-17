# Roadmap

Mapeo de las 11 fases del documento maestro al estado actual del repo.

| Fase | Titulo | Estado | Modulos clave |
| ---- | ------ | ------ | ------------- |
| 1 | Fundaciones del Proyecto | **Hecho** | `pyproject.toml`, `app.py`, `logging_config.py`, `agents/`, `ai/`, `scripts/setup_windows.ps1` |
| 2 | Metamodelo Empresarial | **Hecho** | `core/metamodel/`, `core/catalogs/`, `catalogs/*.yaml` |
| 3 | Excel Empresarial | **Hecho** | `excel/schema.py`, `excel/template_builder.py` |
| 4 | Motor de Parsing | Pendiente | `agents/parser_agent.py` (placeholder), futuro `excel/parser.py` |
| 5 | Motor Semantico IA | Pendiente | `agents/semantic_agent.py` (placeholder), `ai/ollama_client.py` listo |
| 6 | Generador BPMN | Pendiente | `bpmn/` (a crear con `lxml`) |
| 7 | Modelo Sistema -> Comando | Estructural listo | `Command.application_id` obligatorio, `ActivityApplicationUse` |
| 8 | Validacion BPMN | Parcial | `core/governance/rules.py` (nombre actividad); falta validador BPMN |
| 9 | Visualizacion Profesional | Pendiente | Embedding `bpmn-js` via `QtWebEngineView` |
| 10 | Gobierno y Observabilidad | Parcial | Logging con loguru; falta versionamiento/auditoria |
| 11 | Capacidades Futuras | Pendiente | Process mining, RPA, DMN, Neo4j |

## Lo que YA puede hacerse con esta version

- Abrir la app PyQt6 en Windows.
- Generar la plantilla Excel oficial con dropdowns y validaciones.
- Explorar los catalogos cargados.
- Comprobar el estado de Ollama.
- Ejecutar la pipeline multiagente en modo `dry-run` (placeholders).

## Siguiente sprint sugerido (Fase 4 + inicio Fase 5)

1. `excel/parser.py`: leer la plantilla y producir un `EnterpriseModel`.
2. `agents/parser_agent.py`: integrar el parser en la pipeline.
3. `agents/validation_agent.py`: aplicar `governance/rules.py` masivamente.
4. Persistir issues en `data/runtime/issues.json` (auditoria).
5. Mostrar en la UI una vista "Issues" con resultado del parsing.
