"""SuccessFactors Employee Central · Empleados. ID nativo: personIdExternal."""
from app.pipeline.common import (address_norm, clean, code, consent, direct, e164, email_norm, new_std,
                                 parse_date, title)
from app.pipeline.sources import read_csv

SOURCE_CD, ID_FIELD = "SF_EC", "personIdExternal"


def extract(path) -> list[tuple[str, dict]]:
    return [(r[ID_FIELD], r) for r in read_csv(path)]


def standardize(p: dict) -> dict:
    s = new_std("PERSON")
    s["person"] = {"first_name": title(p.get("firstName")), "middle_name": title(p.get("middleName")),
                   "first_surname": title(p.get("lastName")), "second_surname": title(p.get("secondLastName")),
                   "birth_date": parse_date(p.get("dateOfBirth")), "death_date": None,
                   "gender": code("gender", p.get("gender"), "CAT_GENDER")}
    if clean(p.get("terminationReason")):
        s["status"] = code("terminationReason", p["terminationReason"], "CAT_PARTY_STATUS")
    elif clean(p.get("employmentStatus")) == "T":
        s["status"] = code("employmentStatus", "T", "CAT_PARTY_STATUS")
    if clean(p.get("nationalId")):
        s["identifiers"].append({"id_type": code("nationalIdType", p.get("nationalIdType"), "CAT_ID_TYPE"),
                                 "id_number": clean(p["nationalId"]), "verified": True,
                                 "verification": direct("RNEC_API", "CAT_VERIFICATION_SOURCE")})
    s["roles"].append({"role": direct("EMPLOYEE", "CAT_PARTY_ROLE"), "sub_role": direct("EMPLOYEE_PERMANENT", "CAT_PARTY_SUB_ROLE"),
                       "business_unit": code("division", p.get("division"), "CAT_BUSINESS_UNIT"),
                       "valid_from": parse_date(p.get("hireDate"))})
    if em := email_norm(p.get("email")):
        s["contacts"].append({"channel": "EMAIL", "value": em, "is_primary": True, "raw": p.get("email")})
    ph = e164(p.get("cellPhone"))
    s["contacts"].append({"channel": "PHONE", "value": ph, "is_primary": True, "raw": p.get("cellPhone")})
    s["addresses"].append({"line": address_norm(p.get("street")), "country": direct("COL", "CAT_COUNTRY"),
                           "divipola": direct(clean(p.get("city")) or "", "CAT_GEO_DIVIPOLA")})
    s["consents"].append(consent("DATA_PROCESSING", True))   # base contractual de la vinculación laboral
    return s
