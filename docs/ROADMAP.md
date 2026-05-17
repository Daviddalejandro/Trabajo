# Roadmap

Mapeo de las 11 fases del documento maestro al estado actual del repo.

| Fase | Titulo | Estado | Modulos clave |
| ---- | ------ | ------ | ------------- |
| 1 | Fundaciones del Proyecto | **Hecho** | `pyproject.toml`, `app.py`, `logging_config.py`, `agents/`, `ai/`, `scripts/setup_windows.ps1` |
| 2 | Metamodelo Empresarial | **Hecho** | `core/metamodel/`, `core/catalogs/`, `catalogs/*.yaml` |
| 3 | Excel Empresarial | **Hecho** | `excel/schema.py`, `excel/template_builder.py` |
| 4 | Motor de Parsing | **Hecho** | `excel/parser.py`, `agents/parser_agent.py`, `agents/validation_agent.py`, `ui/widgets/issues_view.py` |
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
- **Cargar un Excel diligenciado y obtener un `EnterpriseModel` validado.**
- **Ver en la UI metricas y la tabla de issues (errores/warnings/info).**
- Explorar los catalogos cargados.
- Comprobar el estado de Ollama.
- Ejecutar la pipeline multiagente con ParserAgent + ValidationAgent reales.

## Siguiente sprint sugerido (Fase 5)

1. `agents/semantic_agent.py`: inferencia BPMN sobre filas ambiguas usando
   Ollama (subprocess, eventos implicitos, gateways implicitos).
2. Prompts especializados en `ai/prompts/` (espanol, JSON estructurado).
3. Marcar incertidumbre con codigos `SEM-*` y proponer correcciones.
4. Persistir el `EnterpriseModel` resultante en `data/runtime/*.json`
   para trazabilidad.
