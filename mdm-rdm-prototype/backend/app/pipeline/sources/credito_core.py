"""Sistema de crédito · core de cartera (CREDITO_CORE). ID nativo: ID_CLIENTE.
Extracto plano del maestro de clientes de cartera: identificación, obligaciones (una fila por
obligación, 1NF), teléfonos alternos aportados por la gestión de cobranza (numero:tipo:estado),
calificación de riesgo, autorizaciones (tratamiento, comercial, centrales) y codeudor.

Regla de negocio de la fuente (SPEC §7 etapa 7 y §10.3): los teléfonos alternos nacen con finalidad
COLLECTIONS habilitada y BENEFITS/COMMERCIAL denegadas; los de referencia son medios de un tercero."""
from app.pipeline.common import (address_norm, clean, code, consent, direct, e164, email_norm, new_std, parse_date,
                                 split_given, split_multi, split_nit, split_surnames)
from app.pipeline.sources import read_csv

SOURCE_CD, ID_FIELD = "CREDITO_CORE", "ID_CLIENTE"


def sn(v: str | None) -> bool | None:
    """Banderas S/N del core de cartera (el helper genérico `yn` no reconoce la S castellana)."""
    x = (v or "").strip().upper()
    return True if x in {"S", "SI", "SÍ", "Y", "1"} else False if x in {"N", "NO", "0"} else None


COLLECTION_PURPOSES = [{"purpose": "COLLECTIONS", "allowed": True}, {"purpose": "BENEFITS", "allowed": False}, {"purpose": "COMMERCIAL", "allowed": False}]


def extract(path) -> list[tuple[str, dict]]:
    return [(r[ID_FIELD], r) for r in read_csv(path)]


def standardize(p: dict) -> dict:
    is_org = clean(p.get("TIPO_ID")) == "N"
    s = new_std("ORGANIZATION" if is_org else "PERSON")
    if is_org:
        nit, dv = split_nit(p.get("NUM_ID"))
        s["org"] = {"legal_name": clean(p.get("RAZON_SOCIAL")) or clean(p.get("NOMBRES")), "trade_name": None, "ciiu": None, "org_type": None}
        if nit:
            s["identifiers"].append({"id_type": code("TIPO_ID", "N", "CAT_ID_TYPE"), "id_number": nit, "dv": dv, "verified": False,
                                     "verification": direct("NOT_VERIFIED", "CAT_VERIFICATION_SOURCE")})
        sub = "CUSTOMER_COMPANY"
    else:
        first, middle = split_given(p.get("NOMBRES")); sur1, sur2 = split_surnames(p.get("APELLIDOS"))
        s["person"] = {"first_name": first, "middle_name": middle, "first_surname": sur1, "second_surname": sur2,
                       "birth_date": parse_date(p.get("FECHA_NAC")), "death_date": None,
                       "gender": code("SEXO", p.get("SEXO"), "CAT_GENDER")}
        if clean(p.get("NUM_ID")):
            s["identifiers"].append({"id_type": code("TIPO_ID", p.get("TIPO_ID"), "CAT_ID_TYPE"), "id_number": clean(p["NUM_ID"]).replace(".", ""),
                                     "verified": False, "verification": direct("NOT_VERIFIED", "CAT_VERIFICATION_SOURCE")})
        sub = "CUSTOMER_PERSON"
    if sn(p.get("FALLECIDO")):
        s["status"] = code("FALLECIDO", "S", "CAT_PARTY_STATUS")
    s["roles"].append({"role": direct("CUSTOMER", "CAT_PARTY_ROLE"), "sub_role": direct(sub, "CAT_PARTY_SUB_ROLE"),
                       "business_unit": direct("CREDITO", "CAT_BUSINESS_UNIT"), "valid_from": None})
    # Obligaciones: "numero:producto:estado:fecha_ini:fecha_fin" → una fila por vínculo (1NF)
    for entry in split_multi(p.get("OBLIGACIONES")):
        parts = (entry.split(":") + ["", "", "", "", ""])[:5]
        num, prod, st, ini, fin = parts
        if not num or not prod:
            continue
        s["enrollments"].append({"service": code("PRODUCTO", prod, "CAT_SERVICE"), "status": code("ESTADO_OBLIG", st, "CAT_ENROLLMENT_STATUS"),
                                 "reference": clean(num), "enrolled_at": parse_date(ini), "closed_at": parse_date(fin) if st == "CAN" else None,
                                 "business_unit_code": "CREDITO"})
    if clean(p.get("CALIFICACION")):
        s["segments"].append({"segment_type": "FINANCIAL_RISK", "segment": code("CALIFICACION", p["CALIFICACION"], "CAT_SEGMENT_TYPE")})
    if em := email_norm(p.get("EMAIL")):
        s["contacts"].append({"channel": "EMAIL", "value": em, "is_primary": True, "raw": p.get("EMAIL")})
    if clean(p.get("CELULAR")):
        s["contacts"].append({"channel": "PHONE", "value": e164(p.get("CELULAR")), "is_primary": True, "raw": p.get("CELULAR"),
                              "origin": direct("TITULAR", "CAT_PREF_ORIGIN"), "usage_role": direct("OWNER", "CAT_CONTACT_USAGE_ROLE"),
                              "confirmation": direct("CONFIRMED_BY_TITULAR", "CAT_CONTACT_CONFIRMATION")})
    # Teléfonos de gestión: "numero:tipo:estado" (tipo TIT/REF, estado CONF/NOCONF/ERR)
    for entry in split_multi(p.get("TEL_ALTERNOS")):
        num, tipo, est = (entry.split(":") + ["TIT", "NOCONF"])[:3]
        if not clean(num):
            continue
        s["contacts"].append({"channel": "PHONE", "value": e164(num), "is_primary": False, "raw": num,
                              "origin": direct("THIRD_PARTY_REFERENCE" if tipo == "REF" else "COLLECTIONS_MANAGEMENT", "CAT_PREF_ORIGIN"),
                              "usage_role": code("TIPO_TEL", tipo, "CAT_CONTACT_USAGE_ROLE"),
                              "confirmation": code("ESTADO_TEL", est, "CAT_CONTACT_CONFIRMATION"),
                              "purposes": [dict(x) for x in COLLECTION_PURPOSES]})
    s["addresses"].append({"line": address_norm(p.get("DIRECCION")), "country": direct("COL", "CAT_COUNTRY"),
                           "divipola": direct(clean(p.get("CIUDAD")) or "", "CAT_GEO_DIVIPOLA")})
    for ctype, field in (("DATA_PROCESSING", "AUT_TRATAMIENTO"), ("COMMERCIAL", "AUT_COMERCIAL"), ("CREDIT_BUREAU", "AUT_CENTRALES")):
        if (c := consent(ctype, sn(p.get(field)))) is not None:
            s["consents"].append(c)
    if clean(p.get("CODEUDOR_ID")):   # el codeudor garantiza al cliente (inversa GUARANTEED_BY generada por el loader)
        s["relationships"].append({"to_external_id": clean(p["CODEUDOR_ID"]), "type": direct("GUARANTEED_BY", "CAT_RELATIONSHIP_TYPE")})
    return s
