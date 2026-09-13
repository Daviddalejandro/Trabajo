"""Punto de entrada FastAPI (SPEC §11). Prefijo /api/v1; /health también en raíz para
healthchecks de contenedor."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health, matches, parties, pipeline, rdm
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
