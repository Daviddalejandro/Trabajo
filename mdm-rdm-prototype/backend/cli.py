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


@cli.command("synth-generate")
def synth_generate(seed: int = typer.Option(None, help="Seed fija (por defecto SYNTH_SEED)")) -> None:
    """F2 · Genera los CSV sintéticos de las 5 fuentes y el manifiesto de casos (§13)."""
    from app.synth.generator import generate

    m = generate(seed or settings.synth_seed)
    for k, v in m["counts"].items():
        typer.echo(f"{k:12s} {v} registros")
    typer.echo(f"Casos plantados: {', '.join(sorted(m['cases']))}")


@cli.command("ingest")
def ingest(source: str = typer.Option(..., help="sf_ec | ecc_sd | ecc_mm | crm_bp | web_portal | all"),
           mode: str = typer.Option("full", help="full | delta"),
           file: str = typer.Option(None, help="CSV alterno (por defecto data/synth/<fuente>.csv)"),
           actor: str = typer.Option("pipeline")) -> None:
    """F2 · Pipeline de 7 etapas para una fuente (replica <fuente>_full_load / _delta_nightly)."""
    from app.core.db import SessionLocal
    from app.pipeline.run import run_ingest
    from app.pipeline.sources import SOURCES

    sources = list(SOURCES) if source == "all" else [source]
    with SessionLocal() as session:
        for src in sources:
            r = run_ingest(session, src, mode, file, actor)
            typer.echo(" · ".join(f"{k}={v}" for k, v in r.items()))


@cli.command("rehomologate")
def rehomologate_cmd(catalog: str = typer.Option(None, help="Catálogo (p. ej. CAT_PARTY_ROLE); vacío = todos"),
                     actor: str = typer.Option("rdm-admin")) -> None:
    """F2 · Reprocesa los campos en UNKNOWN tras un cambio en SOURCE_VALUE_MAPPING (§7.2)."""
    from app.core.db import SessionLocal
    from app.pipeline.rehomologate import rehomologate

    with SessionLocal() as session:
        typer.echo(rehomologate(session, catalog, actor))


@cli.command("reset-mdm")
def reset_mdm(yes: bool = typer.Option(False, "--yes", help="Confirma el vaciado de staging y mdm (el RDM se conserva)")) -> None:
    """Vacía staging.* y mdm.* (datos sintéticos) conservando el RDM. Base de `make demo` desde cero."""
    if not yes:
        typer.echo("Agrega --yes para confirmar. Solo vacía datos sintéticos de staging y mdm; el RDM no se toca.")
        raise typer.Exit(code=2)
    from sqlalchemy import text
    from app.core.db import engine

    with engine.begin() as conn:
        tables = conn.execute(text("SELECT table_schema||'.'||table_name FROM information_schema.tables "
                                   "WHERE table_schema IN ('staging','mdm') AND table_type='BASE TABLE'")).scalars().all()
        conn.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))
    typer.echo(f"Vaciadas {len(tables)} tablas de staging y mdm.")


@cli.command("rebuild")
def rebuild(yes: bool = typer.Option(False, "--yes", help="Confirma: elimina los esquemas rdm, mdm y staging y los reconstruye"),
            actor: str = typer.Option("rebuild")) -> None:
    """Reconstruye desde cero: drop de esquemas → migrate → rdm-seed → synth-generate → ingest all (con matching).
    Deja la consola con los casos B y K pendientes (base de las pruebas e2e y de `make demo`)."""
    if not yes:
        typer.echo("Agrega --yes para confirmar. Elimina y reconstruye rdm, mdm y staging con datos sintéticos.")
        raise typer.Exit(code=2)
    from sqlalchemy import text
    from app.core.db import engine

    with engine.begin() as conn:
        for sch in ("staging", "mdm", "rdm"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {sch} CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version"))
    engine.dispose()
    rc = subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"])
    if rc:
        raise typer.Exit(code=rc)
    for args in (["rdm-seed", "--actor", actor], ["synth-generate"], ["ingest", "--source", "all", "--actor", actor]):
        rc = subprocess.call([sys.executable, "cli.py", *args])
        if rc:
            raise typer.Exit(code=rc)
    typer.echo("Reconstrucción completa: RDM sembrado, sintéticos generados, 5 fuentes ingeridas y matching aplicado.")


@cli.command("match")
def match(actor: str = typer.Option("matching")) -> None:
    """F3 · Blocking, scoring, umbrales, merge automático (snapshot) y survivorship sobre los CANDIDATE."""
    from app.core.db import SessionLocal
    from app.matching.engine import run_matching

    with SessionLocal() as session:
        r = run_matching(session, actor)
    typer.echo(" · ".join(f"{k}={v}" for k, v in r.items()))


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
