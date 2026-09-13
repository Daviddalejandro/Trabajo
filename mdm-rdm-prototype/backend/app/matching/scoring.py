"""Scoring por atributo (SPEC §8.2–8.4) con evidencia por comparación: valor A, valor B,
algoritmo, similitud y puntos. La evidencia alimenta la consola y la trazabilidad exigida a un
sistema algorítmico de decisión sobre datos personales (Ley 1581/2012; NIST AI RMF 1.0
MAP/MEASURE; ISO/IEC 42001:2023 cl. 6.1)."""
from __future__ import annotations

from rapidfuzz.distance import JaroWinkler

from app.matching.rules import THRESHOLDS


def jw(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return round(JaroWinkler.normalized_similarity(a, b), 4)


def _row(attr: str, a, b, algo: str, sim: float, points: float, weight: float, note: str = "") -> dict:
    return {"attribute": attr, "value_a": a, "value_b": b, "algorithm": algo, "similarity": sim, "points": points, "weight": weight, "note": note}


def score_person(fa: dict, fb: dict, rules: dict[str, dict]) -> tuple[float, list[dict]]:
    d: list[dict] = []
    w = {k: v["weight"] for k, v in rules.items()}
    p = {k: v["params"] for k, v in rules.items()}
    # Documento
    exact = fa["docs"] & fb["docs"]
    same_number = fa["doc_numbers"] & fb["doc_numbers"]
    if exact:
        d.append(_row("document", sorted(exact)[0], sorted(exact)[0], "EXACT", 1.0, w["document"], w["document"]))
    elif same_number:
        pts = float(p["document"].get("partial_other_type", 15))
        d.append(_row("document", sorted(fa["docs"])[:1], sorted(fb["docs"])[:1], "EXACT", 0.5, pts, w["document"], "mismo número, distinto tipo"))
    else:
        d.append(_row("document", sorted(fa["docs"])[:1], sorted(fb["docs"])[:1], "EXACT", 0.0, 0, w["document"]))
    # Primer apellido: JW ≥ 0.92 + Soundex español
    s = jw(fa["sur1_k"], fb["sur1_k"])
    ok = s >= p["first_surname"].get("jw_min", 0.92) and fa.get("sur1_soundex") == fb.get("sur1_soundex")
    d.append(_row("first_surname", fa["first_surname"], fb["first_surname"], "JARO_WINKLER+SOUNDEX_ES", s, w["first_surname"] if ok else 0, w["first_surname"],
                  f"soundex {fa.get('sur1_soundex')}/{fb.get('sur1_soundex')}"))
    # Primer nombre
    s = jw(fa["first_name_k"], fb["first_name_k"])
    d.append(_row("first_name", fa["first_name"], fb["first_name"], "JARO_WINKLER", s, w["first_name"] if s >= p["first_name"].get("jw_min", 0.90) else 0, w["first_name"]))
    # Fecha de nacimiento: exacta / ±1 año parcial
    ba, bb = fa.get("birth_date"), fb.get("birth_date")
    if ba and bb:
        if ba == bb:
            pts, sim = w["birth_date"], 1.0
        elif abs((ba - bb).days) <= 366:
            pts, sim = float(p["birth_date"].get("partial_1y", 8)), 0.5
        else:
            pts, sim = 0, 0.0
    else:
        pts, sim = 0, 0.0
    d.append(_row("birth_date", str(ba) if ba else None, str(bb) if bb else None, "EXACT_OR_1Y", sim, pts, w["birth_date"]))
    # Segundo apellido
    s = jw(fa["sur2_k"], fb["sur2_k"])
    d.append(_row("second_surname", fa["second_surname"], fb["second_surname"], "JARO_WINKLER", s, w["second_surname"] if s >= p["second_surname"].get("jw_min", 0.92) else 0, w["second_surname"]))
    # Email, teléfono (solo OWNER confirmado en ambos, ya filtrado en features), municipio
    em = fa["emails"] & fb["emails"]
    d.append(_row("email", sorted(fa["emails"])[:1], sorted(fb["emails"])[:1], "EXACT", 1.0 if em else 0.0, w["email"] if em else 0, w["email"]))
    ph = fa["phones"] & fb["phones"]
    d.append(_row("phone", sorted(fa["phones"])[:1], sorted(fb["phones"])[:1], "EXACT", 1.0 if ph else 0.0, w["phone"] if ph else 0, w["phone"],
                  "solo vínculos OWNER + CONFIRMED_BY_TITULAR"))
    ci = fa["cities"] & fb["cities"]
    d.append(_row("municipality", sorted(fa["cities"])[:1], sorted(fb["cities"])[:1], "EXACT", 1.0 if ci else 0.0, w["municipality"] if ci else 0, w["municipality"]))
    return round(sum(r["points"] for r in d), 2), d


def score_org(fa: dict, fb: dict, rules: dict[str, dict]) -> tuple[float, list[dict]]:
    d: list[dict] = []
    w = {k: v["weight"] for k, v in rules.items()}
    p = {k: v["params"] for k, v in rules.items()}
    same = fa.get("nit") and fa["nit"] == fb.get("nit")
    valid = fa.get("nit_valid") and fb.get("nit_valid")
    d.append(_row("nit", fa.get("nit"), fb.get("nit"), "EXACT+CHECK_DIGIT", 1.0 if same else 0.0, w["nit"] if same and valid else 0, w["nit"],
                  "" if valid else "NIT sin formato válido"))
    s = jw(fa.get("legal_tokens"), fb.get("legal_tokens"))
    d.append(_row("legal_name", fa.get("legal_name"), fb.get("legal_name"), "JARO_WINKLER_TOKENS", s, w["legal_name"] if s >= p["legal_name"].get("jw_min", 0.90) else 0, w["legal_name"],
                  "tokens sin S.A.S./LTDA/de Colombia"))
    s = jw(fa.get("trade_k"), fb.get("trade_k"))
    d.append(_row("trade_name", fa.get("trade_name"), fb.get("trade_name"), "JARO_WINKLER", s, w["trade_name"] if s >= p["trade_name"].get("jw_min", 0.90) else 0, w["trade_name"]))
    ci = fa["cities"] & fb["cities"]; co = fa["countries"] & fb["countries"]
    pts = w["municipality"] if ci else (w["municipality"] / 2 if co else 0)
    d.append(_row("municipality", sorted(fa["cities"])[:1] or sorted(fa["countries"])[:1], sorted(fb["cities"])[:1] or sorted(fb["countries"])[:1], "EXACT", 1.0 if ci else (0.5 if co else 0.0), pts, w["municipality"]))
    same_ciiu = fa.get("ciiu") and fa["ciiu"] == fb.get("ciiu")
    d.append(_row("ciiu", fa.get("ciiu"), fb.get("ciiu"), "EXACT", 1.0 if same_ciiu else 0.0, w["ciiu"] if same_ciiu else 0, w["ciiu"]))
    return round(sum(r["points"] for r in d), 2), d


def score_pair(fa: dict, fb: dict, rules: dict[str, dict[str, dict]]) -> tuple[float, list[dict]]:
    if fa["party_type"] != fb["party_type"]:
        raise ValueError("Nunca se compara PERSON con ORGANIZATION (regla dura 3.17)")
    return (score_person if fa["party_type"] == "PERSON" else score_org)(fa, fb, rules[fa["party_type"]])


def decide(score: float) -> str:
    if score >= THRESHOLDS["AUTO_MERGE"]:
        return "AUTO_MERGE"
    if score >= THRESHOLDS["PROBABLE"]:
        return "PROBABLE"
    if score >= THRESHOLDS["POSSIBLE"]:
        return "POSSIBLE"
    return "NO_MATCH"
