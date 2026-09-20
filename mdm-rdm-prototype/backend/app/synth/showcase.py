"""Casos de vitrina S1–S5 (datos sintéticos, seed fija) para demostrar en la Consola de Stewardship y en la
Vista 360 lo que el escenario demo A–U no cubre: errores de digitación muy parecidos, homónimos, un golden
con varios tipos y números de identificación y matching de organizaciones. Se cargan como corridas DELTA
sobre la base actual (`cli.py showcase`), así que también sirven para mostrar cómo entra información nueva
de forma incremental: hash de idempotencia → estandarización → homologación → DQ → XREF → carga → buckets
de bloqueo → matching → elegibilidad (SPEC §7, §8.1)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from app.synth.generator import DATA_DIR, Universe

SHOWCASE_DIR = DATA_DIR / "showcase"
SEED = 20260920

CASES = {
    "S1": "Cédula con un dígito transpuesto (SF_EC vs SAP CRM): mismo correo y celular → PROBABLE por G4 con veto de digitación; el steward decide",
    "S2": "Sin documento en el portal; nombre con una letra cambiada (Jaro-Winkler lo absorbe), fecha con día y mes intercambiados y correo con un carácter de más → PROBABLE por umbral de evidencia, ningún grupo satisfecho",
    "S3": "Homónimo: mismos nombres y apellidos, cédula distinta, nacido con menos de un año de diferencia → POSSIBLE; el documento contradice",
    "S4": "Una persona con tres identificadores (CC en SF_EC, pasaporte en CRM, TI antigua en el portal) → fusiona sola por G4; golden con 3 documentos",
    "S5": "Organización: mismo NIT, razón social con error de digitación en MM → fusiona sola por O1 (NIT + razón social)",
    "S6": "Todos los campos con un solo error de digitación (cédula, nombre, apellidos, fecha, correo, celular) que aún cae en un bucket → se compara y queda en la zona gris; los nombres los absorbe Jaro-Winkler, el resto queda parcial",
    "S7": "Todos los campos con un error de digitación y además el primer apellido cambia de Soundex (B/V) → no comparte ningún bucket: nunca se compara (límite del bloqueo exacto, visible en el explorador de buckets)",
    "S8": "Cobertura parcial: el portal solo trae nombres, apellidos y correo (sin documento, fecha ni celular) → cobertura 52 %, por debajo del mínimo: decide sobre puntos brutos → POSSIBLE",
    "S9": "El grupo G1 manda: mismo documento y primer apellido, pero nombre distinto y fecha cinco años aparte → fusiona sola (G1 documental); queda en el historial de merges para discutir si G1 debe exigir más",
    "S10": "Organizaciones homónimas: misma razón social y ciudad con NIT distinto → PROBABLE por O2 (razón social + municipio) con veto del NIT: cola de organizaciones",
}


def _typo_word(word: str, keep_soundex: bool) -> str:
    """Un solo error de digitación en un nombre: sustitución de una letra. Con `keep_soundex` elige una que conserve
    el Soundex español (s↔z, vocal por vocal); sin él, cambia la primera consonante (b↔v, c↔s) para romperlo."""
    from app.matching.features import soundex_es

    base = soundex_es(word)
    letters = list(word)
    candidates = []
    vowels = "aeiou"
    for i, ch in enumerate(letters):
        low = ch.lower()
        # conservar el Soundex: una vocal por otra (el Soundex español solo codifica consonantes); romperlo: la primera consonante
        reps = [v for v in vowels if v != low] if keep_soundex else ["v", "b", "s", "c", "m", "n"]
        if keep_soundex and (i == 0 or low not in vowels):
            continue
        if not keep_soundex and low in vowels:
            continue
        for rep in reps:
            w = "".join(letters[:i] + [rep.upper() if ch.isupper() else rep] + letters[i + 1:])
            if (soundex_es(w) == base) == keep_soundex:
                candidates.append(w)
        if candidates:
            break
    return candidates[0] if candidates else word + ("s" if keep_soundex else "")


def _swap(doc: str, i: int = 5) -> str:
    d = list(doc); d[i], d[i + 1] = d[i + 1], d[i]
    return "".join(d)


def build(seed: int = SEED) -> tuple[Universe, dict]:
    u = Universe(seed, n_persons=0, n_orgs=0)
    u._next = {"pernr": 90000, "kunnr": 900000, "lifnr": 900000, "partner": 9000000, "user": 900000}   # no colisionar con el demo (XREF)
    P = [u._person(9000 + i) for i in range(8)]
    O = [u._org(900)]
    m: dict = {"seed": seed, "cases": {}}
    # S1 · cédula con dígito transpuesto, todo lo demás igual
    p = P[0]; p.doc_type = "CC"
    m["cases"]["S1"] = {"doc": p.doc, "doc_typo": _swap(p.doc), "email": p.email, "phone": p.phone, "name": f"{p.first} {p.sur1} {p.sur2}",
                        "sf_ec": u.emit_sf_ec(p)}
    p.doc = m["cases"]["S1"]["doc_typo"]
    m["cases"]["S1"]["crm"] = u.emit_crm_person(p, categoria="A")
    # S2 · portal sin documento con nombre, fecha y correo mal digitados
    p = P[1]; p.doc_type = "CC"
    day = min(p.birth.day, 12)
    p.birth = p.birth.replace(day=day if day != p.birth.month else (day % 12) + 1)   # día ≤ 12 y ≠ mes: el portal los intercambia
    m["cases"]["S2"] = {"doc": p.doc, "email": p.email, "phone": p.phone, "name": f"{p.first} {p.sur1} {p.sur2}", "ecc_sd": u.emit_sd_person(p)}
    first_typo = p.first[:-1] + ("a" if p.first[-1] != "a" else "o")
    email_typo = p.email.replace("@", "s@", 1)
    b = p.birth
    p2 = type(p)(**{**p.__dict__, "birth": b.replace(month=b.day, day=b.month)}); p2.sources = {}
    m["cases"]["S2"].update(name_typo=f"{first_typo} {p.sur1} {p.sur2}", email_typo=email_typo, birth=b.isoformat(), birth_typo=p2.birth.isoformat(),
                            portal=u.emit_portal(p2, doc=None, nombres=first_typo, email=email_typo, acepta_comercial="false"))
    # S3 · homónimo con otra cédula y fecha cercana
    p = P[2]; p.doc_type = "CC"
    m["cases"]["S3"] = {"doc_a": p.doc, "name": f"{p.first} {p.sur1} {p.sur2}", "birth_a": p.birth.isoformat(), "sf_ec": u.emit_sf_ec(p)}
    q = type(p)(**{**p.__dict__, "doc": u._doc(), "birth": p.birth.replace(year=p.birth.year + 1), "email": f"otro.{p.email}", "phone": f"31{p.phone[2:]}"})
    q.sources = {}
    m["cases"]["S3"].update(doc_b=q.doc, birth_b=q.birth.isoformat(), crm=u.emit_crm_person(q, categoria="B"))
    # S4 · tres identificadores de tipos distintos para la misma persona
    p = P[3]; p.doc_type = "CC"
    pas, ti = f"AB{u.rng.randint(100000, 999999)}", u._doc()
    m["cases"]["S4"] = {"cc": p.doc, "passport": pas, "ti": ti, "email": p.email, "phone": p.phone, "name": f"{p.first} {p.sur1} {p.sur2}", "sf_ec": u.emit_sf_ec(p)}
    q = type(p)(**{**p.__dict__, "doc": pas, "doc_type": "PAS"}); q.sources = {}
    m["cases"]["S4"]["crm"] = u.emit_crm_person(q, categoria="A", telefonos=[f"{p.phone}:TIT:OWN:TIT"])
    r = type(p)(**{**p.__dict__, "doc": ti, "doc_type": "TI"}); r.sources = {}
    m["cases"]["S4"]["portal"] = u.emit_portal(r, categoria="A")
    # S5 · organización con NIT igual y razón social mal digitada en MM
    o = O[0]
    legal_typo = o.legal.replace("a", "e", 1) if "a" in o.legal else o.legal + "s"
    m["cases"]["S5"] = {"nit": f"{o.nit}-{o.dv}", "legal": o.legal, "legal_typo": legal_typo, "ecc_sd": u.emit_sd_org(o), "ecc_mm": u.emit_mm_org(o, legal=legal_typo)}
    # S6 y S7 · todos los campos con un error de digitación en el registro B (CRM)
    for code, keep, idx in (("S6", True, 4), ("S7", False, 5)):
        p = P[idx]; p.doc_type = "CC"
        day = min(p.birth.day, 12)
        p.birth = p.birth.replace(day=day if day != p.birth.month else (day % 12) + 1)
        b = p.birth
        q = type(p)(**{**p.__dict__, "doc": _swap(p.doc), "first": _typo_word(p.first, True), "sur1": _typo_word(p.sur1, keep), "sur2": _typo_word(p.sur2, True),
                       "birth": b.replace(month=b.day, day=b.month), "email": p.email.replace("@", "s@", 1), "phone": _swap(p.phone, 6)})
        q.sources = {}
        m["cases"][code] = {"a": {"doc": p.doc, "name": f"{p.first} {p.sur1} {p.sur2}", "birth": b.isoformat(), "email": p.email, "phone": p.phone},
                            "b": {"doc": q.doc, "name": f"{q.first} {q.sur1} {q.sur2}", "birth": q.birth.isoformat(), "email": q.email, "phone": q.phone},
                            "sf_ec": u.emit_sf_ec(p), "crm": u.emit_crm_person(q, categoria="A", telefonos=[f"{q.phone}:TIT:OWN:TIT"])}
    # S8 · cobertura parcial: el portal solo trae nombres, apellidos y correo
    p = P[6]; p.doc_type = "CC"
    m["cases"]["S8"] = {"doc": p.doc, "name": f"{p.first} {p.sur1} {p.sur2}", "email": p.email, "sf_ec": u.emit_sf_ec(p), "portal": u.emit_portal(p, doc=None)}
    u.rows["web_portal"][-1].update({"fecha_nacimiento": "", "celular": "", "genero": ""})
    # S9 · G1 manda: documento y primer apellido iguales, nombre y fecha distintos, contactos distintos
    p = P[7]; p.doc_type = "CC"
    q = type(p)(**{**p.__dict__, "first": "Carlos" if p.first != "Carlos" else "Andrés", "middle": "", "birth": p.birth.replace(year=p.birth.year - 5),
                   "email": f"otro.{p.email}", "phone": f"31{p.phone[2:]}"}); q.sources = {}
    m["cases"]["S9"] = {"doc": p.doc, "a": f"{p.first} {p.sur1} {p.sur2} · {p.birth.isoformat()}", "b": f"{q.first} {q.sur1} {q.sur2} · {q.birth.isoformat()}",
                        "sf_ec": u.emit_sf_ec(p), "crm": u.emit_crm_person(q, categoria="B")}
    # S10 · organizaciones homónimas con NIT distinto
    from app.pipeline.common import nit_check_digit
    o = u._org(901); o2 = type(o)(**o.__dict__); o2.sources = {}
    o2.nit = f"8{u.rng.randint(10_000_000, 99_999_999)}"; o2.dv = nit_check_digit(o2.nit)
    m["cases"]["S10"] = {"legal": o.legal, "nit_a": f"{o.nit}-{o.dv}", "nit_b": f"{o2.nit}-{o2.dv}", "ecc_sd": u.emit_sd_org(o), "ecc_mm": u.emit_mm_org(o2)}
    m["counts"] = {k: len(v) for k, v in u.rows.items()}
    return u, m


def write(seed: int = SEED, out_dir: Path = SHOWCASE_DIR) -> dict:
    u, m = build(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    for source, rows in u.rows.items():
        path = out_dir / f"{source}.csv"
        if rows:
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        elif path.exists():
            path.unlink()
    (out_dir / "manifest.json").write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    return m


ORDER = ["sf_ec", "ecc_sd", "ecc_mm", "crm_bp", "web_portal"]


def load(session, actor: str = "showcase", seed: int = SEED) -> tuple[dict, list[dict]]:
    """Genera los CSV y los ingiere como corridas DELTA (una por fuente) sobre la base actual."""
    from app.pipeline.run import run_ingest

    m = write(seed)
    batches = [run_ingest(session, s, "delta", str(SHOWCASE_DIR / f"{s}.csv"), actor) for s in ORDER if (SHOWCASE_DIR / f"{s}.csv").exists()]
    return m, batches


def report(session, m: dict) -> list[dict]:
    """Verifica cada caso contra la base y devuelve filas (caso, ok, evidencia) para la consola y las pruebas."""
    from sqlalchemy import text

    def party_of(system: str, ext: str) -> int | None:
        return session.execute(text("SELECT x.party_sk FROM mdm.xref_party_source x JOIN rdm.source_system s ON s.source_system_sk=x.source_system_cd "
                                    "WHERE s.source_system_cd=:s AND x.external_id=:e"), {"s": system, "e": ext}).scalar()

    def pair(a: int, b: int):
        return session.execute(text("""SELECT m.match_sk, d.value_code AS decision, m.match_status, m.total_score, m.decision_basis, m.score_detail
            FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd
            WHERE m.party_a_sk=LEAST(:a,:b) AND m.party_b_sk=GREATEST(:a,:b) ORDER BY m.match_sk DESC"""), {"a": a, "b": b}).mappings().first()

    def doc_row(pr) -> dict:
        return next((r for r in pr["score_detail"] if r["attribute"] == "document"), {})

    out = []
    c = m["cases"]
    # S1
    a, b = party_of("SF_EC", c["S1"]["sf_ec"]), party_of("SAP_CRM", c["S1"]["crm"])
    pr = pair(a, b) if a and b else None
    ok = bool(pr) and pr["decision"] == "PROBABLE" and pr["match_status"] == "PENDING" and doc_row(pr).get("reason") == "TYPO" and "veto_review" in pr["decision_basis"]["decided_by"]
    out.append({"case": "S1", "ok": ok, "evidence": f"par #{pr['match_sk']} · {pr['decision']} · evidencia {pr['total_score']} · {pr['decision_basis']['decided_by']} · documento {doc_row(pr).get('state')} ({doc_row(pr).get('note')}) · {c['S1']['doc']} vs {c['S1']['doc_typo']}" if pr else "sin par", "party": a, "match": pr["match_sk"] if pr else None})
    # S2
    a, b = party_of("SAP_ECC_SD", c["S2"]["ecc_sd"]), party_of("WEB_PORTAL", c["S2"]["portal"])
    pr = pair(a, b) if a and b else None
    reasons = {r["attribute"]: r.get("reason") for r in (pr["score_detail"] if pr else [])}
    ok = bool(pr) and pr["decision"] == "PROBABLE" and pr["decision_basis"]["decided_by"].startswith("threshold") and not pr["decision_basis"]["satisfied_groups"] and reasons.get("email") == "TYPO" and reasons.get("birth_date") == "DM_SWAP"
    out.append({"case": "S2", "ok": ok, "evidence": f"par #{pr['match_sk']} · {pr['decision']} · evidencia {pr['total_score']} sobre cobertura {pr['decision_basis']['coverage']} · {pr['decision_basis']['decided_by']} · motivos {[(k, v) for k, v in reasons.items() if v]}" if pr else "sin par", "party": a, "match": pr["match_sk"] if pr else None})
    # S3
    a, b = party_of("SF_EC", c["S3"]["sf_ec"]), party_of("SAP_CRM", c["S3"]["crm"])
    pr = pair(a, b) if a and b else None
    ok = bool(pr) and pr["decision"] == "POSSIBLE" and doc_row(pr).get("state") == "DISAGREE"
    out.append({"case": "S3", "ok": ok, "evidence": f"par #{pr['match_sk']} · {pr['decision']} · evidencia {pr['total_score']} · documento {doc_row(pr).get('state')} ({c['S3']['doc_a']} vs {c['S3']['doc_b']}) · {pr['decision_basis']['decided_by']}" if pr else "sin par", "party": a, "match": pr["match_sk"] if pr else None})
    # S4
    sks = {party_of("SF_EC", c["S4"]["sf_ec"]), party_of("SAP_CRM", c["S4"]["crm"]), party_of("WEB_PORTAL", c["S4"]["portal"])}
    ids = session.execute(text("SELECT t.value_code, i.id_number FROM mdm.party_identifier i JOIN rdm.reference_value t ON t.value_sk=i.id_type_cd WHERE i.party_sk=:p ORDER BY 1"), {"p": next(iter(sks))}).all() if len(sks) == 1 else []
    golden = session.execute(text("SELECT g.value_code FROM mdm.party p JOIN rdm.reference_value g ON g.value_sk=p.golden_status_cd WHERE p.party_sk=:p"), {"p": next(iter(sks))}).scalar() if len(sks) == 1 else None
    ok = len(sks) == 1 and golden == "GOLDEN" and {t for t, _ in ids} == {"CC", "PAS", "TI"}
    out.append({"case": "S4", "ok": ok, "evidence": f"party {next(iter(sks))} {golden} con {len(ids)} identificadores {ids}" if len(sks) == 1 else f"sin fusionar: {sks}", "party": next(iter(sks)) if len(sks) == 1 else None, "match": None})
    # S5
    sks = {party_of("SAP_ECC_SD", c["S5"]["ecc_sd"]), party_of("SAP_ECC_MM", c["S5"]["ecc_mm"])}
    ok = len(sks) == 1
    out.append({"case": "S5", "ok": ok, "evidence": f"party {next(iter(sks))} · NIT {c['S5']['nit']} · «{c['S5']['legal']}» vs «{c['S5']['legal_typo']}» fusionados" if ok else f"sin fusionar: {sks}", "party": next(iter(sks)) if ok else None, "match": None})
    # S6: comparado (comparte el bucket Soundex del apellido) y en zona gris con estados parciales
    a, b = party_of("SF_EC", c["S6"]["sf_ec"]), party_of("SAP_CRM", c["S6"]["crm"])
    pr = pair(a, b) if a and b else None
    states = {r["attribute"]: (r["state"], r.get("reason")) for r in (pr["score_detail"] if pr else [])}
    ok = bool(pr) and pr["decision"] in ("PROBABLE", "POSSIBLE") and pr["match_status"] == "PENDING" and states.get("document") == ("PARTIAL", "TYPO") and states.get("birth_date") == ("PARTIAL", "DM_SWAP") and states.get("email") == ("PARTIAL", "TYPO") and states.get("phone") == ("PARTIAL", "TYPO")
    out.append({"case": "S6", "ok": ok, "evidence": (f"par #{pr['match_sk']} · {pr['decision']} · evidencia {pr['total_score']} · {pr['decision_basis']['decided_by']} · estados " + ", ".join(f"{k}={v[0]}{'/' + v[1] if v[1] else ''}" for k, v in states.items()) + f" · A «{c['S6']['a']['name']}» {c['S6']['a']['doc']} / B «{c['S6']['b']['name']}» {c['S6']['b']['doc']}") if pr else "sin par", "party": a, "match": pr["match_sk"] if pr else None})
    # S7: dos parties distintos, sin par (ningún bucket en común)
    a, b = party_of("SF_EC", c["S7"]["sf_ec"]), party_of("SAP_CRM", c["S7"]["crm"])
    pr = pair(a, b) if a and b else None
    ok = bool(a and b) and a != b and pr is None
    out.append({"case": "S7", "ok": ok, "evidence": f"parties {a} y {b} sin par: A «{c['S7']['a']['name']}» / B «{c['S7']['b']['name']}» no comparten documento, correo, celular ni Soundex del apellido → nunca se compararon" if ok else f"inesperado: par {pr['match_sk'] if pr else None}", "party": a, "match": None})
    # S8: cobertura por debajo del mínimo → vía de puntos brutos
    a, b = party_of("SF_EC", c["S8"]["sf_ec"]), party_of("WEB_PORTAL", c["S8"]["portal"])
    pr = pair(a, b) if a and b else None
    ok = bool(pr) and pr["decision"] == "POSSIBLE" and pr["decision_basis"]["decided_by"] == "threshold:raw_points" and pr["decision_basis"]["coverage"] < 60
    out.append({"case": "S8", "ok": ok, "evidence": f"par #{pr['match_sk']} · {pr['decision']} · evidencia {pr['total_score']} sobre cobertura {pr['decision_basis']['coverage']} · {pr['decision_basis']['decided_by']} · sin dato: {[r['attribute'] for r in pr['score_detail'] if r['state'] == 'MISSING']}" if pr else "sin par", "party": a, "match": pr["match_sk"] if pr else None})
    # S9: fusión automática por G1 pese a nombre y fecha distintos
    sks = {party_of("SF_EC", c["S9"]["sf_ec"]), party_of("SAP_CRM", c["S9"]["crm"])}
    just = session.execute(text("SELECT justification FROM mdm.party_merge_history WHERE surviving_party_sk=:p AND unmerged_at IS NULL ORDER BY merge_sk DESC LIMIT 1"), {"p": next(iter(sks))}).scalar() if len(sks) == 1 else None
    ok = len(sks) == 1 and bool(just) and "group:G1" in just
    out.append({"case": "S9", "ok": ok, "evidence": f"party {next(iter(sks))} · A «{c['S9']['a']}» + B «{c['S9']['b']}» fusionados: {just}" if ok else f"sin fusionar por G1: {sks} · {just}", "party": next(iter(sks)) if len(sks) == 1 else None, "match": None})
    # S10: organizaciones homónimas → PROBABLE por O2 con veto del NIT
    a, b = party_of("SAP_ECC_SD", c["S10"]["ecc_sd"]), party_of("SAP_ECC_MM", c["S10"]["ecc_mm"])
    pr = pair(a, b) if a and b else None
    ok = bool(pr) and pr["decision"] == "PROBABLE" and "O2" in pr["decision_basis"]["decided_by"] and "nit" in (pr["decision_basis"].get("vetoed_by") or [])
    out.append({"case": "S10", "ok": ok, "evidence": f"par #{pr['match_sk']} · {pr['decision']} · evidencia {pr['total_score']} · {pr['decision_basis']['decided_by']} · «{c['S10']['legal']}» NIT {c['S10']['nit_a']} vs {c['S10']['nit_b']}" if pr else f"sin par ({a}, {b})", "party": a, "match": pr["match_sk"] if pr else None})
    return out
