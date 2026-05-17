"""Launcher one-shot para Anaconda Prompt.

Uso (desde un Anaconda Prompt, parado en la raiz del repo):

    python scripts/run_anaconda.py

Lo que hace:
  1) Verifica que estamos en un entorno conda.
  2) Si la app no esta instalada en el entorno actual, hace `pip install -e .`.
  3) Lanza la aplicacion PyQt6 con `python -m bpmn_platform`.

Diseñado para que el usuario solo necesite copiar/pegar una linea.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _print_step(text: str) -> None:
    print(f"\n\033[1;34m==> {text}\033[0m")


def _ensure_conda_env() -> None:
    """Avisa si no estamos en conda; no detiene la ejecucion."""
    if "CONDA_PREFIX" in os.environ:
        env_name = os.environ.get("CONDA_DEFAULT_ENV", "(sin nombre)")
        print(f"Entorno conda activo: {env_name}")
        return
    print(
        "Aviso: no parece haber un entorno conda activo.\n"
        "Recomendado: abrir 'Anaconda Prompt' y dentro hacer:\n"
        "    conda create -n bpmn python=3.11 -y\n"
        "    conda activate bpmn\n"
        "    python scripts/run_anaconda.py\n"
    )


def _is_installed() -> bool:
    try:
        import bpmn_platform  # noqa: F401
        return True
    except ImportError:
        return False


def _pip_install() -> None:
    _print_step("Instalando dependencias en el entorno actual (pip install -e .)")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-e", str(PROJECT_ROOT)]
    )


def _launch_app() -> int:
    _print_step("Lanzando BPMN Platform")
    return subprocess.call([sys.executable, "-m", "bpmn_platform"])


def main() -> int:
    print("=== BPMN Platform — launcher Anaconda ===")
    _ensure_conda_env()
    if not _is_installed():
        _pip_install()
    else:
        print("BPMN Platform ya esta instalado en el entorno actual.")
    return _launch_app()


if __name__ == "__main__":
    raise SystemExit(main())
