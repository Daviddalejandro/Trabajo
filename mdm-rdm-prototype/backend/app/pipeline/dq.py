"""Etapa 5 · Calidad (SPEC §7): validaciones categorizadas por CAT_DQ_CATEGORY con severidad
BLOCKING / WARNING / INFO. Un registro con hallazgos BLOCKING va a DQ_QUARANTINE; el resto
continúa con sus hallazgos registrados."""
from __future__ import annotations

import re
from datetime import date

from app.pipeline.common import nit_check_digit
from app.pipeline.homologate import Homologator


def issue(category: str, field: str, severity: str, message: str, **detail) -> dict:
    return {"category": category, "field": field, "severity": severity, "detail": {"message": message, **detail}}


def run_dq(std: dict, hom: Homologator, unresolved: list[dict]) -> tuple[list[dict], bool]:
    issues: list[dict] = []
    blocking = False

    # Códigos sin homologar → VALIDITY (reprocesables con rehomologate, §7.2)
    for e in unresolved:
        issues.append(issue("VALIDITY", e["field"] or e["catalog"], "WARNING",
                            "Código fuente sin homologación: el campo queda en 0 = UNKNOWN",
                            system=hom.system, source_field=e["field"], source_value=e["raw"], catalog=e["catalog"],
                            issue_key=e["issue_key"]))

    # Completitud (BLOCKING)
    if std["party_type"] == "PERSON":
        per = std["person"]
        if not per.get("first_name") or not per.get("first_surname"):
            issues.append(issue("COMPLETENESS", "name", "BLOCKING", "Persona sin primer nombre o primer apellido")); blocking = True
        bd = per.get("birth_date")
        if bd and (bd > date.today() or (date.today() - bd).days > 120 * 365):
            issues.append(issue("VALIDITY", "birth_date", "WARNING", "Fecha de nacimiento fuera de rango; se descarta", value=str(bd)))
            per["birth_date"] = None
    else:
        if not std["org"].get("legal_name"):
            issues.append(issue("COMPLETENESS", "legal_name", "BLOCKING", "Organización sin razón social")); blocking = True
    if not std["identifiers"]:
        if std.get("identifier_required", True):
            issues.append(issue("COMPLETENESS", "identifier", "BLOCKING", "Sin documento de identidad")); blocking = True
        else:   # fuentes donde el documento no es obligatorio (registro digital): sigue, con hallazgo
            issues.append(issue("COMPLETENESS", "identifier", "WARNING", "Sin documento de identidad; matching solo por nombre, fecha y contacto"))

    # Documentos: regex del tipo (EAV) y dígito de verificación NIT
    for ident in std["identifiers"]:
        attrs = (ident["id_type"].get("attrs") or {})
        rx = attrs.get("validation_regex")
        if rx and not re.match(rx, ident["id_number"]):
            issues.append(issue("VALIDITY", "id_number", "WARNING", "Documento no cumple el formato del tipo",
                                id_type=ident["id_type"].get("code"), value=ident["id_number"]))
            ident["verified"] = False
        if ident["id_type"].get("code") == "NIT" and ident.get("dv") and ident["id_number"].isdigit():
            if str(nit_check_digit(ident["id_number"])) != ident["dv"]:
                issues.append(issue("VALIDITY", "nit_check_digit", "WARNING", "Dígito de verificación del NIT inválido",
                                    nit=ident["id_number"], dv=ident["dv"], expected=nit_check_digit(ident["id_number"])))
                ident["verified"] = False

    # Contactos: teléfono no E.164 se descarta
    kept = []
    for c in std["contacts"]:
        if c["channel"] == "PHONE" and not c.get("value"):
            issues.append(issue("VALIDITY", "phone", "WARNING", "Teléfono no normalizable a E.164; se descarta", raw=c.get("raw")))
            continue
        kept.append(c)
    std["contacts"] = kept

    # Segmentos: el valor debe ser hijo de su tipo (CAT_SEGMENT_TYPE jerárquico)
    kept = []
    for s in std["segments"]:
        seg = s["segment"]
        if seg.get("unknown"):
            continue   # ya reportado como código sin homologar
        if seg.get("parent") != s["segment_type"]:
            issues.append(issue("VALIDITY", "segment", "WARNING", "Segmento no pertenece a su tipo; se descarta",
                                segment_type=s["segment_type"], value=seg.get("code")))
            continue
        kept.append(s)
    std["segments"] = kept

    # Vínculos de servicio: solo PERSISTENT y coherente con su UES (regla dura §3.18)
    kept = []
    for e in std["enrollments"]:
        svc = e["service"]
        if svc.get("unknown"):
            continue
        if (svc.get("attrs") or {}).get("service_kind") != "PERSISTENT":
            issues.append(issue("VALIDITY", "service", "WARNING",
                                "Servicio transaccional no vinculable (regla dura 3.18): solo referencia RDM",
                                service=svc.get("code"), reference=e.get("reference")))
            continue
        e["business_unit_code"] = svc.get("parent")
        kept.append(e)
    std["enrollments"] = kept

    # Direcciones: DIVIPOLA inexistente
    for a in std["addresses"]:
        if a.get("divipola") and a["divipola"].get("unknown") and a["divipola"]["raw"]:
            pass  # reportado como código sin homologar (field None → catálogo directo)
    return issues, blocking
