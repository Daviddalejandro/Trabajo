# BPMN Platform — Plataforma BPMN Inteligente (Open Source)

Aplicacion de escritorio para Windows que transforma archivos Excel
empresariales estructurados en BPMN 2.0 valido, con metadata empresarial,
relaciones de arquitectura y gobierno.

Stack 100% Open Source:

- **UI desktop**: PyQt6
- **Excel**: openpyxl (plantilla oficial con dropdowns y validaciones)
- **Metamodelo**: Pydantic v2
- **Catalogos**: YAML
- **Logging**: loguru
- **Motor IA local (offline-first)**: Ollama + httpx
- **BPMN XML (fase 6)**: lxml

> Estado actual: **las 11 fases del documento maestro implementadas**
> (Fase 11 con stubs declarativos listos para extension). Demo end-to-end
> ejecutable en una linea — ver `docs/DEMO.md`.

---

## Requisitos previos (Windows)

1. **Python 3.11+** (https://www.python.org/downloads/windows/).
   Marca "Add Python to PATH" durante la instalacion.
2. **PowerShell 5.1+** (incluido en Windows 10/11).
3. *(Opcional — solo para el motor IA)* **Ollama** (https://ollama.com).

---

## Instalacion rapida

### Opción 1 — Con Anaconda (recomendado si ya tienes Anaconda)

Ver guía detallada en [`docs/RUN_ANACONDA.md`](docs/RUN_ANACONDA.md).

```
# Desde Anaconda Prompt, dentro de la carpeta del repo
conda create -n bpmn python=3.11 -y
conda activate bpmn
python scripts\run_anaconda.py
```

### Opción 2 — Con Python + venv

```powershell
git clone https://github.com/daviddalejandro/trabajo.git
cd trabajo
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\setup_windows.ps1
.\.venv\Scripts\Activate.ps1
bpmn-platform
```

### Opción 3 — Binario .exe (sin Python instalado)

Ver [`docs/BUILD.md`](docs/BUILD.md). Descarga el artefacto desde la
pestaña Actions del repo y ejecutas el `.exe` directamente.

---

## Demo end-to-end en 1 comando

Genera un Excel de muestra **"Onboarding de clientes"**, ejecuta los 9
agentes y produce BPMN 2.0 XML + SVG + JSON metadata en una sola
corrida:

```powershell
.\.venv\Scripts\Activate.ps1
python -m examples.onboarding_demo
```

Salida tipica:

```
[1/3] Excel de muestra generado -> data\exports\demo_onboarding\sample_onboarding.xlsx
[2/3] Pipeline ejecutado (9 agentes).

Resultados por agente:
  [OK ] parser         Procesos: 1, Actividades: 6, Eventos: 3, Gateways: 1. Errores: 0, Warnings: 0.
  [OK ] validation     Validaciones empresariales: 0 hallazgos.
  [OK ] semantic       Inferencias semanticas: 0 hallazgos.
  [OK ] bpmn           BPMN XML generado (6404 bytes, 1 diagramas).
  [OK ] quality        Calidad BPMN: score 100/100 - 0 errores, 0 warnings, 0 infos.
  [OK ] governance     Gobierno empresarial: 0 hallazgos.
  [OK ] metadata       Metadata empresarial: 6 actividades en 1 procesos.
  [OK ] export         Exportados 3 archivo(s) en data\exports\demo_onboarding.
  [OK ] recommendation 1 recomendaciones propuestas.

[3/3] Artefactos generados en data\exports\demo_onboarding:
  - bpmn_<timestamp>.bpmn
  - bpmn_PROC-ONBOARDING_<timestamp>.svg
  - bpmn_metadata_<timestamp>.json
```

Detalle completo en `docs/DEMO.md`.

## Generar la plantilla Excel oficial (en blanco)

Desde la app: menu **Archivo → Generar plantilla Excel...**

Desde la CLI:

```powershell
bpmn-template -o .\plantilla_bpmn.xlsx
```

La plantilla incluye:

- Hoja **Instrucciones** con las reglas de diligenciamiento.
- Hoja **Proceso** con metadata del proceso (1 fila).
- Hoja **Actividades** con dropdowns y validaciones por columna.
- Hoja **Catalogos** con todos los valores aceptados (tipos BPMN,
  sistemas, roles, riesgos, controles).

Regla obligatoria del modelo:

```
Actividad  ->  Sistema  ->  Comando
```

---

## Motor IA (Ollama)

La plataforma usa Ollama como motor IA local para mantener los datos
empresariales en el equipo del usuario.

```powershell
# Instalacion guiada y descarga del modelo por defecto
.\scripts\install_ollama.ps1
```

Cambiar modelo via variable de entorno:

```powershell
$env:BPMN_OLLAMA_MODEL = "qwen2.5:14b"
bpmn-platform
```

Desde la app puedes comprobar el estado con **Herramientas → Comprobar
Ollama**.

---

## Catalogos controlados

Los catalogos viven en `catalogs/*.yaml` y son la unica fuente para los
dropdowns del Excel oficial. Editar con autorizacion del equipo de
arquitectura empresarial.

| Archivo | Contenido |
| --- | --- |
| `bpmn_types.yaml` | Tipos BPMN permitidos (StartEvent, UserTask, ...). |
| `systems.yaml` | Sistemas / aplicaciones corporativas. |
| `roles.yaml` | Roles / responsables. |
| `risks.yaml` | Riesgos homologados. |
| `controls.yaml` | Controles que mitigan los riesgos. |

Tras editarlos, en la app: **Herramientas → Recargar catalogos** (`F5`).

---

## Estructura del repositorio

```
.
├── catalogs/                       # YAML controlados (dropdowns Excel)
├── examples/                       # Demo end-to-end + Excel de muestra
├── scripts/                        # PowerShell para setup Windows
├── src/bpmn_platform/
│   ├── agents/                     # Multiagente real (9 agentes)
│   ├── ai/                         # Cliente Ollama (offline-first)
│   ├── bpmn/                       # Generador BPMN 2.0, layout, quality, SVG
│   ├── core/
│   │   ├── catalogs/               # Loader YAML
│   │   ├── governance/             # Reglas de gobierno
│   │   └── metamodel/              # Entidades Pydantic
│   ├── excel/                      # Plantilla oficial + parser
│   ├── governance/                 # Audit log JSONL
│   ├── integrations/               # Stubs para Process Mining, RPA, DMN, ...
│   ├── ui/                         # PyQt6 (MainWindow + vistas + visor BPMN)
│   ├── app.py                      # Entry point
│   └── config.py                   # Settings (overridables con BPMN_*)
├── tests/                          # pytest (22+ tests)
├── docs/                           # ARCHITECTURE, METAMODEL, PARSER, DEMO, ROADMAP
├── pyproject.toml
└── README.md
```

---

## Tests

```powershell
.\.venv\Scripts\Activate.ps1
pytest
```

---

## Empaquetado a `.exe` (futuro)

```powershell
pip install -e ".[build]"
pyinstaller --name BPMNPlatform --windowed --onefile `
  --add-data "catalogs;catalogs" `
  src/bpmn_platform/app.py
```

El binario quedara en `dist\BPMNPlatform.exe`.

---

## Roadmap

Consulta `docs/ROADMAP.md` para el detalle de las 11 fases del documento
maestro y el estado de cada una.

---

## Licencia

Apache-2.0.
