from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import settings
from app.core.db import db_ping, existing_schemas

router = APIRouter(tags=["salud"])

REQUIRED_SCHEMAS = {"rdm", "mdm", "staging"}


@router.get("/health", summary="Estado del servicio y de la base de datos")
def health() -> JSONResponse:
    try:
        db_ok = db_ping()
        schemas = existing_schemas()
    except Exception as exc:  # noqa: BLE001 — se reporta, no se oculta
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "error", "detail": str(exc), "version": __version__},
        )
    missing = sorted(REQUIRED_SCHEMAS - schemas)
    return JSONResponse(
        status_code=200 if db_ok and not missing else 503,
        content={
            "status": "ok" if db_ok and not missing else "degraded",
            "db": "ok" if db_ok else "error",
            "schemas_missing": missing,
            "env": settings.app_env,
            "version": __version__,
            "banner": "Prototipo — datos sintéticos",
        },
    )
