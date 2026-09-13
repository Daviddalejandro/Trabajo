"""Orquestador del pipeline (SPEC §7) con bitácora staging.LOAD_BATCH (§5.3). Replica los
DAGs de producción: <fuente>_full_load / <fuente>_delta_nightly."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.pipeline.common import sha256
from app.pipeline.dq import run_dq
from app.pipeline.homologate import Homologator
from app.pipeline.load import Loader
from app.pipeline.sources import SOURCES, get_adapter

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synth"


def _json(o):
    return o.isoformat() if isinstance(o, (date, datetime)) else str(o)


def set_context(session: Session, actor: str, batch_id: int | None = None, source_sk: int | None = None) -> None:
    session.execute(text("SELECT set_config('app.actor', :a, false)"), {"a": actor})
    session.execute(text("SELECT set_config('app.batch_id', :b, false)"), {"b": str(batch_id or "")})
    session.execute(text("SELECT set_config('app.source_system_sk', :s, false)"), {"s": str(source_sk or "")})


def open_batch(session: Session, source_sk: int, mode: str, actor: str) -> int:
    return session.execute(text("INSERT INTO staging.load_batch (source_system_cd, mode, actor) VALUES (:s, :m, :a) RETURNING batch_id"),
                           {"s": source_sk, "m": mode, "a": actor}).scalar_one()


def close_batch(session: Session, batch_id: int, status: str, counters: dict, detail: dict | None = None) -> None:
    sets = ", ".join(f"{k}=:{k}" for k in counters)
    session.execute(text(f"UPDATE staging.load_batch SET status=:st, finished_at=now(), detail=CAST(:d AS jsonb){', ' + sets if sets else ''} WHERE batch_id=:b"),
                    {"st": status, "d": json.dumps(detail or {}), "b": batch_id, **counters})


def write_issues(session: Session, issues: list[dict], hom: Homologator, source_sk: int, batch_id: int,
                 staging_ref: str, party_sk: int | None = None) -> None:
    for i in issues:
        session.execute(text(
            "INSERT INTO mdm.party_dq_issue (staging_ref, party_sk, dq_category_cd, field, detail, severity_cd, source_system_cd, batch_id) "
            "VALUES (:ref, :p, :cat, :f, CAST(:d AS jsonb), :sev, :s, :b)"),
            {"ref": i.get("staging_ref", staging_ref), "p": i.get("party_sk", party_sk), "cat": hom.sk("CAT_DQ_CATEGORY", i["category"]),
             "f": i["field"], "d": json.dumps(i["detail"], default=_json), "sev": hom.sk("CAT_SEVERITY", i["severity"]), "s": source_sk, "b": batch_id})


def run_ingest(session: Session, source: str, mode: str = "full", path: str | None = None, actor: str = "pipeline",
               match: bool = True) -> dict:
    adapter = get_adapter(source)
    system_cd, table = SOURCES[source]
    source_sk = session.execute(text("SELECT source_system_sk FROM rdm.source_system WHERE source_system_cd=:c"), {"c": system_cd}).scalar_one()
    batch_id = open_batch(session, source_sk, mode.upper(), actor)
    set_context(session, actor, batch_id, source_sk)
    session.commit()
    counters = dict(extracted=0, unchanged_hash=0, standardized=0, homologated=0, unknown_codes=0, dq_passed=0,
                    dq_quarantined=0, xref_hits=0, loaded=0, matched=0, auto_merged=0, probable=0)
    try:
        hom = Homologator(session, system_cd)
        loader = Loader(session, hom, source_sk, batch_id)
        new_parties: list[int] = []
        updated_goldens: list[int] = []
        # 1 · Extracción (CSV que replica la estructura nativa; en producción: conector real)
        rows = adapter.extract(path or DATA_DIR / f"{source}.csv")
        counters["extracted"] = len(rows)
        for external_id, payload in rows:
            h = sha256(payload)
            # 2 · Landing zone con idempotencia por (external_id, hash)
            known = session.execute(text("SELECT source_hash FROM mdm.xref_party_source WHERE source_system_cd=:s AND external_id=:e"),
                                    {"s": source_sk, "e": external_id}).scalar()
            status = "UNCHANGED" if known == h else "PENDING"
            raw_sk = session.execute(text(
                f"INSERT INTO staging.{table} (batch_id, external_id, payload, source_hash, raw_status) "
                f"VALUES (:b, :e, CAST(:p AS jsonb), :h, :st) RETURNING raw_sk"),
                {"b": batch_id, "e": external_id, "p": json.dumps(payload, ensure_ascii=False), "h": h, "st": status}).scalar_one()
            staging_ref = f"{table}:{raw_sk}"
            if status == "UNCHANGED":
                counters["unchanged_hash"] += 1
                continue
            # 3 · Estandarización (sin tocar códigos)
            std = adapter.standardize(payload)
            counters["standardized"] += 1
            # 4 · Homologación
            unresolved = hom.resolve_all(std)
            counters["homologated"] += 1
            counters["unknown_codes"] += len(unresolved)
            # 5 · Calidad
            issues, blocking = run_dq(std, hom, unresolved)
            session.execute(text(f"UPDATE staging.{table} SET standardized=CAST(:s AS jsonb), raw_status=:st, processed_at=now() WHERE raw_sk=:k"),
                            {"s": json.dumps(std, default=_json, ensure_ascii=False), "st": "DQ_QUARANTINE" if blocking else "DQ_PASSED", "k": raw_sk})
            if blocking:
                counters["dq_quarantined"] += 1
                write_issues(session, issues, hom, source_sk, batch_id, staging_ref)
                continue
            counters["dq_passed"] += 1
            # 6 · Crosswalk (XREF) y 7 · Carga
            party_sk, created = loader.load(external_id, std, h, staging_ref)
            counters["xref_hits"] += 0 if created else 1
            (new_parties if created else updated_goldens).append(party_sk)
            counters["loaded"] += 1
            write_issues(session, issues, hom, source_sk, batch_id, staging_ref, party_sk)
            session.execute(text(f"UPDATE staging.{table} SET raw_status='LOADED' WHERE raw_sk=:k"), {"k": raw_sk})
        loader.finish()
        loader.attach_targets()
        write_issues(session, loader.issues, hom, source_sk, batch_id, "batch")
        # XREF hit sobre un GOLDEN: re-survivorship (SPEC §9) con los datos actualizados de la fuente
        from app.survivorship.engine import apply_survivorship
        for psk in updated_goldens:
            if session.execute(text("SELECT g.value_code FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd WHERE p.party_sk=:p"), {"p": psk}).scalar() == "GOLDEN":
                apply_survivorship(session, psk)
        # 6b · Matching de los candidatos nuevos de este lote (regla dura §3.11: solo registros nuevos)
        if match and new_parties:
            from app.matching.engine import MatchingEngine
            set_context(session, actor, batch_id, None)
            m = MatchingEngine(session).run(actor, batch_id, new_parties)
            counters.update(matched=m["matched"], auto_merged=m["auto_merged"], probable=m["probable"])
            set_context(session, actor, batch_id, source_sk)
        close_batch(session, batch_id, "OK", counters, {"source": source, "path": str(path or DATA_DIR / f"{source}.csv")})
        session.commit()
    except Exception as exc:  # noqa: BLE001 — se registra en la bitácora y se propaga
        session.rollback()
        set_context(session, actor, batch_id, source_sk)
        close_batch(session, batch_id, "FAILED", counters, {"error": str(exc)[:500]})
        session.commit()
        raise
    finally:
        set_context(session, actor)
    return {"batch_id": batch_id, "source": system_cd, "mode": mode.upper(), **counters}
