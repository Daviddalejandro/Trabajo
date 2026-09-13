"""Configuración central (SPEC §4). Identificadores en inglés, mensajes en español."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "MDM/RDM Prototipo · Party"
    app_env: str = "prototype"
    api_prefix: str = "/api/v1"
    database_url: str = "postgresql+psycopg://mdm@127.0.0.1:5433/mdm_prototype"
    synth_seed: int = 20260913
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


settings = Settings()
