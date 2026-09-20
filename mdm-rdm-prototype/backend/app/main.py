"""Punto de entrada FastAPI (SPEC §11). Prefijo /api/v1; /health también en raíz para
healthchecks de contenedor."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import compliance, health, matches, model, parties, pipeline, rdm
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="Prototipo funcional MDM/RDM in-house · Colsubsidio · Dominio Party. "
    "Opera exclusivamente con datos sintéticos.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(health.router, prefix=settings.api_prefix)
app.include_router(rdm.router, prefix=settings.api_prefix)
app.include_router(pipeline.router, prefix=settings.api_prefix)
app.include_router(matches.router, prefix=settings.api_prefix)
app.include_router(parties.router, prefix=settings.api_prefix)
app.include_router(compliance.router, prefix=settings.api_prefix)
app.include_router(model.router, prefix=settings.api_prefix)

# UI compilada servida por la propia API (un solo puerto, sin CORS): `UI_DIST_DIR=../colab/ui`.
# Va después de los routers para que /api/v1 y /health tengan prioridad; las rutas de la UI son hash (#/…).
if settings.ui_dist_dir and Path(settings.ui_dist_dir).is_dir():
    app.mount("/", StaticFiles(directory=settings.ui_dist_dir, html=True), name="ui")
