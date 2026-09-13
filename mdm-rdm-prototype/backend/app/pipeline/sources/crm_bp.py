"""SAP CRM · Business Partner (BUT000/BUT020/ADRC/BUT050). ID nativo: PARTNER.
Campos multivaluados de la fuente (TELEFONOS, RLTYP, RELACIONES, ZZ_PREF) se abren en filas (1NF)."""
from app.pipeline.common import (address_norm, clean, code, consent, direct, e164, email_norm, new_std,
                                 parse_date, split_multi, split_nit, title, yn)
from app.pipeline.sources import read_csv

SOURCE_CD, ID_FIELD = "SAP_CRM", "PARTNER"
PREF_CHANNELS = {"WHATSAPP": "WHATSAPP", "SMS": "SMS", "EMAIL": "EMAIL", "PHONE": "PHONE"}
PURPOSE_CODES = {"BEN": "BENEFITS", "COB": "COLLECTIONS", "COM": "COMMERCIAL"}


def extract(path) -> list[tuple[str, dict]]:
    return [(r[ID_FIELD], r) for r in read_csv(path)]


def standardize(p: dict) -> dict:
    is_person = clean(p.get("TYPE")) == "1"
    s = new_std("PERSON" if is_person else "ORGANIZATION")
    if is_person:
        s["person"] = {"first_name": title(p.get("NAME_FIRST")), "middle_name": title(p.get("NAMEMIDDLE")),
                       "first_surname": title(p.get("NAME_LAST")), "second_surname": title(p.get("NAME_LST2")),
                       "birth_date": parse_date(p.get("BIRTHDT")), "death_date": None,
                       "gender": code("GESCHL", p.get("GESCHL"), "CAT_GENDER")}
        if clean(p.get("IDNUMBER")):
            s["identifiers"].append({"id_type": code("IDTYPE", p.get("IDTYPE"), "CAT_ID_TYPE"), "id_number": clean(p["IDNUMBER"]),
                                     "verified": False, "verification": direct("MANUAL", "CAT_VERIFICATION_SOURCE")})
    else:
        nit, dv = split_nit(p.get("IDNUMBER"))
        s["org"] = {"legal_name": clean(p.get("NAME_ORG1")), "trade_name": clean(p.get("NAME_ORG2")), "ciiu": None,
                    "org_type": code("ZZ_TIPO_ORG", p.get("ZZ_TIPO_ORG"), "CAT_ORG_TYPE")}
        if nit:
            s["identifiers"].append({"id_type": direct("NIT", "CAT_ID_TYPE"), "id_number": nit, "dv": dv, "verified": False,
                                     "verification": direct("MANUAL", "CAT_VERIFICATION_SOURCE")})
    if clean(p.get("ZZ_FALLECIDO")):
        s["status"] = code("ZZ_FALLECIDO", p["ZZ_FALLECIDO"], "CAT_PARTY_STATUS")
    # Roles (RLTYP multivaluado). ZSUB es vínculo de servicio (cuota monetaria), no rol.
    for rl in split_multi(p.get("RLTYP")):
        if rl == "ZSUB":
            s["enrollments"].append({"service": code("RLTYP", rl, "CAT_SERVICE"), "status": code("ZZ_ESTADO_AFIL", p.get("ZZ_ESTADO_AFIL") or "A", "CAT_ENROLLMENT_STATUS"),
                                     "reference": clean(p.get("ZZ_AFILIACION")) or f"SUB-{p[ID_FIELD]}", "enrolled_at": None, "closed_at": None})
            continue
        sub = {"ZAFI": "AFFILIATE_WORKER", "ZEMP": "COMPANY_PRIVATE", "ZBEN": None}.get(rl)
        s["roles"].append({"role": code("RLTYP", rl, "CAT_PARTY_ROLE"), "sub_role": direct(sub, "CAT_PARTY_SUB_ROLE") if sub else None,
                           "business_unit": direct("SUBSIDIO", "CAT_BUSINESS_UNIT") if rl in {"ZAFI", "ZEMP", "ZBEN"} else None, "valid_from": None})
    if clean(p.get("ZZ_CATEGORIA")):
        s["segments"].append({"segment_type": "AFFILIATION", "segment": code("ZZ_CATEGORIA", p["ZZ_CATEGORIA"], "CAT_SEGMENT_TYPE")})
    if em := email_norm(p.get("SMTP_ADDR")):
        purposes = None
        if clean(p.get("ZZ_PREF_EMAIL")):
            purposes = [{"purpose": PURPOSE_CODES.get(k, k), "allowed": yn(v)} for k, v in (x.split(":") for x in split_multi(p["ZZ_PREF_EMAIL"]) if ":" in x)]
        s["contacts"].append({"channel": "EMAIL", "value": em, "is_primary": True, "raw": p.get("SMTP_ADDR"), "purposes": purposes})
    # Teléfonos: numero:origen:uso:confirmacion
    for i, entry in enumerate(split_multi(p.get("TELEFONOS"))):
        parts = (entry.split(":") + ["TIT", "OWN", "TIT"])[:4]
        num, origen, uso, conf = parts
        c = {"channel": "PHONE", "value": e164(num), "is_primary": i == 0, "raw": num,
             "origin": code("ZZ_ORIGEN_TEL", origen, "CAT_PREF_ORIGIN"), "usage_role": code("ZZ_USO_TEL", uso, "CAT_CONTACT_USAGE_ROLE"),
             "confirmation": code("ZZ_CONF_TEL", conf, "CAT_CONTACT_CONFIRMATION")}
        if origen in {"COB", "REF"}:   # aportado por cobranza o tercero: solo COLLECTIONS (SPEC §7 etapa 7)
            c["purposes"] = [{"purpose": "COLLECTIONS", "allowed": True}, {"purpose": "BENEFITS", "allowed": False}, {"purpose": "COMMERCIAL", "allowed": False}]
        s["contacts"].append(c)
    s["addresses"].append({"line": address_norm(p.get("STREET")), "country": direct("COL" if clean(p.get("COUNTRY")) == "CO" else (clean(p.get("COUNTRY")) or ""), "CAT_COUNTRY"),
                           "divipola": direct(clean(p.get("CITY1")) or "", "CAT_GEO_DIVIPOLA")})
    for ctype, field in (("DATA_PROCESSING", "ZZ_CONSENT_DP"), ("COMMERCIAL", "ZZ_CONSENT_COM")):
        if (c := consent(ctype, yn(p.get(field)))) is not None:
            s["consents"].append(c)
    for entry in split_multi(p.get("ZZ_PREF")):        # canal:Y/N → preferencia de canal para todas las finalidades
        ch, _, v = entry.partition(":")
        if ch in PREF_CHANNELS and yn(v) is not None:
            for purpose in ("COLLECTIONS", "BENEFITS", "COMMERCIAL"):
                s["prefs"].append({"channel": PREF_CHANNELS[ch], "purpose": purpose, "allowed": yn(v)})
    for entry in split_multi(p.get("RELACIONES")):     # partner:RELTYP
        to_id, _, rt = entry.partition(":")
        if to_id and rt:
            s["relationships"].append({"to_external_id": to_id.strip(), "type": code("RELTYP", rt, "CAT_RELATIONSHIP_TYPE")})
    if clean(p.get("ZZ_GRUPO_FAM")):
        roles = split_multi(p.get("RLTYP"))
        s["group"] = {"reference": clean(p["ZZ_GRUPO_FAM"]), "group_type": "FAMILY",
                      "member_role": "ANCHOR" if "ZAFI" in roles else ("BENEFICIARY" if "ZBEN" in roles else "MEMBER")}
    return s
