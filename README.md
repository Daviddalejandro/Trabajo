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

> Estado actual: **Fases 1, 2 y 3** del documento maestro implementadas.
> Fases 4-11 (parser, motor semantico IA, generador BPMN, validador,
> visualizacion, gobierno, exportacion) estan andamiadas y se construyen
> incrementalmente.

---

## Requisitos previos (Windows)

1. **Python 3.11+** (https://www.python.org/downloads/windows/).
   Marca "Add Python to PATH" durante la instalacion.
2. **PowerShell 5.1+** (incluido en Windows 10/11).
3. *(Opcional — solo para el motor IA)* **Ollama** (https://ollama.com).

---

## Instalacion rapida

```powershell
# 1) Clonar
git clone https://github.com/daviddalejandro/trabajo.git
cd trabajo

# 2) Habilitar scripts (una sola vez)
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 3) Setup automatico (crea .venv e instala dependencias)
.\scripts\setup_windows.ps1

# 4) Ejecutar la app
.\.venv\Scripts\Activate.ps1
bpmn-platform
```

---

## Generar la plantilla Excel oficial

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
├── scripts/                        # PowerShell para setup Windows
├── src/bpmn_platform/
│   ├── agents/                     # Esqueleto multiagente
│   ├── ai/                         # Cliente Ollama
│   ├── core/
│   │   ├── catalogs/               # Loader YAML
│   │   ├── governance/             # Reglas de gobierno
│   │   └── metamodel/              # Entidades Pydantic
│   ├── excel/                      # Plantilla Excel oficial
│   ├── ui/                         # PyQt6 (MainWindow + vistas)
│   ├── app.py                      # Entry point
│   └── config.py                   # Settings (overridables con BPMN_*)
├── tests/                          # pytest
├── docs/                           # Documentacion tecnica
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
