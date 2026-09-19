"""Rasgos comparables por party (SPEC §8): documentos, nombres normalizados, fecha, contactos
confirmados del titular, municipio; para organizaciones NIT, razón social tokenizada, CIIU."""
from __future__ import annotations

import re
import unicodedata

import jellyfish
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.pipeline.common import nit_check_digit, normalized_key

ORG_STOPWORDS = {"SAS", "S.A.S", "SA", "S.A", "LTDA", "LIMITADA", "DE", "COLOMBIA", "FUNDACION", "CIA", "Y", "E", "&", "EU", "ESAL"}


def fold(s: str | None) -> str:
    v = unicodedata.normalize("NFD", (s or "").upper())
    return "".join(ch for ch in v if unicodedata.category(ch) != "Mn")


def soundex_es(surname: str | None) -> str | None:
    """Soundex tolerante al español: neutraliza LL/Y, Z/S, V/B, C suave, QU/K, GE-GI/J y H muda."""
    v = fold(surname)
    if not v:
        return None
    v = re.sub(r"[^A-Z]", "", v)
    reps = [("LL", "Y"), ("QU", "K"), ("GE", "JE"), ("GI", "JI"), ("CE", "SE"), ("CI", "SI"), ("Z", "S"), ("V", "B"), ("H", ""), ("Ñ", "N")]
    for a, b in reps:
        v = v.replace(a, b)
    return jellyfish.soundex(v) if v else None


def org_tokens(name: str | None) -> str | None:
    # "S.A.S." / "S. A." → "SAS" / "SA" para que caigan en ORG_STOPWORDS y no se abran en letras sueltas
    if name:
        name = re.sub(r"\b((?:[A-Za-z]\.\s?){2,})", lambda m: m.group(1).replace(".", "").replace(" ", "") + " ", name)
    key = normalized_key(name)
    if not key:
        return None
    toks = [t for t in key.split() if t not in ORG_STOPWORDS]
    return " ".join(sorted(toks)) or None


def load_features(session: Session, party_sks: list[int] | None = None, any_status: bool = False) -> dict[int, dict]:
    """Carga en memoria los rasgos de los parties GOLDEN y CANDIDATE (o de la lista dada; `any_status` incluye MERGED)."""
    filt = "AND p.party_sk = ANY(:sks)" if party_sks is not None else ""
    status = "" if any_status else "AND g.value_code IN ('GOLDEN','CANDIDATE')"
    params = {"sks": party_sks} if party_sks is not None else {}
    rows = session.execute(text(f"""
        SELECT p.party_sk, t.value_code AS party_type, g.value_code AS golden_status,
               pp.first_name, pp.middle_name, pp.first_surname, pp.second_surname, pp.birth_date, pp.full_name_normalized,
               po.legal_name, po.trade_name, po.legal_name_normalized, ci.value_code AS ciiu,
               (SELECT array_agg(v.value_code || ':' || i.id_number) FROM mdm.party_identifier i JOIN rdm.reference_value v ON v.value_sk=i.id_type_cd WHERE i.party_sk=p.party_sk) AS ids,
               (SELECT array_agg(DISTINCT c.contact_value) FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk
                  JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd WHERE l.party_sk=p.party_sk AND ch.value_code='EMAIL' AND l.valid_to IS NULL) AS emails,
               (SELECT array_agg(DISTINCT c.contact_value) FROM mdm.party_contact_point l JOIN mdm.contact_point c ON c.contact_point_sk=l.contact_point_sk
                  JOIN rdm.reference_value ch ON ch.value_sk=c.channel_cd JOIN rdm.reference_value ur ON ur.value_sk=l.usage_role_cd
                  JOIN rdm.reference_value cf ON cf.value_sk=l.confirmation_status_cd
                  WHERE l.party_sk=p.party_sk AND ch.value_code='PHONE' AND ur.value_code='OWNER' AND cf.value_code='CONFIRMED_BY_TITULAR' AND l.valid_to IS NULL) AS phones,
               (SELECT array_agg(DISTINCT dv.value_code) FROM mdm.party_address a JOIN rdm.reference_value dv ON dv.value_sk=a.divipola_cd WHERE a.party_sk=p.party_sk AND a.divipola_cd > 0) AS cities,
               (SELECT array_agg(DISTINCT co.value_code) FROM mdm.party_address a JOIN rdm.reference_value co ON co.value_sk=a.country_cd WHERE a.party_sk=p.party_sk AND a.country_cd > 0) AS countries
        FROM mdm.party p JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd
        LEFT JOIN mdm.party_person pp ON pp.party_sk=p.party_sk LEFT JOIN mdm.party_org po ON po.party_sk=p.party_sk
        LEFT JOIN rdm.reference_value ci ON ci.value_sk=po.ciiu_cd
        WHERE 1=1 {status} {filt}"""), params).mappings().all()
    feats: dict[int, dict] = {}
    for r in rows:
        f = dict(r)
        ids = [x.split(":", 1) for x in (r["ids"] or [])]
        f["docs"] = {(t, n) for t, n in ids}
        f["doc_numbers"] = {n for _, n in ids}
        f["nit"] = next((n for t, n in ids if t == "NIT"), None)
        f["emails"] = set(r["emails"] or []); f["phones"] = set(r["phones"] or [])
        f["cities"] = set(r["cities"] or []); f["countries"] = set(r["countries"] or [])
        f["first_name_k"] = fold(r["first_name"]); f["sur1_k"] = fold(r["first_surname"]); f["sur2_k"] = fold(r["second_surname"])
        f["sur1_soundex"] = soundex_es(r["first_surname"])
        f["legal_tokens"] = org_tokens(r["legal_name"]); f["trade_k"] = normalized_key(r["trade_name"])
        f["nit_valid"] = bool(f["nit"] and f["nit"].isdigit() and len(f["nit"]) == 9)
        feats[r["party_sk"]] = f
    return feats


def features_from_input(payload: dict) -> dict:
    """Rasgos de un registro no persistido (match-preview, §8.6)."""
    ptype = payload.get("party_type", "PERSON").upper()
    ids = {(d.get("id_type", "CC").upper(), str(d.get("id_number"))) for d in payload.get("identifiers", []) if d.get("id_number")}
    f = {"party_sk": 0, "party_type": ptype, "golden_status": "PREVIEW",
         "first_name": payload.get("first_name"), "first_surname": payload.get("first_surname"), "second_surname": payload.get("second_surname"),
         "birth_date": payload.get("birth_date"), "legal_name": payload.get("legal_name"), "trade_name": payload.get("trade_name"),
         "ciiu": payload.get("ciiu"), "docs": ids, "doc_numbers": {n for _, n in ids}, "nit": next((n for t, n in ids if t == "NIT"), None),
         "emails": {e.lower() for e in payload.get("emails", []) if e}, "phones": set(payload.get("phones", [])),
         "cities": {c for c in [payload.get("divipola")] if c}, "countries": {c for c in [payload.get("country")] if c}}
    f["first_name_k"] = fold(f["first_name"]); f["sur1_k"] = fold(f["first_surname"]); f["sur2_k"] = fold(f["second_surname"])
    f["sur1_soundex"] = soundex_es(f["first_surname"]); f["legal_tokens"] = org_tokens(f["legal_name"]); f["trade_k"] = normalized_key(f["trade_name"])
    f["nit_valid"] = bool(f["nit"] and f["nit"].isdigit() and len(f["nit"]) == 9)
    if isinstance(f["birth_date"], str):
        from datetime import date
        try:
            f["birth_date"] = date.fromisoformat(f["birth_date"])
        except ValueError:
            f["birth_date"] = None
    return f


def blocking_keys(f: dict) -> list[tuple[str, str]]:
    """(estrategia, clave) por party. Nunca cruza tipos (regla dura §3.17): la clave lleva el tipo."""
    t = f["party_type"]
    keys: list[tuple[str, str]] = []
    if t == "PERSON":
        keys += [("DOC_HASH", f"P|{n}") for n in f["doc_numbers"]]
        keys += [("EMAIL_HASH", f"P|{e}") for e in f["emails"]]
        keys += [("PHONE_HASH", f"P|{p}") for p in f["phones"]]
        if f.get("sur1_soundex"):
            keys.append(("SURNAME_SOUNDEX", f"P|{f['sur1_soundex']}"))
    else:
        if f.get("nit"):
            keys.append(("NIT_HASH", f"O|{f['nit']}"))
        if f.get("legal_tokens"):
            keys.append(("LEGAL_NAME_TOKENS", f"O|{f['legal_tokens']}"))
        keys += [("EMAIL_HASH", f"O|{e}") for e in f["emails"]]
    return keys


def nit_ok(nit: str | None, dv: str | None = None) -> bool:
    return bool(nit and nit.isdigit() and (dv is None or str(nit_check_digit(nit)) == dv))
