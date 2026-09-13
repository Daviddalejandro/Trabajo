"""F0 · criterios de aceptación (SPEC §14): /health OK, esquemas creados, CLI operativa."""
import subprocess
import sys

from app.core.db import existing_schemas


def test_health_root(client):
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok" and body["db"] == "ok"
    assert body["schemas_missing"] == []
    assert body["banner"] == "Prototipo — datos sintéticos"


def test_health_under_api_prefix(client):
    assert client.get("/api/v1/health").status_code == 200


def test_schemas_exist():
    assert {"rdm", "mdm", "staging"} <= existing_schemas()


def test_pg_trgm_installed(client):
    from sqlalchemy import text
    from app.core.db import engine

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_extension WHERE extname='pg_trgm'")).scalar_one() == 1


def test_cli_db_check():
    r = subprocess.run([sys.executable, "cli.py", "db-check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Esquemas faltantes: ninguno" in r.stdout


def test_cli_phase_gates():
    r = subprocess.run([sys.executable, "cli.py", "demo"], capture_output=True, text=True)
    assert r.returncode == 2 and "Fase 5" in r.stdout
