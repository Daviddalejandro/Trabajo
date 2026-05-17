# Empaquetado del .exe para Windows

La plataforma se distribuye como un binario `BPMNPlatform.exe` autónomo
(no requiere Python ni dependencias instaladas en el equipo destino).

## Opción A — Descargar el .exe pre-compilado (recomendado)

Cada push a la rama `claude/**` o `main` dispara automáticamente el
workflow **Build Windows .exe**, que compila el binario en un runner
`windows-latest` y lo publica como artefacto.

**Pasos para descargarlo:**

1. Abre el repo:
   https://github.com/daviddalejandro/trabajo/actions/workflows/build-windows.yml
2. Espera a que el último run termine (~3-5 min, ícono verde ✓).
3. Haz clic sobre el run.
4. En la parte inferior de la página, sección **Artifacts**, descarga
   **`BPMNPlatform-windows-<sha>`**.
5. Descomprime el `.zip`. Adentro está `BPMNPlatform.exe`.
6. Doble clic para abrir la app.

> El artefacto queda disponible 30 días. Si lo necesitas más tiempo,
> creamos un Release en GitHub que lo conserva indefinidamente.

## Opción B — Compilarlo tú mismo en Windows

Si quieres modificar el código y compilarlo localmente:

```powershell
# 1) Setup base
git clone -b claude/create-windows-tool-RvtER https://github.com/daviddalejandro/trabajo.git
cd trabajo
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\setup_windows.ps1

# 2) Activar venv e instalar la extra "build"
.\.venv\Scripts\Activate.ps1
pip install -e ".[build]"

# 3) Compilar
pyinstaller packaging\BPMNPlatform.spec --noconfirm --clean

# 4) Ejecutar
.\dist\BPMNPlatform.exe
```

## Estructura del binario

`BPMNPlatform.exe` es un ejecutable **single-file** (PyInstaller `--onefile`).
Al lanzarse extrae temporalmente a `%TEMP%\_MEI*\` los recursos:

- `catalogs/*.yaml` (catálogos controlados)
- `bpmn_platform/ui/resources/*.svg` (logo Colsubsidio)
- runtime Python + Qt DLLs

Los datos de usuario (logs, exports) se escriben en:

- `%LOCALAPPDATA%\BPMNPlatform\logs\`
- `%LOCALAPPDATA%\BPMNPlatform\data\exports\`

## Modificar catálogos en un .exe ya distribuido

Los catálogos vienen embebidos. Para que los usuarios finales puedan
editarlos sin recompilar (próxima iteración) hay dos caminos:

1. **Catálogos externos**: dejar `catalogs\` en la misma carpeta que
   `BPMNPlatform.exe`; la app prioriza ese path sobre los bundleados.
2. **Editor en-app**: vista CRUD sobre los YAML (Fase 11 extensión).

Por ahora, regenera el `.exe` después de tocar `catalogs/*.yaml`.
