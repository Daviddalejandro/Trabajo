# Arquitectura

```
+------------------------------------------------------------+
|                       UI (PyQt6)                           |
|  HomeView | CatalogView | AboutView | (futuro: BPMN view)  |
+----------------------------+-------------------------------+
                             |
                             v
+------------------------------------------------------------+
|                  Capa de orquestacion                      |
|              agents/  -  Orchestrator + Agents             |
|   parser | validation | semantic | bpmn | governance |     |
|   metadata | quality | export | recommendation             |
+----------------------------+-------------------------------+
                             |
              +--------------+---------------+
              |              |               |
              v              v               v
   +-----------------+ +-------------+ +----------------+
   |   Excel layer   | |  core/      | |    ai/         |
   |  (openpyxl)     | |  metamodel  | |  Ollama client |
   |  template_      | |  catalogs   | |                |
   |  builder        | |  governance | |                |
   +--------+--------+ +------+------+ +-------+--------+
            |                 |                |
            v                 v                v
        plantilla        YAML controlados   modelos LLM
        oficial          (catalogs/)        locales
```

## Flujo objetivo (cuando se completen las fases 4-9)

```
Excel oficial  -->  Parser Agent (openpyxl)  -->  EnterpriseModel (pydantic)
                                  |
                                  v
                          Validation Agent  --> issues
                                  |
                                  v
                         Semantic Agent  (Ollama)  --> inferencias BPMN
                                  |
                                  v
                         BPMN Agent (lxml)  --> BPMN 2.0 XML
                                  |
                                  v
                       Quality / Governance Agents
                                  |
                                  v
                       Export Agent  --> XML / SVG / PNG / PDF
```

## Decisiones clave

1. **Python puro** (PyQt6 + openpyxl) para simplificar empaquetado a `.exe`
   con PyInstaller y mantener todo el stack en un solo runtime.
2. **Catalogos en YAML** versionables en git, sin depender de DB.
3. **Pydantic v2** como contrato unico entre capas. La validacion ocurre
   en el modelo, no en la UI ni en el parser.
4. **Multiagente desde el dia 1**, aunque con placeholders. Esto evita
   refactors estructurales cuando entren las fases 4-9.
5. **Ollama (offline-first)** como motor IA por defecto: los Excels
   empresariales no salen del equipo del usuario.
6. **Regla Actividad -> Sistema -> Comando** materializada en el
   metamodelo: `Command.application_id` es obligatorio, `Activity` solo
   referencia aplicaciones.
