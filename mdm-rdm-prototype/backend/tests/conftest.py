"""Fixtures F0: migra la base de datos de pruebas a head una vez por sesión y expone
un TestClient. DATABASE_URL apunta por defecto al PostgreSQL local (:5433)."""
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient


def run(*args: str) -> subprocess.CompletedProcess:
    r = subprocess.run([sys.executable, *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    """Reconstruye la base desde cero para que la suite sea determinista:
    esquemas → migraciones → semilla RDM (§3.1: el RDM precede al MDM) → sintéticos → ingesta de las 5 fuentes."""
    from sqlalchemy import text
    from app.core.db import engine

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS staging CASCADE; DROP SCHEMA IF EXISTS mdm CASCADE; DROP SCHEMA IF EXISTS rdm CASCADE; "
                          "DROP TABLE IF EXISTS public.alembic_version"))
    run("-m", "alembic", "upgrade", "head")
    run("cli.py", "rdm-seed", "--actor", "pytest")
    run("cli.py", "synth-generate")
    run("cli.py", "ingest", "--source", "all", "--actor", "pytest")
    yield


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c
