"""CLI operativa (SPEC §7). Los comandos replican los nombres lógicos de los DAGs de
producción. Todas las fases están habilitadas (F0–F5)."""
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


@cli.command("validation-generate")
def validation_generate(seed: int = typer.Option(20260914, help="Seed fija del conjunto de validación")) -> None:
    """Validación · Genera data/validation/: extracto SAP ECC (KNA1) y sistema de crédito (CREDITO_CORE) con casos plantados V1–V28."""
    from app.synth.validation import generate

    m = generate(seed)
    for k, v in m["counts"].items():
        typer.echo(f"{k:24s} {v} registros")
    typer.echo(f"Casos plantados: {', '.join(sorted(m['cases']))}")


@cli.command("validation-load")
def validation_load(actor: str = typer.Option("validation", help="Actor de los lotes")) -> None:
    """Validación · Deja en la consola el conjunto SAP ECC + sistema de crédito: validation-generate → reset-mdm (el RDM se
    conserva) → ingest ecc_sd y credito_core (con matching) → rne-sync con el RNE de validación → resumen de la zona gris."""
    steps = (["validation-generate"], ["reset-mdm", "--yes"],
             ["ingest", "--source", "ecc_sd", "--file", "data/validation/ecc_kna1_validacion.csv", "--actor", actor],
             ["ingest", "--source", "credito_core", "--file", "data/validation/credito_core.csv", "--actor", actor],
             ["rne-sync", "--file", "data/validation/rne_validacion.csv", "--actor", actor])
    for args in steps:
        rc = subprocess.call([sys.executable, "cli.py", *args])
        if rc:
            raise typer.Exit(code=rc)
    from sqlalchemy import text
    from app.core.db import engine

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT d.value_code, m.match_status, count(*) FROM mdm.party_match m "
                                 "JOIN rdm.reference_value d ON d.value_sk=m.decision_cd GROUP BY 1,2 ORDER BY 1,2")).all()
    typer.echo("")
    typer.echo(f"{'Decisión':12s}{'Estado':10s}Pares")
    for dec, st, n in rows:
        typer.echo(f"{dec:12s}{st:10s}{n}")
    typer.echo("\nConjunto de validación cargado: zona gris (PROBABLE/POSSIBLE pendientes) en http://localhost:5173/#/stewardship")


@cli.command("ingest")
def ingest(source: str = typer.Option(..., help="sf_ec | ecc_sd | ecc_mm | crm_bp | web_portal | all"),
           mode: str = typer.Option("full", help="full | delta"),
           file: str = typer.Option(None, help="CSV alterno (por defecto data/synth/<fuente>.csv)"),
           actor: str = typer.Option("pipeline")) -> None:
    """F2 · Pipeline de 7 etapas para una fuente (replica <fuente>_full_load / _delta_nightly)."""
    from app.core.db import SessionLocal
    from app.pipeline.run import DATA_DIR, run_ingest
    from app.pipeline.sources import SOURCES

    # `all` = las fuentes del escenario demo (las que tienen CSV por defecto en data/synth/); el conjunto de
    # validación (CREDITO_CORE) se ingiere explícitamente con --file
    sources = [s for s in SOURCES if (DATA_DIR / f"{s}.csv").exists()] if source == "all" else [source]
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
def rne_sync(file: str = typer.Option("data/synth/rne_sample.csv", help="CSV de números excluidos (simulado)"),
             actor: str = typer.Option("rne-sync")) -> None:
    """F5 · Marca rne_excluded en CONTACT_POINT y recalcula elegibilidad (solo afecta la finalidad COMMERCIAL, Ley 2300/2023 art. 5)."""
    from app.compliance.service import rne_sync as _rne
    from app.core.db import SessionLocal

    with SessionLocal() as session:
        r = _rne(session, file, actor)
        session.commit()
    typer.echo(" · ".join(f"{k}={v}" for k, v in r.items()))


@cli.command("purge")
def purge(dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="El prototipo solo simula (SPEC §10.5)"),
          actor: str = typer.Option("retention")) -> None:
    """F5 · Lista los parties con purge_after vencido, sin LEGAL_HOLD y sin vínculo activo; audita PURGE_SIMULATED. Nunca borra."""
    from app.compliance.service import purge_candidates
    from app.core.db import SessionLocal

    if not dry_run:
        typer.echo("El prototipo no borra datos: se ejecuta como simulación (SPEC §10.5).")
    with SessionLocal() as session:
        r = purge_candidates(session, actor, dry_run=True)
        session.commit()
    typer.echo(f"Candidatos a purga: {r['count']}")
    for it in r["items"]:
        typer.echo(f"  party {it['party_sk']} · {it['display_name']} · {it['rule']} · purge_after {it['purge_after']} · {it['legal_basis']}")


@cli.command("eligibility-recompute")
def eligibility_recompute(party: int = typer.Option(None, help="party_sk; vacío = todos")) -> None:
    """F5 · Recalcula la caché de elegibilidad (12 precedencias, SPEC §10.3)."""
    from app.compliance.eligibility import recompute_all, recompute_party
    from app.core.db import SessionLocal

    with SessionLocal() as session:
        n = 1 if party else recompute_all(session)
        if party:
            recompute_party(session, party)
        session.commit()
    typer.echo(f"Elegibilidad recalculada para {n} parties.")


@cli.command("demo")
def demo(actor: str = typer.Option("demo")) -> None:
    """F5 · make demo end-to-end: rebuild (migrar → sembrar → sintéticos → ingerir con matching) → rne-sync → caso Q (ARCO vencida)
    → deja la consola con B y K pendientes e imprime el estado de los 21 casos."""
    from app.demo import plant_and_report

    rc = subprocess.call([sys.executable, "cli.py", "rebuild", "--yes", "--actor", actor])
    if rc:
        raise typer.Exit(code=rc)
    rc = subprocess.call([sys.executable, "cli.py", "rne-sync", "--actor", actor])
    if rc:
        raise typer.Exit(code=rc)
    from app.core.db import SessionLocal

    with SessionLocal() as session:
        report = plant_and_report(session, actor)
        session.commit()
    typer.echo("")
    typer.echo(f"{'Caso':6s}{'Estado':10s}Evidencia")
    for row in report:
        typer.echo(f"{row['case']:6s}{('OK' if row['ok'] else 'REVISAR'):10s}{row['evidence']}")
    if not all(r["ok"] for r in report):
        raise typer.Exit(code=1)
    typer.echo("\nDemo lista: consola con los casos B y K pendientes en http://localhost:5173/#/stewardship")


@cli.command("showcase")
def showcase(actor: str = typer.Option("showcase")) -> None:
    """Vitrina · Carga en modo DELTA los casos S1–S5 (digitación muy parecida, homónimo, golden con tres tipos de documento,
    organización con NIT igual) sobre la base actual y verifica cada uno. Se ejecuta después de `demo` o `validation-load`."""
    from app.core.db import SessionLocal
    from app.synth.showcase import CASES, load, report

    with SessionLocal() as session:
        m, batches = load(session, actor)
        for b in batches:
            typer.echo(f"lote {b['batch_id']} {b['source']} {b['mode']} · extraídos {b['extracted']} · cargados {b['loaded']} · comparados {b['matched']} · auto {b['auto_merged']} · probables {b['probable']}")
        rows = report(session, m)
        session.commit()
    typer.echo("")
    typer.echo(f"{'Caso':6s}{'Estado':10s}Evidencia")
    for r in rows:
        typer.echo(f"{r['case']:6s}{('OK' if r['ok'] else 'REVISAR'):10s}{CASES[r['case']]}")
        typer.echo(f"{'':16s}{r['evidence']}")
    if not all(r["ok"] for r in rows):
        raise typer.Exit(code=1)
    typer.echo("\nVitrina lista: S1–S3 en la Consola de Stewardship, S4 y S5 en la Vista 360 (party_sk arriba).")


@cli.command("export-drive")
def export_drive(out: str = typer.Option("../docs/drive", help="Carpeta de salida (SPEC §17)")) -> None:
    """F5 · Genera en docs/drive/ los entregables por carpeta de Drive: diccionario, catálogos, matching, cumplimiento, evidencia, demo y comité."""
    from app.core.db import SessionLocal
    from app.export.drive import export_all

    with SessionLocal() as session:
        files = export_all(session, out)
    for f in files:
        typer.echo(f)
    typer.echo(f"{len(files)} archivos generados en {out}")


if __name__ == "__main__":
    cli()
