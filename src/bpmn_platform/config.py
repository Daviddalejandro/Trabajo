"""Configuracion central de la plataforma BPMN."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resource_base() -> Path:
    """Raiz de recursos READ-ONLY (catalogos, assets).

    En modo editable: la raiz del proyecto.
    En binario PyInstaller --onefile: el directorio temporal _MEIPASS.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def _user_state_root() -> Path:
    """Raiz para datos del usuario (logs, exports, runtime), siempre escribibles.

    En modo editable: la raiz del proyecto.
    En binario: %LOCALAPPDATA%/BPMNPlatform (Windows) o ~/.bpmn-platform.
    """
    if getattr(sys, "frozen", False):
        if sys.platform.startswith("win"):
            base = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BPMNPlatform"
        else:
            base = Path.home() / ".bpmn-platform"
        return base
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _resource_base()
CATALOG_DIR = PROJECT_ROOT / "catalogs"

_STATE_ROOT = _user_state_root()
DATA_DIR = _STATE_ROOT / "data"
RUNTIME_DIR = DATA_DIR / "runtime"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = _STATE_ROOT / "logs"


class AppSettings(BaseSettings):
    """Settings de la aplicacion. Sobrescribibles via variables BPMN_*."""

    model_config = SettingsConfigDict(env_prefix="BPMN_", env_file=".env", extra="ignore")

    app_name: str = "BPMN Platform"
    app_version: str = "0.1.0"

    # Directorios
    catalog_dir: Path = Field(default=CATALOG_DIR)
    runtime_dir: Path = Field(default=RUNTIME_DIR)
    exports_dir: Path = Field(default=EXPORTS_DIR)
    logs_dir: Path = Field(default=LOGS_DIR)

    # Logging
    log_level: str = "INFO"
    log_retention_days: int = 14

    # Motor IA (Ollama, offline-first)
    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout_seconds: int = 60

    def ensure_dirs(self) -> None:
        for path in (self.runtime_dir, self.exports_dir, self.logs_dir):
            path.mkdir(parents=True, exist_ok=True)


settings = AppSettings()
