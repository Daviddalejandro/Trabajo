"""Scoring por atributo (SPEC §8.2–8.4) con evidencia por comparación: valor A, valor B,
algoritmo, similitud, puntos y ESTADO (AGREE / PARTIAL / DISAGREE / MISSING). El estado separa
"no viajó el dato" de "el dato contradice": un atributo ausente en cualquiera de los dos registros
no suma ni resta (Fellegi & Sunter, 1969); la política (policy.py) decide con la evidencia
normalizada sobre lo comparable. La evidencia alimenta la consola y la trazabilidad exigida a un
sistema algorítmico de decisión sobre datos personales (Ley 1581/2012; NIST AI RMF 1.0
MAP/MEASURE; ISO/IEC 42001:2023 cl. 6.1)."""
from __future__ import annotations

from rapidfuzz.distance import DamerauLevenshtein, JaroWinkler

from app.matching.rules import THRESHOLDS


def jw(a: str | None, b: str | None) -> float:
    if not a or not b:
        return 0.0
    return round(JaroWinkler.normalized_similarity(a, b), 4)


def _row(attr: str, a, b, algo: str, sim: float, points: float, weight: float, note: str = "", state: str | None = None, reason: str | None = None) -> dict:
    if state is None:
        empty = lambda v: v is None or v == "" or v == []  # noqa: E731
        state = "MISSING" if (empty(a) or empty(b)) else ("AGREE" if points >= weight else ("PARTIAL" if points > 0 else "DISAGREE"))
    return {"attribute": attr, "value_a": a, "value_b": b, "algorithm": algo, "similarity": sim, "points": points, "weight": weight, "note": note, "state": state, "reason": reason}


def _text(attr: str, va, vb, ka: str | None, kb: str | None, algo: str, weight: float, jw_min: float, extra_ok: bool = True, note: str = "",
          near_min: float | None = None, near_points: float = 0) -> dict:
    """Comparación textual: MISSING si falta en alguno; AGREE si JW ≥ mínimo (y condición extra); PARTIAL (`NEAR`) si JW
    queda entre `near_min` y el mínimo (error de digitación en el nombre); DISAGREE si no."""
    if not ka or not kb:
        return _row(attr, va, vb, algo, 0.0, 0, weight, note, "MISSING")
    s = jw(ka, kb)
    if s >= jw_min and extra_ok:
        return _row(attr, va, vb, algo, s, weight, weight, note, "AGREE")
    if near_points and ((near_min is not None and s >= near_min) or _typo(ka, kb)):
        # JW por debajo del mínimo pero cerca, o un solo carácter distinto (nombres cortos, donde JW castiga más)
        return _row(attr, va, vb, algo, s, near_points, weight, (note + " · " if note else "") + "parecido, posible error de digitación", "PARTIAL", "NEAR")
    return _row(attr, va, vb, algo, s, 0, weight, note, "DISAGREE")


def _typo(a: str | None, b: str | None) -> bool:
    """Un solo dígito o carácter transpuesto, sustituido, sobrante o faltante (Damerau-Levenshtein = 1)."""
    return bool(a and b and a != b and DamerauLevenshtein.distance(a, b) == 1)


def _sets(attr: str, sa: set, sb: set, weight: float, note: str = "", typo_points: float = 0) -> dict:
    """Conjuntos (correos, teléfonos, municipios): AGREE si comparten un valor; PARTIAL (`TYPO`) si algún par de valores
    está a un solo carácter (correo o celular mal digitado); DISAGREE si no."""
    if not sa or not sb:
        return _row(attr, sorted(sa)[:1], sorted(sb)[:1], "EXACT", 0.0, 0, weight, note, "MISSING")
    hit = sa & sb
    if hit:
        return _row(attr, sorted(hit)[:1], sorted(hit)[:1], "EXACT", 1.0, weight, weight, note, "AGREE")
    near = sorted((a, b) for a in sa for b in sb if _typo(a, b))
    if near and typo_points:
        a, b = near[0]
        return _row(attr, [a], [b], "EXACT_OR_TYPO", 0.9, typo_points, weight, (note + " · " if note else "") + "posible error de digitación: un carácter", "PARTIAL", "TYPO")
    return _row(attr, sorted(sa)[:1], sorted(sb)[:1], "EXACT", 0.0, 0, weight, note, "DISAGREE")


def score_person(fa: dict, fb: dict, rules: dict[str, dict]) -> tuple[float, list[dict]]:
    d: list[dict] = []
    w = {k: v["weight"] for k, v in rules.items()}
    p = {k: v["params"] for k, v in rules.items()}
    # Documento: exacto / mismo número con distinto tipo (parcial) / mismo tipo y números a un solo error de digitación
    # (parcial, `reason` TYPO: la política decide si veta) / mismo tipo con distinto número (contradice) /
    # tipos distintos o sin documento en alguno (no comparable)
    exact = fa["docs"] & fb["docs"]
    same_number = fa["doc_numbers"] & fb["doc_numbers"]
    common_type = {t for t, _ in fa["docs"]} & {t for t, _ in fb["docs"]}
    if exact:
        d.append(_row("document", sorted(exact)[0], sorted(exact)[0], "EXACT", 1.0, w["document"], w["document"], state="AGREE"))
    elif same_number:
        pts = float(p["document"].get("partial_other_type", 15))
        d.append(_row("document", sorted(fa["docs"])[:1], sorted(fb["docs"])[:1], "EXACT", 0.5, pts, w["document"], "mismo número, distinto tipo", "PARTIAL", "OTHER_TYPE"))
    elif common_type:
        typo = [(t, na, nb) for t, na in fa["docs"] for u, nb in fb["docs"] if t == u and DamerauLevenshtein.distance(na, nb) == 1]
        if typo:
            t, na, nb = sorted(typo)[0]
            pts = float(p["document"].get("partial_typo", 12))
            d.append(_row("document", (t, na), (t, nb), "EXACT_OR_TYPO", 0.9, pts, w["document"],
                          "posible error de digitación: un dígito transpuesto o sustituido", "PARTIAL", "TYPO"))
        else:
            d.append(_row("document", sorted(fa["docs"])[:1], sorted(fb["docs"])[:1], "EXACT", 0.0, 0, w["document"], "mismo tipo, número distinto", "DISAGREE"))
    else:
        d.append(_row("document", sorted(fa["docs"])[:1], sorted(fb["docs"])[:1], "EXACT", 0.0, 0, w["document"],
                      "sin documento comparable" if not (fa["docs"] and fb["docs"]) else "tipos de documento distintos: no comparables", "MISSING"))
    # Primer apellido: JW ≥ 0.92 + Soundex español
    d.append(_text("first_surname", fa["first_surname"], fb["first_surname"], fa["sur1_k"], fb["sur1_k"], "JARO_WINKLER+SOUNDEX_ES", w["first_surname"],
                   p["first_surname"].get("jw_min", 0.92), fa.get("sur1_soundex") == fb.get("sur1_soundex"), f"soundex {fa.get('sur1_soundex')}/{fb.get('sur1_soundex')}",
                   p["first_surname"].get("near_min"), float(p["first_surname"].get("partial_near", 0))))
    # Primer nombre
    d.append(_text("first_name", fa["first_name"], fb["first_name"], fa["first_name_k"], fb["first_name_k"], "JARO_WINKLER", w["first_name"], p["first_name"].get("jw_min", 0.90),
                   near_min=p["first_name"].get("near_min"), near_points=float(p["first_name"].get("partial_near", 0))))
    # Fecha de nacimiento: exacta / día y mes intercambiados (12/08 vs 08/12) / un dígito mal digitado / ±1 año / distinta
    ba, bb = fa.get("birth_date"), fb.get("birth_date")
    note, reason = "", None
    if ba and bb:
        swapped = ba.month <= 12 and ba.day <= 12 and bb == ba.replace(month=ba.day, day=ba.month)
        if ba == bb:
            pts, sim, st = w["birth_date"], 1.0, "AGREE"
        elif swapped:
            pts, sim, st, note, reason = float(p["birth_date"].get("partial_swap", 10)), 0.9, "PARTIAL", "día y mes intercambiados: posible error de digitación", "DM_SWAP"
        elif _typo(ba.isoformat(), bb.isoformat()):
            pts, sim, st, note, reason = float(p["birth_date"].get("partial_typo", 8)), 0.8, "PARTIAL", "un dígito distinto: posible error de digitación", "TYPO"
        elif abs((ba - bb).days) <= 366:
            pts, sim, st, note, reason = float(p["birth_date"].get("partial_1y", 8)), 0.5, "PARTIAL", "menos de un año de diferencia", "NEAR"
        else:
            pts, sim, st = 0, 0.0, "DISAGREE"
    else:
        pts, sim, st = 0, 0.0, "MISSING"
    d.append(_row("birth_date", str(ba) if ba else None, str(bb) if bb else None, "EXACT_OR_1Y_OR_TYPO", sim, pts, w["birth_date"], note, st, reason))
    # Segundo apellido
    d.append(_text("second_surname", fa["second_surname"], fb["second_surname"], fa["sur2_k"], fb["sur2_k"], "JARO_WINKLER", w["second_surname"], p["second_surname"].get("jw_min", 0.92),
                   near_min=p["second_surname"].get("near_min"), near_points=float(p["second_surname"].get("partial_near", 0))))
    # Email, teléfono (solo OWNER confirmado en ambos, ya filtrado en features), municipio
    d.append(_sets("email", fa["emails"], fb["emails"], w["email"], typo_points=float(p["email"].get("partial_typo", 0))))
    d.append(_sets("phone", fa["phones"], fb["phones"], w["phone"], "solo vínculos OWNER + CONFIRMED_BY_TITULAR", typo_points=float(p["phone"].get("partial_typo", 0))))
    d.append(_sets("municipality", fa["cities"], fb["cities"], w["municipality"]))
    return round(sum(r["points"] for r in d), 2), d


def score_org(fa: dict, fb: dict, rules: dict[str, dict]) -> tuple[float, list[dict]]:
    d: list[dict] = []
    w = {k: v["weight"] for k, v in rules.items()}
    p = {k: v["params"] for k, v in rules.items()}
    na, nb = fa.get("nit"), fb.get("nit")
    if not na or not nb:
        d.append(_row("nit", na, nb, "EXACT+CHECK_DIGIT", 0.0, 0, w["nit"], "sin NIT en alguno", "MISSING"))
    else:
        same, valid = na == nb, fa.get("nit_valid") and fb.get("nit_valid")
        d.append(_row("nit", na, nb, "EXACT+CHECK_DIGIT", 1.0 if same else 0.0, w["nit"] if same and valid else 0, w["nit"],
                      "" if valid else "NIT sin formato válido", "AGREE" if same and valid else ("PARTIAL" if same else "DISAGREE")))
    d.append(_text("legal_name", fa.get("legal_name"), fb.get("legal_name"), fa.get("legal_tokens"), fb.get("legal_tokens"), "JARO_WINKLER_TOKENS", w["legal_name"],
                   p["legal_name"].get("jw_min", 0.90), note="tokens sin S.A.S./LTDA/de Colombia"))
    d.append(_text("trade_name", fa.get("trade_name"), fb.get("trade_name"), fa.get("trade_k"), fb.get("trade_k"), "JARO_WINKLER", w["trade_name"], p["trade_name"].get("jw_min", 0.90)))
    ci = fa["cities"] & fb["cities"]; co = fa["countries"] & fb["countries"]
    va, vb = sorted(fa["cities"])[:1] or sorted(fa["countries"])[:1], sorted(fb["cities"])[:1] or sorted(fb["countries"])[:1]
    if not va or not vb:
        d.append(_row("municipality", va, vb, "EXACT", 0.0, 0, w["municipality"], state="MISSING"))
    else:
        pts = w["municipality"] if ci else (w["municipality"] / 2 if co else 0)
        d.append(_row("municipality", va, vb, "EXACT", 1.0 if ci else (0.5 if co else 0.0), pts, w["municipality"], state="AGREE" if ci else ("PARTIAL" if co else "DISAGREE")))
    ca, cb = fa.get("ciiu"), fb.get("ciiu")
    d.append(_row("ciiu", ca, cb, "EXACT", 1.0 if (ca and ca == cb) else 0.0, w["ciiu"] if (ca and ca == cb) else 0, w["ciiu"],
                  state="MISSING" if not (ca and cb) else ("AGREE" if ca == cb else "DISAGREE")))
    return round(sum(r["points"] for r in d), 2), d


def score_pair(fa: dict, fb: dict, rules: dict[str, dict[str, dict]]) -> tuple[float, list[dict]]:
    if fa["party_type"] != fb["party_type"]:
        raise ValueError("Nunca se compara PERSON con ORGANIZATION (regla dura 3.17)")
    return (score_person if fa["party_type"] == "PERSON" else score_org)(fa, fb, rules[fa["party_type"]])


def decide(score: float) -> str:
    """Umbrales v1 sobre puntos brutos (SPEC §8.4); la política v2 decide con `policy.decide_pair`."""
    if score >= THRESHOLDS["AUTO_MERGE"]:
        return "AUTO_MERGE"
    if score >= THRESHOLDS["PROBABLE"]:
        return "PROBABLE"
    if score >= THRESHOLDS["POSSIBLE"]:
        return "POSSIBLE"
    return "NO_MATCH"
