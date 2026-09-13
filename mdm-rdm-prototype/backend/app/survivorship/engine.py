"""Aplica las reglas de survivorship (SPEC §9) sobre un party a partir de los registros
estandarizados de todas sus fuentes (XREF → staging.standardized).

- nombre, documento, fecha de nacimiento: SOURCE_PRIORITY SF_EC > SAP_CRM > SAP_ECC_SD > SAP_ECC_MM > CREDITO_CORE > WEB_PORTAL
- fallecimiento / estado DECEASED: MOST_RECENT (cualquier fuente que lo informe prevalece)
- email / teléfono (vínculo primario): MOST_RECENT por captured_at del vínculo
- resto (género, CIIU, tipo de organización): MOST_COMPLETE
- roles y vínculos de servicio: UNION (no compiten); segmentos: fuente autoritativa por tipo (ya en carga)
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.matching.rules import SOURCE_PRIORITY
from app.pipeline.common import normalized_key
from app.pipeline.sources import SOURCES

TABLE_BY_SOURCE = {v[0]: v[1] for v in SOURCES.values()}
PERSON_PRIORITY_FIELDS = ["first_name", "middle_name", "first_surname", "second_surname", "birth_date"]
ORG_PRIORITY_FIELDS = ["legal_name", "trade_name"]


def _sk(session: Session, catalog: str, code: str) -> int:
    return session.execute(text("SELECT value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code=:c AND value_code=:v"), {"c": catalog, "v": code}).scalar_one()


def source_records(session: Session, party_sk: int) -> list[tuple[str, int, dict]]:
    """[(source_cd, source_sk, standardized)] ordenados por prioridad de fuente."""
    xrefs = session.execute(text("""
        SELECT s.source_system_cd, s.source_system_sk, x.external_id FROM mdm.xref_party_source x
        JOIN rdm.source_system s ON s.source_system_sk = x.source_system_cd WHERE x.party_sk = :p"""), {"p": party_sk}).all()
    out = []
    for cd, ssk, ext in xrefs:
        table = TABLE_BY_SOURCE.get(cd)
        if not table:
            continue
        std = session.execute(text(f"SELECT standardized FROM staging.{table} WHERE external_id=:e AND standardized IS NOT NULL "
                                   "ORDER BY raw_sk DESC LIMIT 1"), {"e": ext}).scalar()
        if std:
            out.append((cd, ssk, std))
    rank = {s: i for i, s in enumerate(SOURCE_PRIORITY)}
    out.sort(key=lambda r: rank.get(r[0], 99))
    return out


def _record(session: Session, party_sk: int, field: str, strategy: str, source_sk: int | None, value) -> None:
    session.execute(text("""
        INSERT INTO mdm.party_survivorship (party_sk, field_name, strategy_cd, winning_source_cd, winning_value)
        VALUES (:p, :f, :s, :src, :v)
        ON CONFLICT (party_sk, field_name) DO UPDATE SET strategy_cd=EXCLUDED.strategy_cd, winning_source_cd=EXCLUDED.winning_source_cd,
            winning_value=EXCLUDED.winning_value, decided_at=now()"""),
        {"p": party_sk, "f": field, "s": _sk(session, "CAT_SURVIVORSHIP_STRATEGY", strategy), "src": source_sk,
         "v": None if value is None else (json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value))})


def apply_survivorship(session: Session, party_sk: int) -> dict:
    ptype = session.execute(text("SELECT v.value_code FROM mdm.party p JOIN rdm.reference_value v ON v.value_sk=p.party_type_cd WHERE p.party_sk=:p"),
                            {"p": party_sk}).scalar()
    if ptype is None:
        raise LookupError(f"Party {party_sk} no existe")
    recs = source_records(session, party_sk)
    winners: dict[str, dict] = {}
    if not recs:
        return {"party_sk": party_sk, "fields": 0}

    def priority(fields: list[str], section: str) -> dict[str, tuple]:
        chosen = {}
        for f in fields:
            for cd, ssk, std in recs:
                v = (std.get(section) or {}).get(f)
                if v not in (None, ""):
                    chosen[f] = (cd, ssk, v, "SOURCE_PRIORITY"); break
            if f not in chosen:
                # MOST_COMPLETE (fallback): el valor no nulo más largo
                cands = [(cd, ssk, (std.get(section) or {}).get(f)) for cd, ssk, std in recs if (std.get(section) or {}).get(f)]
                if cands:
                    cd, ssk, v = max(cands, key=lambda c: len(str(c[2])))
                    chosen[f] = (cd, ssk, v, "MOST_COMPLETE")
                else:
                    chosen[f] = (None, None, None, "MOST_COMPLETE")
        return chosen

    def most_complete_code(section: str, key: str) -> tuple:
        for cd, ssk, std in recs:
            e = (std.get(section) or {}).get(key)
            if e and e.get("sk", 0) > 0:
                return cd, ssk, e["sk"], e.get("code")
        return None, None, 0, None

    if ptype == "PERSON":
        ch = priority(PERSON_PRIORITY_FIELDS, "person")
        gcd, gssk, gsk, gcode = most_complete_code("person", "gender")
        full = " ".join(x for x in [ch["first_name"][2], ch["middle_name"][2], ch["first_surname"][2], ch["second_surname"][2]] if x)
        session.execute(text("""UPDATE mdm.party_person SET first_name=:fn, middle_name=:mn, first_surname=:s1, second_surname=:s2,
            birth_date=CAST(:bd AS DATE), gender_cd=CASE WHEN :g > 0 THEN :g ELSE gender_cd END, full_name_normalized=:full WHERE party_sk=:p"""),
            {"fn": ch["first_name"][2], "mn": ch["middle_name"][2], "s1": ch["first_surname"][2], "s2": ch["second_surname"][2],
             "bd": ch["birth_date"][2], "g": gsk, "full": normalized_key(full), "p": party_sk})
        for f, (cd, ssk, v, strat) in ch.items():
            _record(session, party_sk, f, strat, ssk, v); winners[f] = {"source": cd, "value": v, "strategy": strat}
        _record(session, party_sk, "gender", "MOST_COMPLETE", gssk, gcode); winners["gender"] = {"source": gcd, "value": gcode, "strategy": "MOST_COMPLETE"}
        # documento: la fuente de mayor prioridad que traiga documento
        for cd, ssk, std in recs:
            ids = std.get("identifiers") or []
            if ids:
                doc = f"{ids[0]['id_type'].get('code')}:{ids[0]['id_number']}"
                _record(session, party_sk, "document", "SOURCE_PRIORITY", ssk, doc); winners["document"] = {"source": cd, "value": doc, "strategy": "SOURCE_PRIORITY"}
                break
    else:
        ch = priority(ORG_PRIORITY_FIELDS, "org")
        ccd, cssk, csk, ccode = most_complete_code("org", "ciiu")
        ocd, ossk, osk, ocode = most_complete_code("org", "org_type")
        session.execute(text("""UPDATE mdm.party_org SET legal_name=:ln, trade_name=:tn, legal_name_normalized=:lnn,
            ciiu_cd=CASE WHEN :c > 0 THEN :c ELSE ciiu_cd END, org_type_cd=CASE WHEN :o > 0 THEN :o ELSE org_type_cd END WHERE party_sk=:p"""),
            {"ln": ch["legal_name"][2], "tn": ch["trade_name"][2], "lnn": normalized_key(ch["legal_name"][2]), "c": csk, "o": osk, "p": party_sk})
        for f, (cd, ssk, v, strat) in ch.items():
            _record(session, party_sk, f, strat, ssk, v); winners[f] = {"source": cd, "value": v, "strategy": strat}
        _record(session, party_sk, "ciiu", "MOST_COMPLETE", cssk, ccode); _record(session, party_sk, "org_type", "MOST_COMPLETE", ossk, ocode)
        for cd, ssk, std in recs:
            ids = std.get("identifiers") or []
            if ids:
                _record(session, party_sk, "document", "SOURCE_PRIORITY", ssk, f"NIT:{ids[0]['id_number']}"); break

    # Estado DECEASED: MOST_RECENT — cualquier fuente que lo informe prevalece (Ley 1581/2012 art. 4 lit. d)
    deceased_src = next(((cd, ssk) for cd, ssk, std in recs if (std.get("status") or {}).get("code") == "DECEASED"), None)
    if deceased_src:
        session.execute(text("UPDATE mdm.party SET party_status_cd=:d WHERE party_sk=:p"), {"d": _sk(session, "CAT_PARTY_STATUS", "DECEASED"), "p": party_sk})
        _record(session, party_sk, "party_status", "MOST_RECENT", deceased_src[1], "DECEASED"); winners["party_status"] = {"source": deceased_src[0], "value": "DECEASED"}

    # Email y teléfono: MOST_RECENT por captured_at del vínculo → is_primary
    for channel in ("EMAIL", "PHONE"):
        rows = session.execute(text("""
            SELECT l.party_contact_sk, c.contact_value, l.source_system_cd, s.source_system_cd AS cd FROM mdm.party_contact_point l
            JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd
            JOIN rdm.reference_value ur ON ur.value_sk=l.usage_role_cd JOIN rdm.source_system s ON s.source_system_sk=l.source_system_cd
            WHERE l.party_sk=:p AND ch.value_code=:ch AND l.valid_to IS NULL AND ur.value_code IN ('OWNER','SHARED')
            ORDER BY l.captured_at DESC, l.party_contact_sk DESC"""), {"p": party_sk, "ch": channel}).all()
        if rows:
            win = rows[0]
            session.execute(text("UPDATE mdm.party_contact_point SET is_primary = (party_contact_sk = :w) WHERE party_contact_sk = ANY(:all)"),
                            {"w": win[0], "all": [r[0] for r in rows]})
            _record(session, party_sk, channel.lower(), "MOST_RECENT", win[2], win[1]); winners[channel.lower()] = {"source": win[3], "value": win[1], "strategy": "MOST_RECENT"}
    _record(session, party_sk, "roles", "MOST_COMPLETE", None, "UNION: todos los roles con su linaje")
    session.execute(text("UPDATE mdm.party SET golden_version = golden_version + 1, updated_at = now() WHERE party_sk=:p"), {"p": party_sk})
    _completeness(session, party_sk, ptype)
    return {"party_sk": party_sk, "fields": len(winners), "winners": winners}


def _completeness(session: Session, party_sk: int, ptype: str) -> None:
    if ptype == "PERSON":
        checks = session.execute(text("""
            SELECT pp.first_name IS NOT NULL, pp.first_surname IS NOT NULL, pp.birth_date IS NOT NULL, pp.gender_cd > 0,
                   EXISTS (SELECT 1 FROM mdm.party_identifier i WHERE i.party_sk=pp.party_sk),
                   EXISTS (SELECT 1 FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd WHERE l.party_sk=pp.party_sk AND ch.value_code='EMAIL'),
                   EXISTS (SELECT 1 FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd WHERE l.party_sk=pp.party_sk AND ch.value_code='PHONE'),
                   EXISTS (SELECT 1 FROM mdm.party_address a WHERE a.party_sk=pp.party_sk AND a.divipola_cd > 0)
            FROM mdm.party_person pp WHERE pp.party_sk=:p"""), {"p": party_sk}).one()
    else:
        checks = session.execute(text("""
            SELECT po.legal_name IS NOT NULL, EXISTS (SELECT 1 FROM mdm.party_identifier i WHERE i.party_sk=po.party_sk), po.ciiu_cd > 0, po.org_type_cd > 0,
                   EXISTS (SELECT 1 FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd WHERE l.party_sk=po.party_sk AND ch.value_code='EMAIL'),
                   EXISTS (SELECT 1 FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd WHERE l.party_sk=po.party_sk AND ch.value_code='PHONE'),
                   EXISTS (SELECT 1 FROM mdm.party_address a WHERE a.party_sk=po.party_sk AND a.divipola_cd > 0)
            FROM mdm.party_org po WHERE po.party_sk=:p"""), {"p": party_sk}).one()
    score = round(100 * sum(1 for c in checks if c) / len(checks), 2)
    session.execute(text("UPDATE mdm.party SET completeness_score=:s WHERE party_sk=:p"), {"s": score, "p": party_sk})
