"""Fixtures F0: migra la base de datos de pruebas a head una vez por sesión y expone
un TestClient. DATABASE_URL apunta por defecto al PostgreSQL local (:5433)."""
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session", autouse=True)
def migrated_db():
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    # F1: el RDM precede al MDM (regla dura §3.1); la semilla es idempotente
    r = subprocess.run([sys.executable, "cli.py", "rdm-seed", "--actor", "pytest"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    yield


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c
