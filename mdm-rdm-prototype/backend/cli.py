"""CLI operativa (SPEC §7). Los comandos replican los nombres lógicos de los DAGs de
producción. En F0 solo existen `db-check` y `migrate`; el resto se habilita por fase."""
import subprocess
import sys

import typer

from app.core.config import settings
from app.core.db import db_ping, existing_schemas

cli = typer.Typer(help="MDM/RDM Prototipo · Party — comandos operativos", no_args_is_help=True)


@cli.command("db-check")
def db_check() -> None:
    """Verifica conexión y esquemas (rdm, mdm, staging)."""
    ok = db_ping()
    schemas = existing_schemas()
    faltan = sorted({"rdm", "mdm", "staging"} - schemas)
    typer.echo(f"Base de datos: {'OK' if ok else 'ERROR'} · {settings.database_url}")
    typer.echo(f"Esquemas faltantes: {faltan or 'ninguno'}")
    raise typer.Exit(code=0 if ok and not faltan else 1)


@cli.command("migrate")
def migrate() -> None:
    """Aplica las migraciones Alembic hasta head."""
    raise typer.Exit(code=subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"]))


def _pending(fase: str) -> None:
    typer.echo(f"Comando disponible a partir de la {fase} (SPEC §14).")
    raise typer.Exit(code=2)


@cli.command("rdm-seed")
def rdm_seed(actor: str = typer.Option("rdm-seed", help="Actor registrado en RDM_AUDIT_LOG")) -> None:
    """F1 · Siembra dominios, catálogos, valores, EAV, sistemas fuente y homologaciones (idempotente)."""
    from app.core.db import SessionLocal
    from app.rdm.seed import seed_rdm

    with SessionLocal() as session:
        rep = seed_rdm(session, actor=actor)
        session.commit()
    for k, v in rep.as_dict().items():
        typer.echo(f"{k:15s} creados: {v}")
    typer.echo("RDM sembrado. Prueba canónica: GET /api/v1/rdm/homologate?system=SAP_CRM&field=GESCHL&value=1 → M")


@cli.command("ingest")
def ingest(source: str = typer.Option(..., help="sf_ec | ecc_sd | ecc_mm | crm_bp | web_portal"),
           mode: str = typer.Option("full", help="full | delta")) -> None:
    """F2 · Pipeline de 7 etapas para una fuente."""
    _pending("Fase 2")


@cli.command("match")
def match() -> None:
    """F3 · Blocking, scoring, umbrales, merge automático y survivorship."""
    _pending("Fase 3")


@cli.command("rne-sync")
def rne_sync(file: str = typer.Option(..., help="CSV de números excluidos (simulado)")) -> None:
    """F5 · Marca rne_excluded en CONTACT_POINT (solo finalidad COMMERCIAL)."""
    _pending("Fase 5")


@cli.command("demo")
def demo() -> None:
    """F5 · make demo end-to-end."""
    _pending("Fase 5")


@cli.command("export-drive")
def export_drive() -> None:
    """F5 · Genera en docs/drive/ los entregables de la fase (SPEC §17)."""
    _pending("Fase 5")


if __name__ == "__main__":
    cli()
