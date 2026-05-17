# PyInstaller spec para BPMN Platform (Windows --onefile).
#
# Uso (en Windows, dentro de un venv con el proyecto instalado):
#   pyinstaller packaging/BPMNPlatform.spec --noconfirm
#
# El binario final queda en dist/BPMNPlatform.exe
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve().parent

# Datos a embeber dentro del binario.
datas = [
    # Catalogos YAML (semilla read-only; quedan dentro del bundle).
    (str(PROJECT_ROOT / "catalogs"), "catalogs"),
    # Recursos de marca Colsubsidio.
    (
        str(PROJECT_ROOT / "src" / "bpmn_platform" / "ui" / "resources"),
        "bpmn_platform/ui/resources",
    ),
]

# Modulos que PyInstaller a veces no detecta por su analisis estatico.
hidden_imports = [
    *collect_submodules("bpmn_platform"),
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "openpyxl",
    "openpyxl.cell._writer",
    "yaml",
    "lxml",
    "lxml.etree",
    "loguru",
    "httpx",
    # PyQt6 modulos que importamos en la app.
    "PyQt6.QtCore",
    "PyQt6.QtGui",
    "PyQt6.QtWidgets",
    "PyQt6.QtSvg",
    "PyQt6.QtSvgWidgets",
]


a = Analysis(
    [str(PROJECT_ROOT / "src" / "bpmn_platform" / "app.py")],
    pathex=[str(PROJECT_ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Modulos pesados que no usamos.
        "tkinter",
        "test",
        "unittest",
        "PyQt6.QtBluetooth",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSensors",
        "PyQt6.QtPositioning",
        "PyQt6.QtTest",
        "PyQt6.QtNfc",
        "PyQt6.QtWebChannel",
        "PyQt6.QtWebSockets",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtCharts",
        "PyQt6.QtDataVisualization",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BPMNPlatform",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,                       # ventana sin consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                           # opcional: ruta a .ico
)
