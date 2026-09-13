"""Etapa 4 · Homologación (SPEC §7): resuelve cada código fuente contra
VW_RDM_SOURCE_TO_CANONICAL; los códigos ya canónicos se resuelven por CATALOG_CODE +
VALUE_CODE (regla dura §3.4). Sin mapeo → 0 = UNKNOWN + hallazgo VALIDITY (lo emite DQ)."""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


class Homologator:
    def __init__(self, session: Session, source_system_cd: str):
        self.system = source_system_cd
        rows = session.execute(text(
            "SELECT source_field, source_value, value_sk, value_code FROM rdm.vw_rdm_source_to_canonical WHERE source_system_cd=:s"),
            {"s": source_system_cd}).all()
        self.mappings = {(r[0], r[1]): (r[2], r[3]) for r in rows}
        self.catalogs: dict[str, dict[str, dict]] = {}
        for r in session.execute(text(
                "SELECT catalog_code, value_code, value_sk, parent_value_code FROM rdm.vw_rdm_lookup WHERE is_active")).all():
            self.catalogs.setdefault(r[0], {})[r[1]] = {"sk": r[2], "parent": r[3], "attrs": {}}
        by_sk = {v["sk"]: v for cat in self.catalogs.values() for v in cat.values()}
        for r in session.execute(text("SELECT value_sk, field_code, field_value FROM rdm.reference_field_value")).all():
            if r[0] in by_sk:
                by_sk[r[0]]["attrs"][r[1]] = r[2]
        self.by_sk = by_sk

    # ------------------------------------------------------------------ consultas
    def info(self, catalog: str, code: str | None) -> dict | None:
        return self.catalogs.get(catalog, {}).get(code) if code else None

    def sk(self, catalog: str, code: str) -> int:
        i = self.info(catalog, code)
        if i is None:
            raise LookupError(f"RDM: {catalog}.{code} no existe o está deprecado")
        return i["sk"]

    def code_of(self, sk: int) -> str | None:
        if sk == 0:
            return "UNKNOWN"
        if sk == -1:
            return "NOT_APPLICABLE"
        for cat in self.catalogs.values():
            for code, v in cat.items():
                if v["sk"] == sk:
                    return code
        return None

    # ------------------------------------------------------------------ resolución
    def resolve(self, entry: dict) -> dict:
        if entry.get("field") is None:
            info = self.info(entry["catalog"], entry["raw"])
        else:
            hit = self.mappings.get((entry["field"], entry["raw"]))
            info = self.info(entry["catalog"], hit[1]) if hit else None
        if info:
            entry.update(sk=info["sk"], code=next(c for c, v in self.catalogs[entry["catalog"]].items() if v["sk"] == info["sk"]),
                         parent=info["parent"], attrs=info["attrs"], unknown=False)
        else:
            entry.update(sk=0, code=None, parent=None, attrs={}, unknown=True, issue_key=uuid.uuid4().hex)
        return entry

    def resolve_all(self, std: dict) -> list[dict]:
        """Recorre el registro estandarizado y resuelve in situ toda entrada de código."""
        unresolved: list[dict] = []

        def walk(node):
            if isinstance(node, dict):
                if {"field", "raw", "catalog"} <= node.keys() and "sk" not in node:
                    self.resolve(node)
                    if node["unknown"]:
                        unresolved.append(node)
                    return
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)

        walk(std)
        return unresolved
