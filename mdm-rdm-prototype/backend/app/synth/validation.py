"""Conjunto de validación (datos sintéticos, seed fija): un extracto SAP ECC (KNA1, mismo adaptador
`ecc_sd`) y un sistema de crédito / core de cartera (`credito_core`) con solapamiento controlado y
28 casos plantados V1–V28 cuyo desenlace verifica tests/test_validation_suite.py.

Escribe data/validation/ecc_kna1_validacion.csv, credito_core.csv, credito_core_delta.csv,
rne_validacion.csv y manifest_validacion.json. Documentos en rangos ficticios (9xxxxxxxx / 8xxxxxxxx)."""
from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

from app.synth.generator import REGIO_BY_CITY, nit_check_digit

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "validation"
CITIES = list(REGIO_BY_CITY)
TODAY = date(2026, 9, 14)


@dataclass
class VPerson:
    pid: int
    first: str
    middle: str
    sur1: str
    sur2: str
    gender: str
    birth: date
    doc_type: str
    doc: str
    email: str
    phone: str
    city: str
    street: str
    ids: dict = field(default_factory=dict)


@dataclass
class VOrg:
    oid: int
    legal: str
    nit: str
    dv: int
    city: str
    street: str
    ids: dict = field(default_factory=dict)


class ValidationSet:
    def __init__(self, seed: int = 20260914, n_common: int = 200, n_ecc_only: int = 60, n_credit_only: int = 40, n_orgs: int = 12):
        self.rng = random.Random(seed)
        self.fake = Faker("es_CO"); Faker.seed(seed)
        self.seed = seed
        self._docs: set[str] = set()
        self.ecc: list[dict] = []
        self.credit: list[dict] = []
        self.credit_delta: list[dict] = []
        self.rne: list[str] = []
        self.manifest: dict = {"seed": seed, "cases": {}, "counts": {}}
        self._kunnr = 400000
        self._cli = 100000
        self._obl = 70000
        self.common = [self._person(i) for i in range(n_common)]
        self.ecc_only = [self._person(1000 + i) for i in range(n_ecc_only)]
        self.credit_only = [self._person(2000 + i) for i in range(n_credit_only)]
        self.orgs = [self._org(i) for i in range(n_orgs)]

    # ------------------------------------------------------------------ fábricas
    def _doc(self) -> str:
        while True:
            d = f"9{self.rng.randint(10_000_000, 99_999_999)}"
            if d not in self._docs:
                self._docs.add(d); return d

    def _person(self, i: int, minor: bool = False) -> VPerson:
        g = self.rng.choice(["M", "F"])
        first = self.fake.first_name_male() if g == "M" else self.fake.first_name_female()
        middle = (self.fake.first_name_male() if g == "M" else self.fake.first_name_female()) if self.rng.random() < 0.55 else ""
        years = self.rng.randint(6, 17) if minor else self.rng.randint(19, 80)
        birth = TODAY - timedelta(days=years * 365 + self.rng.randint(0, 364))
        return VPerson(pid=i, first=first, middle=middle, sur1=self.fake.last_name(), sur2=self.fake.last_name(), gender=g, birth=birth,
                       doc_type="TI" if minor else self.rng.choices(["CC", "CE", "PAS"], [0.92, 0.05, 0.03])[0], doc=self._doc(),
                       email=f"{first}.{self.fake.last_name()}{i}@validacion.test".lower().replace(" ", ""),
                       phone=f"3{self.rng.randint(0, 4)}{self.rng.randint(10_000_000, 99_999_999)}", city=self.rng.choice(CITIES), street=self.fake.street_address())

    def _org(self, i: int) -> VOrg:
        base = self.fake.company().replace(",", "")
        nit = f"8{self.rng.randint(10_000_000, 99_999_999)}"
        return VOrg(oid=i, legal=f"{base} S.A.S.", nit=nit, dv=nit_check_digit(nit), city=self.rng.choice(CITIES), street=self.fake.street_address())

    def _new_kunnr(self) -> str:
        self._kunnr += 1; return f"{self._kunnr:010d}"

    def _new_cli(self) -> str:
        self._cli += 1; return f"CL{self._cli:07d}"

    def _new_obl(self) -> str:
        self._obl += 1; return f"OB-{self._obl}"

    # ------------------------------------------------------------------ emisores
    def emit_ecc_person(self, p: VPerson, contracts: list[tuple[str, str, str]] | None = None, risk: str = "", name1: str | None = None,
                        doc: str | None = "keep", phone: str | None = None, email: str | None = None,
                        bprol: str = "ZAFI", categoria: str = "", beneficiario_de: str = "") -> str:
        kid = self._new_kunnr(); p.ids["ecc"] = kid
        contracts = contracts if contracts is not None else [(f"CT-{kid[-5:]}", self.rng.choice(["ZSAL", "ZCRE"]), "A")]
        self.ecc.append({"KUNNR": kid, "KTOKD": "ZPER", "STKZN": "X", "NAME1": name1 or f"{p.first} {p.middle}".strip(), "NAME2": f"{p.sur1} {p.sur2}",
                         "STCD1": "", "STCD2": p.doc if doc == "keep" else (doc or ""), "GBDAT": p.birth.isoformat(), "LAND1": "CO",
                         "REGIO": REGIO_BY_CITY[p.city], "ORT01": p.city, "STRAS": p.street, "TELF1": phone if phone is not None else p.phone,
                         "SMTP_ADDR": (email or p.email).upper(), "CTLPC": risk,
                         "ZZ_CONTRATOS": ";".join(f"{r}:{s}:{st}" for r, s, st in contracts), "ZZ_SERVICIOS": "", "LOEVM": "",
                         "BPROL": bprol, "ZZ_CATEGORIA": categoria, "ZZ_BENEFICIARIO_DE": beneficiario_de,
                         "ERDAT": "2023-02-01", "AEDAT": "2026-09-01"})
        return kid

    def emit_ecc_org(self, o: VOrg, legal: str | None = None) -> str:
        kid = self._new_kunnr(); o.ids["ecc"] = kid
        self.ecc.append({"KUNNR": kid, "KTOKD": "ZORG", "STKZN": "", "NAME1": legal or o.legal, "NAME2": o.legal.split(" S.A.S.")[0].upper(),
                         "STCD1": f"{o.nit}-{o.dv}", "STCD2": "", "GBDAT": "", "LAND1": "CO", "REGIO": REGIO_BY_CITY[o.city], "ORT01": o.city,
                         "STRAS": o.street, "TELF1": f"601{self.rng.randint(1_000_000, 9_999_999)}", "SMTP_ADDR": f"contacto@{o.legal.split()[0].lower()}.test",
                         "CTLPC": "", "ZZ_CONTRATOS": f"CT-{kid[-5:]}:ZSAL:A", "ZZ_SERVICIOS": "", "LOEVM": "",
                         "BPROL": "ZEMP", "ZZ_CATEGORIA": "", "ZZ_BENEFICIARIO_DE": "", "ERDAT": "2022-06-01", "AEDAT": "2026-09-01"})
        return kid

    def emit_credit(self, p: VPerson, obligations: list[tuple[str, str, str, str]] | None = None, calif: str = "A", alternos: list[str] | None = None,
                    aut_tra: str = "S", aut_com: str = "S", aut_cen: str = "S", fallecido: str = "N", codeudor: str = "", tipo_id: str | None = None,
                    num_id: str | None = "keep", nombres: str | None = None, email: str | None = None, celular: str | None = None,
                    birth: date | None = None, target: list[dict] | None = None) -> str:
        cid = self._new_cli(); p.ids.setdefault("credit", cid)
        obl = obligations if obligations is not None else [(self._new_obl(), "CS", "VIG", "2024-03-15", "")]
        tid = tipo_id or {"CC": "C", "CE": "E", "TI": "T", "PAS": "P"}[p.doc_type]
        row = {"ID_CLIENTE": cid, "TIPO_ID": tid, "NUM_ID": p.doc if num_id == "keep" else (num_id or ""), "NOMBRES": nombres or f"{p.first} {p.middle}".strip(),
               "APELLIDOS": f"{p.sur1} {p.sur2}", "SEXO": "H" if p.gender == "M" else "M", "FECHA_NAC": (birth or p.birth).strftime("%d/%m/%Y"),
               "CIUDAD": p.city, "DIRECCION": p.street, "EMAIL": email if email is not None else p.email, "CELULAR": celular if celular is not None else p.phone,
               "TEL_ALTERNOS": ";".join(alternos or []), "OBLIGACIONES": ";".join(":".join(x) for x in obl), "CALIFICACION": calif,
               "AUT_TRATAMIENTO": aut_tra, "AUT_COMERCIAL": aut_com, "AUT_CENTRALES": aut_cen, "FALLECIDO": fallecido, "CODEUDOR_ID": codeudor,
               "RAZON_SOCIAL": "", "FECHA_ACT": "2026-09-10"}
        (target if target is not None else self.credit).append(row)
        return cid

    def emit_credit_org(self, o: VOrg) -> str:
        cid = self._new_cli(); o.ids["credit"] = cid
        self.credit.append({"ID_CLIENTE": cid, "TIPO_ID": "N", "NUM_ID": f"{o.nit}-{o.dv}", "NOMBRES": "", "APELLIDOS": "", "SEXO": "", "FECHA_NAC": "",
                            "CIUDAD": o.city, "DIRECCION": o.street, "EMAIL": f"pagos@{o.legal.split()[0].lower()}.test", "CELULAR": f"601{self.rng.randint(1_000_000, 9_999_999)}",
                            "TEL_ALTERNOS": "", "OBLIGACIONES": f"{self._new_obl()}:CS:VIG:2024-01-10:", "CALIFICACION": "B", "AUT_TRATAMIENTO": "S", "AUT_COMERCIAL": "N",
                            "AUT_CENTRALES": "S", "FALLECIDO": "N", "CODEUDOR_ID": "", "RAZON_SOCIAL": o.legal.upper(), "FECHA_ACT": "2026-09-10"})
        return cid

    # ------------------------------------------------------------------ construcción
    def build(self) -> None:
        C = self.manifest["cases"]; rng = self.rng
        P = self.common
        # población base común: ECC + crédito con variaciones leves de captura
        for p in P[30:]:
            self.emit_ecc_person(p, risk=rng.choice(["", "001", "002"]), categoria=rng.choice(["A", "A", "B", "C"]))
            self.emit_credit(p, calif=rng.choice("ABC"), aut_com=rng.choice(["S", "S", "N"]),
                             nombres=(f"{p.first} {p.middle}".strip()).upper() if rng.random() < 0.3 else None,
                             obligations=[(self._new_obl(), rng.choice(["CS", "TC"]), rng.choice(["VIG", "VIG", "MOR", "CAN"]), "2023-05-02", "2025-12-31")])
        for p in self.ecc_only:   # solo en ECC: la mayoría afiliados, una parte proveedores de servicios
            self.emit_ecc_person(p, bprol=rng.choice(["ZAFI", "ZAFI", "ZAFI", "ZPRO"]), categoria=rng.choice(["A", "B", "C", ""]))
        for p in self.credit_only:
            self.emit_credit(p, calif=rng.choice("ABCDE"))
        for o in self.orgs[2:]:
            self.emit_ecc_org(o)
        # V1 · auto-merge: mismo documento, nombre con error tipográfico en crédito
        p = P[0]; C["V1"] = {"ecc": self.emit_ecc_person(p, contracts=[("CT-V1", "ZSAL", "A")]),
                             "credit": self.emit_credit(p, nombres=(p.first[:-1] + "h " + p.middle).strip()), "doc": p.doc}
        # V2 · probable: crédito con documento distinto (tarjeta de identidad antigua: tipos no comparables), mismo nombre, fecha y
        #     email; celular distinto → grupo G3 = PROBABLE (con el mismo celular sería G4 = AUTO)
        p = P[1]; C["V2"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(p, tipo_id="T", num_id=self._doc(), celular=f"30{self.rng.randint(10_000_000, 99_999_999)}")}
        # V3 · posible: homónimos con la misma fecha de nacimiento y documentos distintos, sin contacto común
        p = P[2]; h = self._person(9003); h.first, h.middle, h.sur1, h.sur2, h.birth, h.gender, h.city = p.first, p.middle, p.sur1, p.sur2, p.birth, p.gender, p.city
        C["V3"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(h)}
        # V4 · duplicado dentro del sistema de crédito: dos clientes con el mismo documento
        p = P[3]; c1 = self.emit_credit(p, obligations=[(self._new_obl(), "CS", "VIG", "2022-01-01", "")])
        c2 = self.emit_credit(p, obligations=[(self._new_obl(), "TC", "MOR", "2023-06-01", "")], email=p.email.replace("@", "2@"))
        C["V4"] = {"credit_1": c1, "credit_2": c2, "ecc": self.emit_ecc_person(p), "doc": p.doc}
        # V5 · organización: cliente jurídico con el mismo NIT en ECC y crédito
        o = self.orgs[0]; C["V5"] = {"ecc": self.emit_ecc_org(o, legal=o.legal.upper()), "credit": self.emit_credit_org(o), "nit": o.nit}
        # V6 · fallecido con obligación vigente
        p = P[4]; C["V6"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(p, fallecido="S")}
        # V7 · autorización comercial negada, obligación vigente
        p = P[5]; C["V7"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(p, aut_com="N")}
        # V8 · solo obligaciones canceladas hace 11 años: sin obligación vigente y retención vencida (candidato a purga)
        p = P[6]; C["V8"] = {"credit": self.emit_credit(p, obligations=[(self._new_obl(), "CS", "CAN", "2012-01-10", "2015-06-30")]), "doc": p.doc}
        # V9 · moroso (MOR → SUSPENDED): la cobranza sigue siendo legítima
        p = P[7]; C["V9"] = {"ecc": self.emit_ecc_person(p, contracts=[("CT-V9", "ZSAL", "A")]), "credit": self.emit_credit(p, obligations=[(self._new_obl(), "CS", "MOR", "2024-02-01", "")], calif="D")}
        # V10 · teléfonos de gestión: titular no confirmado, referencia y número errado
        p = P[8]; tels = [f"31{rng.randint(10_000_000, 99_999_999)}:TIT:NOCONF", f"32{rng.randint(10_000_000, 99_999_999)}:REF:NOCONF", f"30{rng.randint(10_000_000, 99_999_999)}:TIT:ERR"]
        C["V10"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(p, alternos=tels), "phones": [p.phone] + [t.split(":")[0] for t in tels]}
        # V11 · RNE: el celular del titular está en el registro
        p = P[9]; C["V11"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(p, aut_com="S"), "phone": p.phone}; self.rne.append(f"+57{p.phone}")
        # V12 · calidad: crédito sin documento (cuarentena), ECC con teléfono inválido (advertencia), producto LB sin homologar
        p = P[10]; C["V12"] = {"credit_missing_doc": self.emit_credit(p, num_id=None), "ecc_bad_phone": self.emit_ecc_person(P[11], phone="12"),
                               "credit_unknown_product": self.emit_credit(P[12], obligations=[(self._new_obl(), "LB", "VIG", "2025-01-01", "")]), "unknown_product_doc": P[12].doc}
        self.emit_ecc_person(P[12])
        # V13 · delta: el sistema de crédito informa un correo nuevo (MOST_RECENT) para un cliente ya cargado
        p = P[13]; C["V13"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(p), "new_email": f"nuevo.{p.email}"}
        self.emit_credit(p, email=C["V13"]["new_email"], target=self.credit_delta)
        self.credit_delta[-1]["ID_CLIENTE"] = C["V13"]["credit"]
        # V14 · codeudor: relación GUARANTEED_BY / GUARANTOR_OF entre dos clientes de crédito
        p, g = P[14], P[15]; cg = self.emit_credit(g, obligations=[]); C["V14"] = {"deudor": self.emit_credit(p, codeudor=cg), "codeudor": cg}
        self.emit_ecc_person(p); self.emit_ecc_person(g)
        # V15 · ARCO cancelación sobre cliente con obligación vigente (se ejecuta en la suite)
        p = P[16]; C["V15"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(p)}
        # V16 · audiencia de cobranza por servicio (se consulta en la suite) · V17 · match-preview con solicitante nuevo
        p = P[17]; C["V16"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(p, obligations=[(self._new_obl(), "CS", "VIG", "2025-03-01", "")])}
        C["V17"] = {"uses": "V1"}
        # V18 · stewardship: probable entre ECC y crédito (documento con dígito transpuesto), decidido por owners
        p = P[18]; swapped = p.doc[:-2] + p.doc[-1] + p.doc[-2]
        if swapped == p.doc:
            swapped = p.doc[:-1] + str((int(p.doc[-1]) + 1) % 10)
        C["V18"] = {"ecc": self.emit_ecc_person(p), "credit": self.emit_credit(p, num_id=swapped)}
        # V19 · survivorship: nombre desde ECC (prioridad), email más reciente desde crédito
        p = P[19]; C["V19"] = {"ecc": self.emit_ecc_person(p, name1=f"{p.first} {p.middle}".strip()), "credit": self.emit_credit(p, nombres=p.first.upper(), email=f"reciente.{p.email}")}
        # V20–V25 · feed, export, vista 360, idempotencia, crosswalk y auditoría se verifican sobre V1/V9
        p = P[20]; C["V22"] = {"ecc": self.emit_ecc_person(p, contracts=[("CT-V22", "ZSAL", "A")], risk="001"),
                               "credit": self.emit_credit(p, obligations=[(self._new_obl(), "CS", "VIG", "2024-08-01", ""), (self._new_obl(), "TC", "CAN", "2021-01-01", "2023-01-01")], calif="D")}
        # V26 · beneficiario: BPROL=ZBEN, sub-rol AFFILIATE_BENEFICIARY y relación BENEFICIARY_OF con el titular
        tit, ben = P[21], P[22]
        kid_tit = self.emit_ecc_person(tit, categoria="A")
        C["V26"] = {"titular_ecc": kid_tit, "beneficiario_ecc": self.emit_ecc_person(ben, bprol="ZBEN", categoria="A", beneficiario_de=kid_tit),
                    "credit": self.emit_credit(tit)}
        # V27 · doble rol en la misma fuente (BUT100 multivalor): afiliado y proveedor de servicios
        p = P[23]; C["V27"] = {"ecc": self.emit_ecc_person(p, bprol="ZAFI;ZPRO", categoria="B"), "credit": self.emit_credit(p)}
        # V28 · BPROL sin homologar: el rol queda UNKNOWN y se corrige con rehomologar (§7.2)
        p = P[24]; C["V28"] = {"ecc": self.emit_ecc_person(p, bprol="ZXXX"), "source_value": "ZXXX"}
        for i in range(20):   # ruido del RNE
            self.rne.append(f"+573{rng.randint(0, 4)}{rng.randint(10_000_000, 99_999_999)}")
        self.manifest["counts"] = {"ecc_kna1_validacion": len(self.ecc), "credito_core": len(self.credit), "credito_core_delta": len(self.credit_delta), "rne": len(self.rne)}

    def write(self, out_dir: Path = DATA_DIR) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, rows in [("ecc_kna1_validacion", self.ecc), ("credito_core", self.credit), ("credito_core_delta", self.credit_delta)]:
            with (out_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        with (out_dir / "rne_validacion.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["numero"]); w.writerows([[x] for x in self.rne])
        (out_dir / "manifest_validacion.json").write_text(json.dumps(self.manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        return self.manifest


def generate(seed: int = 20260914, out_dir: Path = DATA_DIR) -> dict:
    v = ValidationSet(seed)
    v.build()
    return v.write(out_dir)
