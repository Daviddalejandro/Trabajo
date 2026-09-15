"""Genera los CSV sintéticos de las 5 fuentes con solapamiento controlado y los casos
plantados A–T (SPEC §13). Escribe data/synth/<fuente>.csv y data/synth/manifest.json
(ids externos de cada caso para los tests). Los documentos usan rangos no plausibles
(cédulas 900xxxxxx / NIT 8xxxxxxxx ficticios) marcados como sintéticos.
"""
from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "synth"
UES = ["SUB", "SAL", "EDU", "VIV", "CRE", "REC", "HOT", "MER"]
CITIES = ["11001", "05001", "25286", "25754", "76001"]
REGIO_BY_CITY = {"11001": "BOG", "05001": "ANT", "25286": "CUN", "25754": "CUN", "76001": "VAL"}


def nit_check_digit(nit: str) -> int:
    weights = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    total = sum(int(d) * w for d, w in zip(reversed(nit), weights))
    r = total % 11
    return r if r < 2 else 11 - r


@dataclass
class Person:
    pid: int
    first: str
    middle: str
    sur1: str
    sur2: str
    gender: str          # M/F
    birth: date
    doc_type: str        # CC/CE/TI/PAS/PPT
    doc: str
    email: str
    phone: str           # 10 dígitos nacionales
    city: str
    street: str
    sources: dict = field(default_factory=dict)   # source -> external_id


@dataclass
class Org:
    oid: int
    legal: str
    trade: str
    nit: str
    dv: int
    org_type: str
    brsch: str
    city: str
    street: str
    sources: dict = field(default_factory=dict)


class Universe:
    def __init__(self, seed: int, n_persons: int = 800, n_orgs: int = 120):
        self.seed = seed
        self.rng = random.Random(seed)
        self.fake = Faker("es_CO")
        Faker.seed(seed)
        self.persons: list[Person] = []
        self.orgs: list[Org] = []
        self.rows: dict[str, list[dict]] = {k: [] for k in ["sf_ec", "ecc_sd", "ecc_mm", "crm_bp", "web_portal"]}
        self.delta_rows: dict[str, list[dict]] = {"ecc_sd": []}   # corridas delta plantadas (caso S)
        self.manifest: dict = {"seed": seed, "cases": {}}
        self._docs: set[str] = set()
        self._next = {"pernr": 10000, "kunnr": 300000, "lifnr": 500000, "partner": 7000000, "user": 1}
        for i in range(n_persons):
            self.persons.append(self._person(i))
        for i in range(n_orgs):
            self.orgs.append(self._org(i))

    # ------------------------------------------------------------------ fábricas
    def _doc(self) -> str:
        while True:
            d = f"9{self.rng.randint(10_000_000, 99_999_999)}"   # rango ficticio 9xxxxxxxx
            if d not in self._docs:
                self._docs.add(d)
                return d

    def _person(self, i: int, minor: bool = False) -> Person:
        g = self.rng.choice(["M", "F"])
        first = self.fake.first_name_male() if g == "M" else self.fake.first_name_female()
        middle = (self.fake.first_name_male() if g == "M" else self.fake.first_name_female()) if self.rng.random() < 0.6 else ""
        years = self.rng.randint(5, 17) if minor else self.rng.randint(18, 85)
        birth = date(2026, 9, 13) - timedelta(days=years * 365 + self.rng.randint(0, 364))
        doc_type = "TI" if minor else self.rng.choices(["CC", "CE", "PAS", "PPT"], [0.9, 0.05, 0.03, 0.02])[0]
        city = self.rng.choice(CITIES)
        return Person(
            pid=i, first=first, middle=middle, sur1=self.fake.last_name(), sur2=self.fake.last_name(), gender=g,
            birth=birth, doc_type=doc_type, doc=self._doc(),
            email=f"{first}.{self.fake.last_name()}{i}@ejemplo.test".lower().replace(" ", ""),
            phone=f"3{self.rng.randint(0, 4)}{self.rng.randint(10_000_000, 99_999_999)}",
            city=city, street=self.fake.street_address(),
        )

    def _org(self, i: int) -> Org:
        base = self.fake.company().replace(",", "")
        org_type = self.rng.choice(["SAS", "LTDA", "SA", "ESAL"])
        suffix = {"SAS": "S.A.S.", "LTDA": "Ltda.", "SA": "S.A.", "ESAL": "Fundación"}[org_type]
        legal = f"{suffix} {base}" if org_type == "ESAL" else f"{base} {suffix}"
        nit = f"8{self.rng.randint(10_000_000, 99_999_999)}"
        return Org(oid=i, legal=legal, trade=base.upper(), nit=nit, dv=nit_check_digit(nit), org_type=org_type,
                   brsch=self.rng.choice(["G471", "Q861", "K649", "I551", "P852"]),
                   city=self.rng.choice(CITIES), street=self.fake.street_address())

    def new_id(self, kind: str) -> str:
        self._next[kind] += 1
        n = self._next[kind]
        return {"pernr": f"{n:08d}", "kunnr": f"{n:010d}", "lifnr": f"{n:010d}", "partner": f"{n:010d}", "user": f"u{n:06d}"}[kind]

    # ------------------------------------------------------------------ emisores por fuente
    def emit_sf_ec(self, p: Person, division: str | None = None, status: str = "A", term_reason: str = "") -> str:
        pid = self.new_id("pernr"); p.sources["sf_ec"] = pid
        self.rows["sf_ec"].append({
            "personIdExternal": pid, "firstName": p.first, "middleName": p.middle, "lastName": p.sur1,
            "secondLastName": p.sur2, "gender": p.gender, "dateOfBirth": p.birth.isoformat(),
            "nationalIdType": p.doc_type, "nationalId": p.doc, "email": p.email, "cellPhone": p.phone,
            "employmentStatus": status, "terminationReason": term_reason,
            "hireDate": (p.birth + timedelta(days=365 * 22)).isoformat(),
            "division": division or self.rng.choice(UES), "city": p.city, "street": p.street,
            "lastModifiedDateTime": "2026-09-01T02:00:00",
        })
        return pid

    def emit_sd_person(self, p: Person, contracts: list[tuple[str, str, str]] | None = None, risk: str = "",
                       extra_services: str = "", name_variant: str | None = None, doc: str | None = "keep",
                       phone: str | None = None, bprol: str = "ZAFI", categoria: str = "", beneficiario_de: str = "") -> str:
        kid = self.new_id("kunnr"); p.sources["ecc_sd"] = kid
        contracts = contracts or [(f"CR-{kid[-5:]}", "ZCRE", "A")]
        first = name_variant or f"{p.first} {p.middle}".strip()
        self.rows["ecc_sd"].append({
            "KUNNR": kid, "KTOKD": "ZPER", "STKZN": "X", "NAME1": first, "NAME2": f"{p.sur1} {p.sur2}",
            "STCD1": "", "STCD2": (p.doc if doc == "keep" else (doc or "")), "GBDAT": p.birth.isoformat(),
            "LAND1": "CO", "REGIO": REGIO_BY_CITY[p.city], "ORT01": p.city, "STRAS": p.street,
            "TELF1": phone if phone is not None else p.phone, "SMTP_ADDR": p.email.upper(), "CTLPC": risk,
            "ZZ_CONTRATOS": ";".join(f"{r}:{s}:{st}" for r, s, st in contracts), "ZZ_SERVICIOS": extra_services,
            "BPROL": bprol, "ZZ_CATEGORIA": categoria, "ZZ_BENEFICIARIO_DE": beneficiario_de,
            "LOEVM": "", "ERDAT": "2024-03-01", "AEDAT": "2026-09-01",
        })
        return kid

    def emit_sd_org(self, o: Org, legal: str | None = None, contracts: list[tuple[str, str, str]] | None = None) -> str:
        kid = self.new_id("kunnr"); o.sources["ecc_sd"] = kid
        contracts = contracts or [(f"CT-{kid[-5:]}", "ZSAL", "A")]
        self.rows["ecc_sd"].append({
            "KUNNR": kid, "KTOKD": "ZORG", "STKZN": "", "NAME1": legal or o.legal, "NAME2": o.trade,
            "STCD1": f"{o.nit}-{o.dv}", "STCD2": "", "GBDAT": "", "LAND1": "CO", "REGIO": REGIO_BY_CITY[o.city],
            "ORT01": o.city, "STRAS": o.street, "TELF1": f"601{self.rng.randint(1_000_000, 9_999_999)}",
            "SMTP_ADDR": f"contacto@{o.trade.split()[0].lower()}.test", "CTLPC": "",
            "ZZ_CONTRATOS": ";".join(f"{r}:{s}:{st}" for r, s, st in contracts), "ZZ_SERVICIOS": "",
            "BPROL": "ZEMP", "ZZ_CATEGORIA": "", "ZZ_BENEFICIARIO_DE": "",
            "LOEVM": "", "ERDAT": "2023-05-01", "AEDAT": "2026-09-01",
        })
        return kid

    def emit_mm_org(self, o: Org, legal: str | None = None, bad_dv: bool = False) -> str:
        lid = self.new_id("lifnr"); o.sources["ecc_mm"] = lid
        dv = (o.dv + 1) % 10 if bad_dv else o.dv
        self.rows["ecc_mm"].append({
            "LIFNR": lid, "KTOKK": "ZLIE", "STKZN": "", "NAME1": legal or o.legal, "SORT1": o.trade,
            "STCD1": f"{o.nit}-{dv}", "STCD2": "", "LAND1": "CO", "REGIO": REGIO_BY_CITY[o.city], "ORT01": o.city,
            "STRAS": o.street, "TELF1": f"601{self.rng.randint(1_000_000, 9_999_999)}",
            "SMTP_ADDR": f"proveedores@{o.trade.split()[0].lower()}.test", "BRSCH": o.brsch,
            "ZZ_TIPO_SOC": o.org_type, "LOEVM": "", "ERDAT": "2022-01-15",
        })
        return lid

    def emit_mm_person(self, p: Person) -> str:
        lid = self.new_id("lifnr"); p.sources["ecc_mm"] = lid
        self.rows["ecc_mm"].append({
            "LIFNR": lid, "KTOKK": "ZLIE", "STKZN": "X", "NAME1": f"{p.first} {p.middle}".strip(),
            "SORT1": f"{p.sur1} {p.sur2}", "STCD1": "", "STCD2": p.doc, "LAND1": "CO",
            "REGIO": REGIO_BY_CITY[p.city], "ORT01": p.city, "STRAS": p.street, "TELF1": p.phone,
            "SMTP_ADDR": p.email, "BRSCH": "", "ZZ_TIPO_SOC": "", "LOEVM": "", "ERDAT": "2022-06-15",
        })
        return lid

    def emit_crm_person(self, p: Person, roles: str = "ZAFI", categoria: str = "", telefonos: list[str] | None = None,
                        relaciones: list[str] | None = None, grupo: str = "", consent_dp: str = "Y", consent_com: str = "Y",
                        prefs: str = "", email_prefs: str = "", fallecido: str = "", estado_afil: str = "A",
                        afiliacion: str | None = None, id_type: str | None = None) -> str:
        pid = self.new_id("partner"); p.sources["crm_bp"] = pid
        tels = telefonos if telefonos is not None else [f"{p.phone}:TIT:OWN:TIT"]
        idt = id_type or {"CC": "ZCC", "CE": "ZCE", "TI": "ZTI", "PAS": "ZPAS", "PPT": "ZPPT"}[p.doc_type]
        self.rows["crm_bp"].append({
            "PARTNER": pid, "TYPE": "1", "NAME_FIRST": p.first, "NAMEMIDDLE": p.middle, "NAME_LAST": p.sur1,
            "NAME_LST2": p.sur2, "NAME_ORG1": "", "NAME_ORG2": "", "GESCHL": "1" if p.gender == "M" else "2",
            "BIRTHDT": p.birth.strftime("%Y%m%d"), "IDTYPE": idt, "IDNUMBER": p.doc, "RLTYP": roles,
            "ZZ_CATEGORIA": categoria, "ZZ_AFILIACION": afiliacion if afiliacion is not None else (f"AF-{pid[-6:]}" if "ZAFI" in roles else ""),
            "ZZ_ESTADO_AFIL": estado_afil, "COUNTRY": "CO", "REGION": REGIO_BY_CITY[p.city], "CITY1": p.city,
            "STREET": p.street, "SMTP_ADDR": p.email, "TELEFONOS": ";".join(tels),
            "RELACIONES": ";".join(relaciones or []), "ZZ_GRUPO_FAM": grupo, "ZZ_CONSENT_DP": consent_dp,
            "ZZ_CONSENT_COM": consent_com, "ZZ_PREF": prefs, "ZZ_PREF_EMAIL": email_prefs, "ZZ_FALLECIDO": fallecido,
            "ZZ_TIPO_ORG": "", "CHDAT": "20260901",
        })
        return pid

    def emit_crm_org(self, o: Org, roles: str = "ZEMP", relaciones: list[str] | None = None) -> str:
        pid = self.new_id("partner"); o.sources["crm_bp"] = pid
        self.rows["crm_bp"].append({
            "PARTNER": pid, "TYPE": "2", "NAME_FIRST": "", "NAMEMIDDLE": "", "NAME_LAST": "", "NAME_LST2": "",
            "NAME_ORG1": o.legal, "NAME_ORG2": o.trade, "GESCHL": "", "BIRTHDT": "", "IDTYPE": "ZNIT",
            "IDNUMBER": f"{o.nit}-{o.dv}", "RLTYP": roles, "ZZ_CATEGORIA": "", "ZZ_AFILIACION": "", "ZZ_ESTADO_AFIL": "",
            "COUNTRY": "CO", "REGION": REGIO_BY_CITY[o.city], "CITY1": o.city, "STREET": o.street,
            "SMTP_ADDR": f"rrhh@{o.trade.split()[0].lower()}.test", "TELEFONOS": f"601{self.rng.randint(1_000_000, 9_999_999)}:TIT:OWN:TIT",
            "RELACIONES": ";".join(relaciones or []), "ZZ_GRUPO_FAM": "", "ZZ_CONSENT_DP": "Y", "ZZ_CONSENT_COM": "N",
            "ZZ_PREF": "", "ZZ_PREF_EMAIL": "", "ZZ_FALLECIDO": "", "ZZ_TIPO_ORG": o.org_type, "CHDAT": "20260901",
        })
        return pid

    def emit_portal(self, p: Person, categoria: str = "", segmento: str = "", doc: str | None = "keep",
                    tipo_doc: str | None = None, nombres: str | None = None, apellidos: str | None = None,
                    acepta_datos: str = "true", acepta_comercial: str = "true", genero: str | None = None) -> str:
        uid = self.new_id("user"); p.sources["web_portal"] = uid
        td = tipo_doc or {"CC": "cedula", "CE": "cedula_extranjeria", "TI": "tarjeta_identidad", "PAS": "pasaporte", "PPT": "ppt"}[p.doc_type]
        self.rows["web_portal"].append({
            "user_id": uid, "tipo_doc": td if doc else "", "num_doc": (p.doc if doc == "keep" else (doc or "")),
            "nombres": nombres if nombres is not None else f"{p.first} {p.middle}".strip(),
            "apellidos": apellidos if apellidos is not None else f"{p.sur1} {p.sur2}",
            "fecha_nacimiento": p.birth.isoformat(), "genero": genero or p.gender, "email": p.email,
            "celular": f"+57 {p.phone[:3]} {p.phone[3:6]} {p.phone[6:]}", "categoria": categoria,
            "segmento_comercial": segmento, "acepta_datos": acepta_datos, "acepta_comercial": acepta_comercial,
            "ciudad": p.city, "updated_at": "2026-09-05T10:00:00",
        })
        return uid

    # ------------------------------------------------------------------ escenario
    def build(self) -> None:
        rng = self.rng
        P, O = self.persons, self.orgs
        cases = self.manifest["cases"]
        # Reservas para casos plantados: personas 0..39, organizaciones 0..9
        reserved_p, reserved_o = 40, 10

        # --- población base con solapamiento controlado
        for p in P[reserved_p:]:
            r = rng.random()
            if r < 0.30:   # empleado + afiliado
                self.emit_sf_ec(p); self.emit_crm_person(p, categoria=rng.choice("ABC"))
            elif r < 0.55: # afiliado + cliente SD
                self.emit_crm_person(p, categoria=rng.choice("ABC")); self.emit_sd_person(p, risk=rng.choice(["001", "002", "003"]))
            elif r < 0.75: # afiliado + portal
                self.emit_crm_person(p, categoria=rng.choice("ABC")); self.emit_portal(p, categoria=rng.choice("ABC"), segmento=rng.choice(["basico", "premium"]))
            elif r < 0.85: # solo portal
                self.emit_portal(p, segmento=rng.choice(["basico", "premium"]))
            elif r < 0.92: # solo SD
                self.emit_sd_person(p, risk=rng.choice(["001", "002", "003"]))
            elif r < 0.96: # proveedor persona natural
                self.emit_mm_person(p)
            else:          # en las tres: empleado, afiliado y portal
                self.emit_sf_ec(p); self.emit_crm_person(p, categoria=rng.choice("ABC")); self.emit_portal(p, categoria=rng.choice("ABC"))
        for o in O[reserved_o:]:
            r = rng.random()
            if r < 0.5:
                self.emit_mm_org(o)
            elif r < 0.8:
                self.emit_crm_org(o); self.emit_sd_org(o)
            else:
                self.emit_mm_org(o); self.emit_crm_org(o)

        # --- Caso A · auto-merge: misma persona en ECC_SD y CRM, mismo documento, variación tipográfica leve
        a = P[0]
        cases["A"] = {"ecc_sd": self.emit_sd_person(a, name_variant=f"{a.first[:-1]}{a.first[-1].swapcase()} {a.middle}".strip()),
                      "crm_bp": self.emit_crm_person(a, categoria="A"), "doc": a.doc}
        # --- Caso B · probable en una sola fuente: usuario re-registrado sin documento, JW alto + misma fecha
        b = P[1]
        cases["B"] = {"web_portal_1": self.emit_portal(b, categoria="B"),
                      "web_portal_2": self.emit_portal(b, doc=None, nombres=f"{b.first} {b.middle}".strip().replace("a", "á", 1),
                                                       acepta_comercial="false")}
        # --- Caso C · posible: homónimos con fecha distinta
        c1, c2 = P[2], P[3]
        c2.first, c2.middle, c2.sur1, c2.sur2 = c1.first, c1.middle, c1.sur1, c1.sur2
        c2.birth = c1.birth + timedelta(days=200)   # fecha distinta dentro del año: puntaje parcial → zona POSSIBLE
        c2.city = c1.city
        cases["C"] = {"crm_bp": self.emit_crm_person(c1, categoria="C"), "web_portal": self.emit_portal(c2)}
        # --- Caso D · organización duplicada: mismo NIT, "La Espiga S.A.S." vs "LA ESPIGA"
        d = O[0]; d.legal, d.trade, d.org_type = "La Espiga S.A.S.", "LA ESPIGA", "SAS"
        cases["D"] = {"ecc_mm": self.emit_mm_org(d, legal="La Espiga S.A.S."), "ecc_sd": self.emit_sd_org(d, legal="LA ESPIGA"), "nit": d.nit}
        # --- Caso E · no contacto: consent COMMERCIAL revocado (N) y pref WHATSAPP denegada
        e = P[4]
        cases["E"] = {"crm_bp": self.emit_crm_person(e, categoria="A", consent_com="N", prefs="WHATSAPP:N")}
        # --- Caso F · ARCO sobre party fusionado: usa el caso A (se decide en F5)
        cases["F"] = {"uses": "A"}
        # --- Caso G · caché XREF: segunda corrida de ECC_SD (se ejecuta en tests)
        cases["G"] = {"source": "ecc_sd"}
        # --- Caso H · RNE: titular con consent COMMERCIAL GRANTED cuyo celular está en el RNE simulado
        h = P[5]
        cases["H"] = {"crm_bp": self.emit_crm_person(h, categoria="B", consent_com="Y"),
                      "ecc_sd": self.emit_sd_person(h, contracts=[("CR-H0005", "ZCRE", "A")]), "phone": h.phone}   # crédito vigente: cobranza legítima
        # --- Caso I · segmentos multi-tipo: AFFILIATION=A (CRM), FINANCIAL_RISK=HIGH (SD), COMMERCIAL=PREMIUM (portal)
        i = P[6]
        cases["I"] = {"crm_bp": self.emit_crm_person(i, categoria="A"), "ecc_sd": self.emit_sd_person(i, risk="003"),
                      "web_portal": self.emit_portal(i, categoria="A", segmento="premium"), "doc": i.doc}
        # --- Caso J · contacto compartido: celular del hijo (menor) OWNER; madre GUARDIAN; grupo familiar
        mother, child = P[7], self._person(9007, minor=True)
        child.sur1, child.sur2 = mother.sur1, self.fake.last_name()
        self.persons.append(child)
        shared = child.phone
        mother.phone = f"31{rng.randint(10_000_000, 99_999_999)}"
        cases["J"] = {"mother": self.emit_crm_person(mother, categoria="A", grupo="FAM-0007",
                                                     telefonos=[f"{mother.phone}:TIT:OWN:TIT", f"{shared}:TIT:GUA:TIT"]),
                      "child": self.emit_crm_person(child, roles="ZBEN", grupo="FAM-0007", telefonos=[f"{shared}:TIT:OWN:TIT"],
                                                    consent_com="Y"), "shared_phone": shared}
        # relaciones madre→hijo (PARENT_OF con inversa CHILD_OF) se adjuntan al caso O
        # --- Caso K · zona gris entre owners: SF_EC vs CRM, sin documento común (CRM sin documento), nombres JW alto + misma fecha
        k = P[8]
        cases["K"] = {"sf_ec": self.emit_sf_ec(k, division="SAL"), "crm_bp": self.emit_crm_person(k, categoria="B", id_type="ZPAS")}
        self.rows["crm_bp"][-1]["IDNUMBER"] = f"P{rng.randint(100000, 999999)}"   # pasaporte distinto: sin documento común
        # --- Caso L · unmerge del caso A (se ejecuta en F3)
        cases["L"] = {"uses": "A"}
        # --- Caso M · audiencia (F5) / N · match-preview con datos del caso A (F3)
        cases["M"] = {"role": "AFFILIATE"}; cases["N"] = {"uses": "A"}
        # --- Caso O · relaciones P/O: LEGAL_REP_OF, SUBSIDIARY_OF, PARENT_OF/CHILD_OF; SPOUSE_OF P→O rechazado
        rep, org1, org2 = P[9], O[1], O[2]
        crm_org1 = self.emit_crm_org(org1); crm_org2 = self.emit_crm_org(org2, relaciones=[f"{crm_org1}:ZSUB"])
        crm_rep = self.emit_crm_person(rep, categoria="A", relaciones=[f"{crm_org1}:ZREP", f"{crm_org2}:ZSPO"])
        # madre PARENT_OF hijo (caso J) → inversa CHILD_OF automática
        self.rows["crm_bp"][[r["PARTNER"] for r in self.rows["crm_bp"]].index(cases["J"]["mother"])]["RELACIONES"] = f"{cases['J']['child']}:ZPAR"
        cases["O"] = {"rep": crm_rep, "org1": crm_org1, "org2": crm_org2, "mother": cases["J"]["mother"], "child": cases["J"]["child"]}
        # --- Caso P · rehomologación: CRM RLTYP=ZPRV sin mapeo
        pp = P[10]
        cases["P"] = {"crm_bp": self.emit_crm_person(pp, roles="ZPRV", afiliacion="")}
        # --- Caso Q · fallecido (SF_EC terminación por muerte) y SLA ARCO vencido (F5)
        q = P[11]
        cases["Q"] = {"sf_ec": self.emit_sf_ec(q, status="T", term_reason="DEATH"), "crm_bp": self.emit_crm_person(q, categoria="C")}
        # --- Caso R · vínculos de servicio: CUOTA_MONETARIA (CRM), 2 CREDITO_SOCIAL (uno CLOSED) + SALUD_EPS (SD),
        #     más HOTEL y SUPERMERCADO transaccionales rechazados
        r_ = P[12]
        cases["R"] = {"crm_bp": self.emit_crm_person(r_, roles="ZAFI;ZSUB", categoria="A", afiliacion="AF-R00012"),
                      "ecc_sd": self.emit_sd_person(r_, contracts=[("CR-1001", "ZCRE", "A"), ("CR-0990", "ZCRE", "C"), ("EPS-77", "ZSAL", "A")],
                                                    risk="002", extra_services="ZHOT;ZSUP"), "doc": r_.doc}
        # --- Caso S · cobranza solo con obligación vigente: consent DP sí, sin crédito activo
        s = P[13]
        cases["S"] = {"crm_bp": self.emit_crm_person(s, categoria="B", consent_dp="Y", consent_com="N"), "doc": s.doc}
        # el crédito de S llega después, en una corrida delta de ECC_SD (archivo aparte, no en la carga inicial)
        cases["S"]["delta_kunnr"] = self.emit_sd_person(s, contracts=[("CR-S0013", "ZCRE", "A")])
        self.delta_rows["ecc_sd"].append(self.rows["ecc_sd"].pop())
        # --- Caso T · finalidades por contacto y teléfonos de cobranza
        t = P[14]
        t_tels = [f"{t.phone}:TIT:OWN:TIT", f"30{rng.randint(10_000_000, 99_999_999)}:COB:OWN:UNC",
                  f"31{rng.randint(10_000_000, 99_999_999)}:REF:REF:UNC", f"32{rng.randint(10_000_000, 99_999_999)}:COB:OWN:WRG"]
        cases["T"] = {"crm_bp": self.emit_crm_person(t, categoria="A", telefonos=t_tels, email_prefs="BEN:Y;COB:Y;COM:N", consent_dp="Y", consent_com="Y"),
                      "ecc_sd": self.emit_sd_person(t, contracts=[("CR-T0014", "ZCRE", "A")], risk="001"), "phones": [x.split(":")[0] for x in t_tels]}
        # --- Calidad plantada (F2): documento faltante (cuarentena), teléfono inválido, DV de NIT errado, DIVIPOLA inexistente
        dq1, dq2, dq3 = P[15], P[16], P[17]
        cases["DQ"] = {"missing_doc": self.emit_sd_person(dq1, doc=None), "bad_phone": self.emit_sd_person(dq2, phone="123"),
                       "bad_divipola": self.emit_crm_person(dq3, categoria="A"), "bad_nit": self.emit_mm_org(O[3], bad_dv=True)}
        self.rows["crm_bp"][-1]["CITY1"] = "99999"
        self.manifest["counts"] = {k: len(v) for k, v in self.rows.items()}

    def write(self, out_dir: Path = DATA_DIR) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        for src, rows in self.rows.items():
            path = out_dir / f"{src}.csv"
            with path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader(); w.writerows(rows)
        for src, rows in self.delta_rows.items():   # corridas delta (caso S): <fuente>_delta.csv
            with (out_dir / f"{src}_delta.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(self.rows[src][0].keys()))
                w.writeheader(); w.writerows(rows)
        # RNE simulado (caso H) — solo números, sin persona
        with (out_dir / "rne_sample.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["numero"]); w.writerow([f"+57{self.manifest['cases']['H']['phone']}"])
            for _ in range(20):
                w.writerow([f"+573{self.rng.randint(0, 4)}{self.rng.randint(10_000_000, 99_999_999)}"])
        (out_dir / "manifest.json").write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.manifest


def generate(seed: int, out_dir: Path = DATA_DIR) -> dict:
    u = Universe(seed)
    u.build()
    return u.write(out_dir)
