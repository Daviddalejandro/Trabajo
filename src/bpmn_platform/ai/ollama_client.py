"""Cliente Ollama minimo (offline-first).

En esta fase solo exponemos:
  * `health()`: detecta si Ollama esta corriendo y que modelos hay.
  * `generate(prompt)`: completion sincrona.

Las fases 4-6 enriqueceran este cliente con prompts especializados,
streaming y manejo de tool calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings
from ..logging_config import get_logger

log = get_logger(__name__)


@dataclass
class OllamaStatus:
    available: bool
    base_url: str
    models: list[str]
    error: str | None = None


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        default_model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.default_model = default_model or settings.ollama_model
        self.timeout = timeout or settings.ollama_timeout_seconds

    def health(self) -> OllamaStatus:
        url = f"{self.base_url}/api/tags"
        try:
            response = httpx.get(url, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return OllamaStatus(available=True, base_url=self.base_url, models=models)
        except Exception as exc:  # noqa: BLE001
            log.warning("Ollama no disponible en {}: {}", self.base_url, exc)
            return OllamaStatus(
                available=False,
                base_url=self.base_url,
                models=[],
                error=str(exc),
            )

    def generate(self, prompt: str, *, model: str | None = None, **options: Any) -> str:
        payload = {
            "model": model or self.default_model,
            "prompt": prompt,
            "stream": False,
            "options": options,
        }
        url = f"{self.base_url}/api/generate"
        response = httpx.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("response", "")
