# Roadmap

Mapeo de las 11 fases del documento maestro al estado actual del repo.

| Fase | Titulo | Estado | Modulos clave |
| ---- | ------ | ------ | ------------- |
| 1 | Fundaciones del Proyecto | **Hecho** | `pyproject.toml`, `app.py`, `logging_config.py`, `agents/`, `ai/`, `scripts/setup_windows.ps1` |
| 2 | Metamodelo Empresarial | **Hecho** | `core/metamodel/`, `core/catalogs/`, `catalogs/*.yaml` |
| 3 | Excel Empresarial | **Hecho** | `excel/schema.py`, `excel/template_builder.py` |
| 4 | Motor de Parsing | **Hecho** | `excel/parser.py`, `agents/parser_agent.py`, `agents/validation_agent.py`, `ui/widgets/issues_view.py` |
| 5 | Motor Semantico IA | **Hecho** | `agents/semantic_agent.py` (reglas + Ollama opcional), `ai/ollama_client.py` |
| 6 | Generador BPMN 2.0 | **Hecho** | `bpmn/generator.py`, `bpmn/layout.py`, `agents/bpmn_agent.py` |
| 7 | Sistema -> Comando | **Hecho** | `Command.application_id` obligatorio, `ActivityApplicationUse`, parser, GovernanceAgent |
| 8 | Validacion BPMN | **Hecho** | `bpmn/quality.py` (score 0-100), `agents/quality_agent.py` |
| 9 | Visualizacion Profesional | **Hecho** | `bpmn/export.py` (SVG), `ui/widgets/bpmn_view.py`, exportacion XML/SVG/JSON |
| 10 | Gobierno y Observabilidad | **Hecho** | `governance/audit.py` (JSONL), `agents/governance_agent.py`, loguru |
| 11 | Capacidades Futuras | **Hecho (stubs)** | `integrations/stubs.py` (Process Mining, RPA, DMN, IA generativa, Neo4j, simulacion, EDA) |

## Lo que YA puede hacerse con esta version

- Abrir la app PyQt6 en Windows.
- Generar la plantilla Excel oficial con dropdowns y validaciones.
- Cargar un Excel diligenciado y obtener un `EnterpriseModel` validado.
- **Generar BPMN 2.0 XML compatible con Camunda Modeler / bpmn.io.**
- **Visualizar el diagrama BPMN renderizado en SVG dentro de la app (zoom/pan).**
- **Validar la calidad BPMN (score 0-100) con criterios estructurales y empresariales.**
- **Exportar XML, SVG y JSON metadata a una carpeta destino.**
- Ejecutar la pipeline multiagente completa (9 agentes reales).
- Auditar cada corrida en `logs/audit/audit_YYYYMMDD.jsonl`.
- Demo end-to-end via `python -m examples.onboarding_demo`.

## Que falta para subir el nivel a produccion

Estas son extensiones naturales sobre las fases ya implementadas:

1. **Sub-procesos BPMN**: implementar `<bpmn:subProcess>` con expand/collapse.
2. **Lanes y Pools**: separar visualmente por Role o Application.
3. **Dataflow visible**: dibujar `dataObjectReference` y asociaciones.
4. **Editor BPMN bidireccional**: permitir editar el SVG y propagar al modelo.
5. **Persistencia versionada**: SQLite con historico de cambios por proceso.
6. **Tests E2E con PyQt6**: usar pytest-qt para cubrir la UI.
7. **Empaquetado**: PyInstaller spec + firmado opcional con osslsigncode.
8. **Adaptadores reales para Fase 11**:
   - Camunda Cloud (subir BPMN via API).
   - Celonis / Disco (process mining).
   - Neo4j (cargar el `EnterpriseModel` como grafo).

Cada uno se conecta sobre las interfaces existentes (`integrations/stubs.py`)
sin modificar las fases 1-10.
