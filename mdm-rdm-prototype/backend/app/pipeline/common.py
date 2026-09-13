"""Estandarización (SPEC §7 etapa 3, regla dura §3.8): limpieza sin tocar códigos.
Helpers compartidos por los adaptadores de fuente."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date, datetime

import phonenumbers
from nameparser import HumanName

MULTI_SEP = ";"


def nfc(s: str | None) -> str:
    return unicodedata.normalize("NFC", (s or "").strip())


def clean(s: str | None) -> str | None:
    """TRIM + NFC + espacios múltiples colapsados. Vacío → None."""
    v = re.sub(r"\s+", " ", nfc(s))
    return v or None


def title(s: str | None) -> str | None:
    v = clean(s)
    return v.title() if v else None


def normalized_key(s: str | None) -> str | None:
    """Mayúsculas sin acentos ni puntuación, para comparación y blocking."""
    v = clean(s)
    if not v:
        return None
    v = unicodedata.normalize("NFD", v)
    v = "".join(ch for ch in v if unicodedata.category(ch) != "Mn")
    v = re.sub(r"[^A-Za-z0-9 ]+", " ", v)
    return re.sub(r"\s+", " ", v).strip().upper() or None


def strip_titles(s: str | None) -> str | None:
    """nameparser para retirar tratamientos (Dr., Sra., Ing.) antes de dividir nombres."""
    v = clean(s)
    if not v:
        return None
    hn = HumanName(v)
    parts = " ".join(p for p in [hn.first, hn.middle, hn.last] if p)
    return clean(parts) or v


def split_given(s: str | None) -> tuple[str | None, str | None]:
    v = strip_titles(s)
    if not v:
        return None, None
    parts = v.split(" ")
    return title(parts[0]), title(" ".join(parts[1:])) if len(parts) > 1 else None


def split_surnames(s: str | None) -> tuple[str | None, str | None]:
    v = clean(s)
    if not v:
        return None, None
    parts = v.split(" ")
    return title(parts[0]), title(" ".join(parts[1:])) if len(parts) > 1 else None


def e164(phone: str | None, region: str = "CO") -> str | None:
    v = clean(phone)
    if not v:
        return None
    try:
        num = phonenumbers.parse(v, region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_possible_number(num):
        return None
    return phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)


def email_norm(s: str | None) -> str | None:
    v = clean(s)
    if not v:
        return None
    v = v.lower()
    return v if re.match(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", v) else None


def address_norm(s: str | None) -> str | None:
    v = clean(s)
    if not v:
        return None
    v = re.sub(r"\.(?=\S)", ". ", v)
    repl = {"CL.": "CALLE", "CL ": "CALLE ", "CRA.": "CARRERA", "CRA ": "CARRERA ", "KR ": "CARRERA ",
            "AV.": "AVENIDA", "AV ": "AVENIDA ", "DG.": "DIAGONAL", "TV.": "TRANSVERSAL", "#": "No."}
    up = v.upper()
    for k, r in repl.items():
        up = up.replace(k, r)
    return re.sub(r"\s+", " ", up).strip()


def parse_date(s: str | None) -> date | None:
    v = clean(s)
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(v[:19] if "T" in fmt else v, fmt).date()
        except ValueError:
            continue
    return None


def split_multi(s: str | None) -> list[str]:
    """1NF (regla dura §3.6): un campo multivaluado de la fuente se abre en una lista."""
    return [p.strip() for p in (s or "").split(MULTI_SEP) if p.strip()]


def sha256(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def contact_hash(channel: str, value: str) -> str:
    return hashlib.sha256(f"{channel}|{value}".encode()).hexdigest()


def nit_check_digit(nit: str) -> int:
    weights = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    total = sum(int(d) * w for d, w in zip(reversed(nit), weights))
    r = total % 11
    return r if r < 2 else 11 - r


def split_nit(raw: str | None) -> tuple[str | None, str | None]:
    """'800123456-7' → ('800123456', '7'); sin DV → (nit, None)."""
    v = clean(raw)
    if not v:
        return None, None
    v = v.replace(".", "").replace(" ", "")
    if "-" in v:
        n, dv = v.split("-", 1)
        return n, dv
    return v, None


# ---------------------------------------------------------------- entradas de código
def code(field: str, raw: str | None, catalog: str) -> dict | None:
    """Código fuente a homologar vía SOURCE_VALUE_MAPPING (sistema, campo, valor)."""
    v = clean(raw)
    return {"field": field, "raw": v, "catalog": catalog} if v else None


def direct(canonical: str, catalog: str) -> dict:
    """Código ya canónico (resuelto por CATALOG_CODE + VALUE_CODE, regla dura §3.4)."""
    return {"field": None, "raw": canonical, "catalog": catalog}


def new_std(party_type: str) -> dict:
    return {"party_type": party_type, "status": None, "person": {}, "org": {}, "identifiers": [], "names": [],
            "roles": [], "segments": [], "enrollments": [], "contacts": [], "addresses": [], "consents": [],
            "prefs": [], "relationships": [], "group": None}


def consent(consent_type: str, granted: bool | None) -> dict | None:
    if granted is None:
        return None
    return {"consent_type": direct(consent_type, "CAT_CONSENT_TYPE"),
            "status": direct("GRANTED" if granted else "DENIED", "CAT_CONSENT_STATUS")}


def yn(v: str | None) -> bool | None:
    s = (v or "").strip().lower()
    if s in {"y", "x", "true", "1", "si", "sí"}:
        return True
    if s in {"n", "false", "0", "no"}:
        return False
    return None
