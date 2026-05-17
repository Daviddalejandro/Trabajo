"""Carga y validacion de catalogos YAML.

Los catalogos viven en `catalogs/` (directorio del proyecto). Cada archivo
YAML expone una lista de entradas con al menos `code` y `label`. Los
codigos se usan como valores aceptados por los dropdowns del Excel oficial.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...config import settings


class CatalogEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    description: str | None = None

    @field_validator("code")
    @classmethod
    def _normalize_code(cls, value: str) -> str:
        return value.strip()


class Catalog(BaseModel):
    name: str
    entries: list[CatalogEntry] = Field(default_factory=list)

    @property
    def codes(self) -> list[str]:
        return [entry.code for entry in self.entries]

    @property
    def labels(self) -> list[str]:
        return [entry.label for entry in self.entries]


@dataclass
class CatalogBundle:
    """Conjunto de catalogos cargados del disco."""

    bpmn_types: Catalog
    systems: Catalog
    roles: Catalog
    risks: Catalog
    controls: Catalog
    extras: dict[str, Catalog] = field(default_factory=dict)

    def all(self) -> dict[str, Catalog]:
        base = {
            "bpmn_types": self.bpmn_types,
            "systems": self.systems,
            "roles": self.roles,
            "risks": self.risks,
            "controls": self.controls,
        }
        base.update(self.extras)
        return base


def _read_yaml(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or []
    if not isinstance(data, list):
        raise ValueError(f"El catalogo {path.name} debe ser una lista YAML.")
    return data


def _load_one(catalog_dir: Path, name: str) -> Catalog:
    path = catalog_dir / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Catalogo requerido no encontrado: {path}")
    raw = _read_yaml(path)
    entries = [CatalogEntry(**item) for item in raw]
    return Catalog(name=name, entries=entries)


def load_catalogs(catalog_dir: Path | None = None) -> CatalogBundle:
    """Carga los catalogos canonicos de la plataforma."""
    base = Path(catalog_dir) if catalog_dir else settings.catalog_dir
    return CatalogBundle(
        bpmn_types=_load_one(base, "bpmn_types"),
        systems=_load_one(base, "systems"),
        roles=_load_one(base, "roles"),
        risks=_load_one(base, "risks"),
        controls=_load_one(base, "controls"),
    )
