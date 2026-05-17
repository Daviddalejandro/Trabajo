# Cómo correr BPMN Platform con Anaconda (Windows)

Esta guía asume que ya tienes **Anaconda** instalado (con Python 3.11+).
No necesitas instalar Python adicional, ni un `venv` aparte, ni PyInstaller.

## Camino corto (recomendado)

1. Descarga el código:
   - Opción A — `git clone`:
     ```
     git clone -b claude/create-windows-tool-RvtER https://github.com/daviddalejandro/trabajo.git
     ```
   - Opción B — descarga el `.zip` del branch desde GitHub y descomprime.

2. **Abre el "Anaconda Prompt"** desde el menú Inicio
   (NO la PowerShell normal — el Anaconda Prompt ya trae `conda` en el PATH).

3. Entra a la carpeta del repo:
   ```
   cd ruta\donde\esta\trabajo
   ```

4. Crea un entorno limpio (solo la primera vez):
   ```
   conda create -n bpmn python=3.11 -y
   conda activate bpmn
   ```

5. Instala la app + dependencias y lánzala (un solo comando):
   ```
   python scripts\run_anaconda.py
   ```

Eso es todo. La ventana PyQt6 se abrirá. Próximas veces basta con:

```
conda activate bpmn
python scripts\run_anaconda.py
```

## Camino manual (si prefieres entender qué pasa)

```
conda create -n bpmn python=3.11 -y
conda activate bpmn
pip install -e .
bpmn-platform
```

## Probar el demo HR sin abrir la app

Con el entorno `bpmn` activo:

```
python -m examples.build_hr_excel -o vinculacion.xlsx
python -m examples.onboarding_demo -o .\salida_demo
```

El segundo comando genera el Excel de muestra (Onboarding clientes),
corre la pipeline completa y deja en `.\salida_demo\` el `.bpmn`,
el `.svg`, el `.json` y el **reporte HTML** (doble clic para verlo en
el navegador).

## ¿Qué pasa con Spyder / Jupyter?

- **Spyder**: PyQt6 puede chocar con el intérprete IPython embebido de
  Spyder (ambos pelean por el event loop). No recomendado para lanzar
  la app desktop. Sí sirve para editar código.
- **Jupyter**: las apps de escritorio PyQt6 no corren bien dentro de un
  notebook. Para inspeccionar el modelo o el parser, sí funciona:

  ```python
  from bpmn_platform.excel.parser import ExcelParser
  result = ExcelParser().parse(r"C:\ruta\a\vinculacion.xlsx")
  print(len(result.model.activities), "actividades")
  for issue in result.issues:
      print(issue.severity.value, issue.code, issue.message)
  ```

## Resolución de problemas

| Síntoma | Causa probable | Solución |
| --- | --- | --- |
| `conda: command not found` | No estás en Anaconda Prompt | Cierra y reabre desde "Anaconda Prompt" |
| `ImportError: PyQt6` | El entorno no se instaló | Repite `pip install -e .` con `bpmn` activo |
| Ventana no aparece | Tarjeta de video sin OpenGL básico | Define `set QT_OPENGL=software` antes de lanzar |
| Fonts raras | Falta refresco de fuentes Windows | Reiniciar el equipo o ejecutar como administrador la 1ª vez |
| `Excel cargado: 0 actividades` | El Excel se diligenció sin respetar el dropdown de "Tipo BPMN" | Usa la plantilla `Archivo → Generar plantilla Excel...` |

## Desinstalar

```
conda activate bpmn
pip uninstall bpmn-platform -y
conda deactivate
conda env remove -n bpmn
```
