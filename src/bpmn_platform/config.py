"""Configuracion central de la plataforma BPMN."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = PROJECT_ROOT / "catalogs"
DATA_DIR = PROJECT_ROOT / "data"
RUNTIME_DIR = DATA_DIR / "runtime"
EXPORTS_DIR = DATA_DIR / "exports"
LOGS_DIR = PROJECT_ROOT / "logs"


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
