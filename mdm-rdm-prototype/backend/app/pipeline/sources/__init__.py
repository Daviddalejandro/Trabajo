"""Adaptadores por fuente (SPEC §7.1): `extract()` lee el CSV que replica la estructura
nativa y `standardize(payload)` produce el registro canónico. Interfaz limpia para que en
producción el conector real (OData, BAPI, IDoc) sustituya solo `extract()`."""
from importlib import import_module

SOURCES = {
    "sf_ec": ("SF_EC", "stg_sf_ec_raw"),
    "ecc_sd": ("SAP_ECC_SD", "stg_ecc_sd_raw"),
    "ecc_mm": ("SAP_ECC_MM", "stg_ecc_mm_raw"),
    "crm_bp": ("SAP_CRM", "stg_crm_bp_raw"),
    "web_portal": ("WEB_PORTAL", "stg_web_portal_raw"),
    "credito_core": ("CREDITO_CORE", "stg_credito_core_raw"),
}


def get_adapter(source: str):
    if source not in SOURCES:
        raise KeyError(f"Fuente desconocida: {source}. Válidas: {', '.join(SOURCES)}")
    return import_module(f"app.pipeline.sources.{source}")


def read_csv(path) -> list[dict]:
    import csv

    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
