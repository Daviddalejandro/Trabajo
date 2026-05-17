"""Entry point dedicado para PyInstaller.

`src/bpmn_platform/app.py` usa imports relativos (`from .config import ...`)
porque se importa como modulo (`python -m bpmn_platform`, entry_point
`bpmn-platform`). PyInstaller, en cambio, ejecuta el archivo de entrada
como script suelto y los imports relativos fallan con:

    ImportError: attempted relative import with no known parent package

Este launcher fuerza la importacion del paquete completo y delega en
`bpmn_platform.app.run`, manteniendo `app.py` intacto.
"""
from __future__ import annotations

import multiprocessing

from bpmn_platform.app import run


if __name__ == "__main__":
    # Necesario en Windows para que multiprocessing funcione en binarios
    # frozen (PyInstaller). Es no-op si no se usa multiprocessing.
    multiprocessing.freeze_support()
    raise SystemExit(run())
