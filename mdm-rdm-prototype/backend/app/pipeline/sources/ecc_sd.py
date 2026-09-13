"""SAP ECC 6.0 · SD · Clientes (KNA1). ID nativo: KUNNR. Persona natural cuando STKZN = X."""
from app.pipeline.common import (address_norm, clean, code, consent, direct, e164, email_norm, new_std,
                                 normalized_key, parse_date, split_given, split_multi, split_nit, split_surnames, title)
from app.pipeline.sources import read_csv

SOURCE_CD, ID_FIELD = "SAP_ECC_SD", "KUNNR"


def extract(path) -> list[tuple[str, dict]]:
    return [(r[ID_FIELD], r) for r in read_csv(path)]


def standardize(p: dict) -> dict:
    is_person = clean(p.get("STKZN")) == "X"
    s = new_std("PERSON" if is_person else "ORGANIZATION")
    if is_person:
        first, middle = split_given(p.get("NAME1")); sur1, sur2 = split_surnames(p.get("NAME2"))
        s["person"] = {"first_name": first, "middle_name": middle, "first_surname": sur1, "second_surname": sur2,
                       "birth_date": parse_date(p.get("GBDAT")), "death_date": None, "gender": None}
        if clean(p.get("STCD2")):
            s["identifiers"].append({"id_type": direct("CC", "CAT_ID_TYPE"), "id_number": clean(p["STCD2"]), "verified": False,
                                     "verification": direct("NOT_VERIFIED", "CAT_VERIFICATION_SOURCE")})
        sub = "CUSTOMER_PERSON"
    else:
        nit, dv = split_nit(p.get("STCD1"))
        s["org"] = {"legal_name": clean(p.get("NAME1")), "trade_name": clean(p.get("NAME2")), "ciiu": None, "org_type": None}
        if nit:
            s["identifiers"].append({"id_type": direct("NIT", "CAT_ID_TYPE"), "id_number": nit, "dv": dv, "verified": False,
                                     "verification": direct("NOT_VERIFIED", "CAT_VERIFICATION_SOURCE")})
        sub = "CUSTOMER_COMPANY"
    if clean(p.get("LOEVM")) == "X":
        s["status"] = direct("INACTIVE", "CAT_PARTY_STATUS")
    # Contratos: "ref:servicio:estado" — una fila por vínculo (1NF)
    ues_seen = set()
    for entry in split_multi(p.get("ZZ_CONTRATOS")):
        parts = entry.split(":")
        if len(parts) != 3:
            continue
        ref, svc, st = parts
        s["enrollments"].append({"service": code("KTOKD", svc, "CAT_SERVICE"), "status": code("ZZ_ESTADO_CONTRATO", st, "CAT_ENROLLMENT_STATUS"),
                                 "reference": clean(ref), "enrolled_at": parse_date(p.get("ERDAT")),
                                 "closed_at": parse_date(p.get("AEDAT")) if st == "C" else None})
    for svc in split_multi(p.get("ZZ_SERVICIOS")):   # consumos puntuales: el DQ los rechaza por §3.18
        s["enrollments"].append({"service": code("KTOKD", svc, "CAT_SERVICE"), "status": direct("ACTIVE", "CAT_ENROLLMENT_STATUS"),
                                 "reference": f"TX-{p[ID_FIELD]}-{svc}", "enrolled_at": None, "closed_at": None, "transactional_hint": True})
    s["roles"].append({"role": direct("CUSTOMER", "CAT_PARTY_ROLE"), "sub_role": direct(sub, "CAT_PARTY_SUB_ROLE"),
                       "business_unit": None, "valid_from": parse_date(p.get("ERDAT"))})
    if clean(p.get("CTLPC")):
        s["segments"].append({"segment_type": "FINANCIAL_RISK", "segment": code("CTLPC", p["CTLPC"], "CAT_SEGMENT_TYPE")})
    if em := email_norm(p.get("SMTP_ADDR")):
        s["contacts"].append({"channel": "EMAIL", "value": em, "is_primary": True, "raw": p.get("SMTP_ADDR")})
    s["contacts"].append({"channel": "PHONE", "value": e164(p.get("TELF1")), "is_primary": True, "raw": p.get("TELF1")})
    s["addresses"].append({"line": address_norm(p.get("STRAS")), "country": code("LAND1", p.get("LAND1"), "CAT_COUNTRY"),
                           "divipola": direct(clean(p.get("ORT01")) or "", "CAT_GEO_DIVIPOLA"), "region": code("REGIO", p.get("REGIO"), "CAT_GEO_DIVIPOLA")})
    s["consents"].append(consent("DATA_PROCESSING", True))   # relación contractual
    return s
