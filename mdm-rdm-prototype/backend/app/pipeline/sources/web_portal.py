"""Portal web · Usuarios digitales. ID nativo: user_id. Nombres como texto libre → nameparser + división."""
from app.pipeline.common import (clean, code, consent, direct, e164, email_norm, new_std, parse_date,
                                 split_given, split_surnames, yn)
from app.pipeline.sources import read_csv

SOURCE_CD, ID_FIELD = "WEB_PORTAL", "user_id"


def extract(path) -> list[tuple[str, dict]]:
    return [(r[ID_FIELD], r) for r in read_csv(path)]


def standardize(p: dict) -> dict:
    s = new_std("PERSON")
    s["identifier_required"] = False   # el registro digital admite usuarios sin documento (caso B)
    first, middle = split_given(p.get("nombres")); sur1, sur2 = split_surnames(p.get("apellidos"))
    s["person"] = {"first_name": first, "middle_name": middle, "first_surname": sur1, "second_surname": sur2,
                   "birth_date": parse_date(p.get("fecha_nacimiento")), "death_date": None,
                   "gender": code("genero", (clean(p.get("genero")) or "").upper(), "CAT_GENDER")}
    if clean(p.get("num_doc")):
        s["identifiers"].append({"id_type": code("tipo_doc", p.get("tipo_doc"), "CAT_ID_TYPE"), "id_number": clean(p["num_doc"]),
                                 "verified": False, "verification": direct("NOT_VERIFIED", "CAT_VERIFICATION_SOURCE")})
    s["roles"].append({"role": direct("DIGITAL_USER", "CAT_PARTY_ROLE"), "sub_role": direct("DIGITAL_REGISTERED", "CAT_PARTY_SUB_ROLE"),
                       "business_unit": None, "valid_from": parse_date(p.get("updated_at"))})
    if clean(p.get("categoria")):
        s["segments"].append({"segment_type": "AFFILIATION", "segment": code("categoria", p["categoria"], "CAT_SEGMENT_TYPE")})
    if clean(p.get("segmento_comercial")):
        s["segments"].append({"segment_type": "COMMERCIAL", "segment": code("segmento_comercial", p["segmento_comercial"], "CAT_SEGMENT_TYPE")})
    if em := email_norm(p.get("email")):
        s["contacts"].append({"channel": "EMAIL", "value": em, "is_primary": True, "raw": p.get("email")})
    s["contacts"].append({"channel": "PHONE", "value": e164(p.get("celular")), "is_primary": True, "raw": p.get("celular")})
    if clean(p.get("ciudad")):
        s["addresses"].append({"line": None, "country": direct("COL", "CAT_COUNTRY"), "divipola": direct(clean(p["ciudad"]), "CAT_GEO_DIVIPOLA")})
    for ctype, field in (("DATA_PROCESSING", "acepta_datos"), ("COMMERCIAL", "acepta_comercial")):
        if (c := consent(ctype, yn(p.get(field)))) is not None:
            s["consents"].append(c)
    return s
