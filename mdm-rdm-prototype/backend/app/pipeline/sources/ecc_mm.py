"""SAP ECC 6.0 · MM · Proveedores (LFA1). ID nativo: LIFNR."""
from app.pipeline.common import (address_norm, clean, code, consent, direct, e164, email_norm, new_std,
                                 parse_date, split_given, split_nit, split_surnames)
from app.pipeline.sources import read_csv

SOURCE_CD, ID_FIELD = "SAP_ECC_MM", "LIFNR"


def extract(path) -> list[tuple[str, dict]]:
    return [(r[ID_FIELD], r) for r in read_csv(path)]


def standardize(p: dict) -> dict:
    is_person = clean(p.get("STKZN")) == "X"
    s = new_std("PERSON" if is_person else "ORGANIZATION")
    if is_person:
        first, middle = split_given(p.get("NAME1")); sur1, sur2 = split_surnames(p.get("SORT1"))
        s["person"] = {"first_name": first, "middle_name": middle, "first_surname": sur1, "second_surname": sur2,
                       "birth_date": None, "death_date": None, "gender": None}
        if clean(p.get("STCD2")):
            s["identifiers"].append({"id_type": direct("CC", "CAT_ID_TYPE"), "id_number": clean(p["STCD2"]), "verified": False,
                                     "verification": direct("NOT_VERIFIED", "CAT_VERIFICATION_SOURCE")})
        sub = "VENDOR_SERVICES"
    else:
        nit, dv = split_nit(p.get("STCD1"))
        s["org"] = {"legal_name": clean(p.get("NAME1")), "trade_name": clean(p.get("SORT1")),
                    "ciiu": code("BRSCH", p.get("BRSCH"), "CAT_CIIU"), "org_type": code("ZZ_TIPO_SOC", p.get("ZZ_TIPO_SOC"), "CAT_ORG_TYPE")}
        if nit:
            s["identifiers"].append({"id_type": direct("NIT", "CAT_ID_TYPE"), "id_number": nit, "dv": dv, "verified": False,
                                     "verification": direct("DIAN_API", "CAT_VERIFICATION_SOURCE")})
        sub = "VENDOR_GOODS"
    if clean(p.get("LOEVM")) == "X":
        s["status"] = direct("INACTIVE", "CAT_PARTY_STATUS")
    s["roles"].append({"role": direct("VENDOR", "CAT_PARTY_ROLE"), "sub_role": direct(sub, "CAT_PARTY_SUB_ROLE"),
                       "business_unit": None, "valid_from": parse_date(p.get("ERDAT"))})
    if em := email_norm(p.get("SMTP_ADDR")):
        s["contacts"].append({"channel": "EMAIL", "value": em, "is_primary": True, "raw": p.get("SMTP_ADDR")})
    s["contacts"].append({"channel": "PHONE", "value": e164(p.get("TELF1")), "is_primary": True, "raw": p.get("TELF1")})
    s["addresses"].append({"line": address_norm(p.get("STRAS")), "country": code("LAND1", p.get("LAND1"), "CAT_COUNTRY"),
                           "divipola": direct(clean(p.get("ORT01")) or "", "CAT_GEO_DIVIPOLA"), "region": code("REGIO", p.get("REGIO"), "CAT_GEO_DIVIPOLA")})
    s["consents"].append(consent("DATA_PROCESSING", True))
    return s
