"""Etapas 6 y 7 · Crosswalk y carga (SPEC §7). En F2 el crosswalk resuelve por XREF:
hit → actualización directa del party vinculado (regla dura §3.11); miss → el registro
se crea como party CANDIDATE con su XREF (el matching de F3 decide merges y promueve a
GOLDEN). Toda fila de hechos lleva linaje (regla dura §3.14) y toda escritura audita por
trigger en PARTY_AUDIT_LOG con el contexto de sesión (actor, batch, fuente)."""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.pipeline.common import address_hash, contact_hash
from app.pipeline.homologate import Homologator

RETENTION_BY_UES = {"CREDITO": "FINANCIAL_10Y", "SALUD": "HEALTH_20Y", "SUBSIDIO": "AFFILIATE_5Y"}
SOURCE_SLICE_TABLES = ["party_role", "party_segment", "party_identifier", "party_name", "party_address", "party_consent"]


def _sk(entry: dict | None, default: int = 0) -> int:
    return entry["sk"] if entry else default


def _code(entry: dict | None) -> str | None:
    """Código canónico de una entrada homologada (o el valor crudo si quedó UNKNOWN)."""
    return (entry.get("code") or entry.get("raw")) if entry else None


class Loader:
    def __init__(self, session: Session, hom: Homologator, source_sk: int, batch_id: int):
        self.s, self.hom, self.src, self.batch = session, hom, source_sk, batch_id
        self.targets: dict[str, dict] = {}
        self.deferred_rel: list[tuple[int, str, dict]] = []
        self.deferred_grp: list[tuple[int, dict]] = []
        self.issues: list[dict] = []
        c = lambda cat, code: hom.sk(cat, code)  # noqa: E731
        self.K = {
            "PERSON": c("CAT_PARTY_TYPE", "PERSON"), "ORGANIZATION": c("CAT_PARTY_TYPE", "ORGANIZATION"),
            "CANDIDATE": c("CAT_GOLDEN_STATUS", "CANDIDATE"), "GOLDEN": c("CAT_GOLDEN_STATUS", "GOLDEN"),
            "ACTIVE": c("CAT_PARTY_STATUS", "ACTIVE"), "DECEASED": c("CAT_PARTY_STATUS", "DECEASED"),
            "LEGAL": c("CAT_NAME_TYPE", "LEGAL"), "TRADE": c("CAT_NAME_TYPE", "TRADE"),
            "OWNER": c("CAT_CONTACT_USAGE_ROLE", "OWNER"), "CONFIRMED_BY_TITULAR": c("CAT_CONTACT_CONFIRMATION", "CONFIRMED_BY_TITULAR"),
            "TITULAR": c("CAT_PREF_ORIGIN", "TITULAR"), "ANY": c("CAT_CONTACT_FREQUENCY", "ANY"),
            "GEO_PENDING": c("CAT_GEOCODING_STATUS", "PENDING"), "CLOSED": c("CAT_ENROLLMENT_STATUS", "CLOSED"),
            "FAMILY": c("CAT_GROUP_TYPE", "FAMILY"), "CORPORATE_GROUP": c("CAT_GROUP_TYPE", "CORPORATE_GROUP"),
        }
        self.channel = {code: v["sk"] for code, v in hom.catalogs["CAT_CONTACT_CHANNEL"].items()}
        self.purpose = {code: v["sk"] for code, v in hom.catalogs["CAT_CONTACT_PURPOSE"].items()}
        self.member_role = {code: v["sk"] for code, v in hom.catalogs["CAT_GROUP_MEMBER_ROLE"].items()}
        self.retention = {code: v for code, v in hom.catalogs["CAT_RETENTION_RULE"].items()}
        self.reltypes = {r[0]: r for r in session.execute(text(
            "SELECT value_code, value_sk, from_party_type, to_party_type, inverse_code FROM rdm.vw_rdm_cat_relationship_type WHERE is_active")).all()}

    # ------------------------------------------------------------------ utilidades
    def q(self, sql: str, **p):
        return self.s.execute(text(sql), p)

    def _ins(self, table: str, pk: str, cols: dict, entries: dict[str, dict] | None = None, on_conflict: str = "") -> int | None:
        names = ", ".join(cols)
        binds = ", ".join(f":{k}" for k in cols)
        row = self.q(f"INSERT INTO mdm.{table} ({names}) VALUES ({binds}) {on_conflict} RETURNING {pk}", **cols).first()
        if row is None:
            return None
        for col, entry in (entries or {}).items():
            if entry and entry.get("unknown"):
                self.targets[entry["issue_key"]] = {"target_table": table, "target_pk": pk, "target_sk": row[0], "target_column": col,
                                                    "party_sk": cols.get("party_sk")}
        return row[0]

    def dq(self, party_sk: int | None, staging_ref: str, category: str, field: str, severity: str, message: str, **detail):
        self.issues.append({"party_sk": party_sk, "staging_ref": staging_ref, "category": category, "field": field,
                            "severity": severity, "detail": {"message": message, **detail}})

    # ------------------------------------------------------------------ carga de un registro
    def load(self, external_id: str, std: dict, source_hash: str, staging_ref: str) -> tuple[int, bool]:
        hit = self.q("SELECT party_sk FROM mdm.xref_party_source WHERE source_system_cd=:s AND external_id=:e",
                     s=self.src, e=external_id).scalar()
        status_sk = _sk(std.get("status"), self.K["ACTIVE"]) or self.K["ACTIVE"]
        ptype = self.K[std["party_type"]]
        if hit is None:
            party_sk = self._ins("party", "party_sk", {"party_type_cd": ptype, "golden_status_cd": self.K["CANDIDATE"],
                                                       "party_status_cd": status_sk}, {"party_status_cd": std.get("status")})
            self._ins("xref_party_source", "xref_sk", {"party_sk": party_sk, "source_system_cd": self.src,
                                                       "external_id": external_id, "source_hash": source_hash})
            created = True
        else:
            party_sk = hit
            self.q("UPDATE mdm.xref_party_source SET source_hash=:h, last_seen_at=now() WHERE source_system_cd=:s AND external_id=:e",
                   h=source_hash, s=self.src, e=external_id)
            # DECEASED prevalece sobre cualquier estado (principio de veracidad, Ley 1581/2012 art. 4 lit. d)
            self.q("UPDATE mdm.party SET party_status_cd = CASE WHEN party_status_cd=:d THEN :d ELSE :st END, updated_at=now() WHERE party_sk=:p",
                   d=self.K["DECEASED"], st=status_sk, p=party_sk)
            self._delete_source_slice(party_sk)
            created = False
        self._core(party_sk, std, created)
        self._identifiers(party_sk, std)
        self._names(party_sk, std)
        roles = self._roles(party_sk, std)
        self._segments(party_sk, std)
        self._enrollments(party_sk, std, roles)
        self._contacts(party_sk, std)
        self._addresses(party_sk, std)
        self._consents_prefs(party_sk, std)
        for r in std["relationships"]:
            self.deferred_rel.append((party_sk, staging_ref, r))
        if std.get("group"):
            self.deferred_grp.append((party_sk, std["group"]))
        self._completeness(party_sk, std)
        return party_sk, created

    def _delete_source_slice(self, party_sk: int) -> None:
        self.q("DELETE FROM mdm.party_contact_pref WHERE party_contact_sk IN "
               "(SELECT party_contact_sk FROM mdm.party_contact_point WHERE party_sk=:p AND source_system_cd=:s)", p=party_sk, s=self.src)
        self.q("DELETE FROM mdm.party_contact_eligibility_cache WHERE party_contact_sk IN "
               "(SELECT party_contact_sk FROM mdm.party_contact_point WHERE party_sk=:p AND source_system_cd=:s)", p=party_sk, s=self.src)
        self.q("DELETE FROM mdm.party_contact_point WHERE party_sk=:p AND source_system_cd=:s", p=party_sk, s=self.src)
        self.q("DELETE FROM mdm.party_data_retention WHERE entity='PARTY_SERVICE_ENROLLMENT' AND entity_sk IN "
               "(SELECT enrollment_sk FROM mdm.party_service_enrollment WHERE party_sk=:p AND source_system_cd=:s)", p=party_sk, s=self.src)
        self.q("DELETE FROM mdm.party_service_enrollment WHERE party_sk=:p AND source_system_cd=:s", p=party_sk, s=self.src)
        self.q("DELETE FROM mdm.party_relationship WHERE from_party_sk=:p AND source_system_cd=:s", p=party_sk, s=self.src)
        for t in SOURCE_SLICE_TABLES:
            self.q(f"DELETE FROM mdm.{t} WHERE party_sk=:p AND source_system_cd=:s", p=party_sk, s=self.src)

    def _core(self, party_sk: int, std: dict, created: bool) -> None:
        golden = self.q("SELECT golden_status_cd FROM mdm.party WHERE party_sk=:p", p=party_sk).scalar_one()
        owns_core = created or golden == self.K["CANDIDATE"]   # en GOLDEN decide survivorship (F3)
        if std["party_type"] == "PERSON":
            per = std["person"]
            full = " ".join(x for x in [per.get("first_name"), per.get("middle_name"), per.get("first_surname"), per.get("second_surname")] if x)
            from app.pipeline.common import normalized_key
            cols = {"party_sk": party_sk, "first_name": per.get("first_name"), "middle_name": per.get("middle_name"),
                    "first_surname": per.get("first_surname"), "second_surname": per.get("second_surname"),
                    "birth_date": per.get("birth_date"), "death_date": per.get("death_date"), "gender_cd": _sk(per.get("gender")),
                    "full_name_normalized": normalized_key(full)}
            if created:
                self._ins("party_person", "party_sk", cols, {"gender_cd": per.get("gender")})
            elif owns_core:
                self.q("UPDATE mdm.party_person SET first_name=:first_name, middle_name=:middle_name, first_surname=:first_surname, "
                       "second_surname=:second_surname, birth_date=COALESCE(:birth_date, birth_date), gender_cd=CASE WHEN :gender_cd>0 THEN :gender_cd ELSE gender_cd END, "
                       "full_name_normalized=:full_name_normalized WHERE party_sk=:party_sk", **cols)
        else:
            org = std["org"]
            from app.pipeline.common import normalized_key
            cols = {"party_sk": party_sk, "legal_name": org.get("legal_name"), "trade_name": org.get("trade_name"),
                    "legal_name_normalized": normalized_key(org.get("legal_name")), "ciiu_cd": _sk(org.get("ciiu")), "org_type_cd": _sk(org.get("org_type"))}
            if created:
                self._ins("party_org", "party_sk", cols, {"ciiu_cd": org.get("ciiu"), "org_type_cd": org.get("org_type")})
            elif owns_core:
                self.q("UPDATE mdm.party_org SET legal_name=:legal_name, trade_name=:trade_name, legal_name_normalized=:legal_name_normalized, "
                       "ciiu_cd=CASE WHEN :ciiu_cd>0 THEN :ciiu_cd ELSE ciiu_cd END, org_type_cd=CASE WHEN :org_type_cd>0 THEN :org_type_cd ELSE org_type_cd END "
                       "WHERE party_sk=:party_sk", **cols)

    def _identifiers(self, party_sk: int, std: dict) -> None:
        for i in std["identifiers"]:
            self._ins("party_identifier", "identifier_sk",
                      {"party_sk": party_sk, "id_type_cd": _sk(i["id_type"]), "id_number": i["id_number"],
                       "verification_source_cd": _sk(i.get("verification")), "is_verified": bool(i.get("verified")),
                       "verified_at": None, "source_system_cd": self.src},
                      {"id_type_cd": i["id_type"]}, "ON CONFLICT (party_sk, id_type_cd, id_number) DO UPDATE SET captured_at=now()")

    def _names(self, party_sk: int, std: dict) -> None:
        if std["party_type"] == "PERSON":
            per = std["person"]
            full = " ".join(x for x in [per.get("first_name"), per.get("middle_name"), per.get("first_surname"), per.get("second_surname")] if x)
            names = [(self.K["LEGAL"], full)]
        else:
            names = [(self.K["LEGAL"], std["org"].get("legal_name"))]
            if std["org"].get("trade_name"):
                names.append((self.K["TRADE"], std["org"]["trade_name"]))
        for t, v in names:
            if v:
                self._ins("party_name", "party_name_sk", {"party_sk": party_sk, "name_type_cd": t, "name_value": v, "source_system_cd": self.src})

    def _roles(self, party_sk: int, std: dict) -> list[tuple[int, int]]:
        out = []
        for r in std["roles"]:
            bu = _sk(r.get("business_unit"), -1) if r.get("business_unit") else -1
            sk = self._ins("party_role", "party_role_sk",
                           {"party_sk": party_sk, "role_cd": _sk(r["role"]), "sub_role_cd": _sk(r.get("sub_role")),
                            "business_unit_cd": bu, "valid_from": r.get("valid_from") or date.today(), "source_system_cd": self.src},
                           {"role_cd": r["role"], "sub_role_cd": r.get("sub_role"), "business_unit_cd": r.get("business_unit")},
                           "ON CONFLICT (party_sk, role_cd, business_unit_cd, source_system_cd, valid_from) DO UPDATE SET captured_at=now()")
            out.append((sk, bu))
        return out

    def _segments(self, party_sk: int, std: dict) -> None:
        for s in std["segments"]:
            type_info = self.hom.info("CAT_SEGMENT_TYPE", s["segment_type"])
            type_sk, seg = type_info["sk"], s["segment"]
            cur = self.q("SELECT party_segment_sk, segment_cd, source_system_cd FROM mdm.party_segment WHERE party_sk=:p AND segment_type_cd=:t AND valid_to IS NULL",
                         p=party_sk, t=type_sk).first()
            if cur and cur.segment_cd == seg["sk"]:
                continue
            if cur:
                auth = (type_info["attrs"] or {}).get("authoritative_source")
                cur_src = self.q("SELECT source_system_cd FROM rdm.source_system WHERE source_system_sk=:s", s=cur.source_system_cd).scalar()
                if auth and cur_src == auth and self.hom.system != auth:
                    continue   # la fuente autoritativa del tipo conserva el segmento (SPEC §9)
                self.q("UPDATE mdm.party_segment SET valid_to=CURRENT_DATE WHERE party_segment_sk=:k", k=cur.party_segment_sk)
            self._ins("party_segment", "party_segment_sk",
                      {"party_sk": party_sk, "segment_type_cd": type_sk, "segment_cd": seg["sk"], "source_system_cd": self.src},
                      {"segment_cd": seg})

    def _enrollments(self, party_sk: int, std: dict, roles: list[tuple[int, int]]) -> None:
        for e in std["enrollments"]:
            bu_code = e.get("business_unit_code")
            bu_sk = self.hom.sk("CAT_BUSINESS_UNIT", bu_code) if bu_code else -1
            role_sk = next((rs for rs, rb in roles if rb == bu_sk), roles[0][0] if roles else None)
            status = e["status"]
            sk = self._ins("party_service_enrollment", "enrollment_sk",
                           {"party_sk": party_sk, "party_role_sk": role_sk, "business_unit_cd": bu_sk, "service_cd": _sk(e["service"]),
                            "enrollment_status_cd": _sk(status), "enrolled_at": e.get("enrolled_at"), "closed_at": e.get("closed_at"),
                            "source_reference": e["reference"], "source_system_cd": self.src},
                           {"service_cd": e["service"], "enrollment_status_cd": status},
                           "ON CONFLICT (party_sk, service_cd, source_reference) DO UPDATE SET enrollment_status_cd=EXCLUDED.enrollment_status_cd, "
                           "closed_at=EXCLUDED.closed_at, captured_at=now()")
            if status.get("code") == "CLOSED":
                rule = RETENTION_BY_UES.get(bu_code, "AFFILIATE_5Y")
                years = int(self.retention[rule]["attrs"].get("years", 5))
                closed = e.get("closed_at") or date.today()
                exists = self.q("SELECT 1 FROM mdm.party_data_retention WHERE entity='PARTY_SERVICE_ENROLLMENT' AND entity_sk=:k", k=sk).first()
                if not exists:
                    self._ins("party_data_retention", "retention_sk",
                              {"party_sk": party_sk, "entity": "PARTY_SERVICE_ENROLLMENT", "entity_sk": sk,
                               "retention_rule_cd": self.retention[rule]["sk"], "purge_after": closed + timedelta(days=365 * years),
                               "legal_basis": f"{rule}: {years} años desde el cierre del vínculo ({bu_code})"})

    def _contacts(self, party_sk: int, std: dict) -> None:
        for c in std["contacts"]:
            if not c.get("value"):
                continue
            ch = self.channel[c["channel"]]
            h = contact_hash(c["channel"], c["value"])
            cp = self.q("INSERT INTO mdm.contact_point (channel_cd, contact_value, contact_hash) VALUES (:c, :v, :h) "
                        "ON CONFLICT (channel_cd, contact_hash) DO UPDATE SET contact_value=EXCLUDED.contact_value RETURNING contact_point_sk",
                        c=ch, v=c["value"], h=h).scalar_one()
            link = self._ins("party_contact_point", "party_contact_sk",
                             {"party_sk": party_sk, "contact_point_sk": cp, "usage_role_cd": _sk(c.get("usage_role"), self.K["OWNER"]) or self.K["OWNER"],
                              "confirmation_status_cd": _sk(c.get("confirmation"), self.K["CONFIRMED_BY_TITULAR"]) or self.K["CONFIRMED_BY_TITULAR"],
                              "origin_cd": _sk(c.get("origin"), self.K["TITULAR"]) or self.K["TITULAR"], "is_primary": bool(c.get("is_primary")),
                              "source_system_cd": self.src},
                             {"usage_role_cd": c.get("usage_role"), "confirmation_status_cd": c.get("confirmation"), "origin_cd": c.get("origin")},
                             "ON CONFLICT (party_sk, contact_point_sk, valid_from) DO UPDATE SET captured_at=now()")
            for pref in c.get("purposes") or []:
                if pref.get("allowed") is None:
                    continue
                self._ins("party_contact_pref", "pref_sk",
                          {"party_sk": party_sk, "channel_cd": ch, "party_contact_sk": link, "purpose_cd": self.purpose[pref["purpose"]],
                           "allowed": pref["allowed"], "frequency_cd": self.K["ANY"], "origin_cd": _sk(c.get("origin"), self.K["TITULAR"]) or self.K["TITULAR"]},
                          on_conflict="ON CONFLICT (party_sk, channel_cd, party_contact_sk, purpose_cd) WHERE valid_to IS NULL DO UPDATE SET allowed=EXCLUDED.allowed")

    def _addresses(self, party_sk: int, std: dict) -> None:
        # Una dirección es única dentro del party por (línea normalizada, país, municipio): si otra fuente ya la
        # aportó se reutiliza la fila (conserva el linaje de la primera fuente) y solo se refresca captured_at.
        # Hay una sola dirección principal por party: la conserva la primera fuente que la cargó.
        has_primary = self.q("SELECT 1 FROM mdm.party_address WHERE party_sk=:p AND is_primary", p=party_sk).first() is not None
        for i, a in enumerate(std["addresses"]):
            div = a.get("divipola")
            if div and div.get("unknown") and not div.get("raw"):
                div = None
            h = address_hash(a.get("line"), _code(a.get("country")), _code(div))
            sk = self._ins("party_address", "address_sk",
                           {"party_sk": party_sk, "address_line": a.get("line"), "country_cd": _sk(a.get("country")),
                            "divipola_cd": _sk(div), "geocoding_status_cd": self.K["GEO_PENDING"], "is_primary": i == 0 and not has_primary,
                            "address_hash": h, "source_system_cd": self.src},
                           {"country_cd": a.get("country"), "divipola_cd": div},
                           "ON CONFLICT (party_sk, address_hash) DO UPDATE SET captured_at=now(), "
                           "is_primary = mdm.party_address.is_primary OR EXCLUDED.is_primary")
            if sk is not None and i == 0:
                has_primary = True

    def _consents_prefs(self, party_sk: int, std: dict) -> None:
        for c in std["consents"]:
            if not c:
                continue
            t, st = _sk(c["consent_type"]), _sk(c["status"])
            cur = self.q("SELECT consent_sk, consent_status_cd FROM mdm.party_consent WHERE party_sk=:p AND consent_type_cd=:t AND valid_to IS NULL", p=party_sk, t=t).first()
            if cur and cur.consent_status_cd == st:
                continue
            if cur:
                self.q("UPDATE mdm.party_consent SET valid_to=now() WHERE consent_sk=:k", k=cur.consent_sk)
            granted = c["status"].get("code") == "GRANTED"
            self._ins("party_consent", "consent_sk", {"party_sk": party_sk, "consent_type_cd": t, "consent_status_cd": st,
                                                      "granted_at": "now()" if granted else None, "revoked_at": None if granted else "now()",
                                                      "evidence_ref": f"{self.hom.system}:{self.batch}", "source_system_cd": self.src})
        for p in std["prefs"]:
            self._ins("party_contact_pref", "pref_sk",
                      {"party_sk": party_sk, "channel_cd": self.channel[p["channel"]], "party_contact_sk": None, "purpose_cd": self.purpose[p["purpose"]],
                       "allowed": p["allowed"], "frequency_cd": self.K["ANY"], "origin_cd": self.K["TITULAR"]},
                      on_conflict="ON CONFLICT (party_sk, channel_cd, party_contact_sk, purpose_cd) WHERE valid_to IS NULL DO UPDATE SET allowed=EXCLUDED.allowed")

    def _completeness(self, party_sk: int, std: dict) -> None:
        if std["party_type"] == "PERSON":
            per = std["person"]
            checks = [per.get("first_name"), per.get("first_surname"), per.get("birth_date"), _sk(per.get("gender")) > 0,
                      bool(std["identifiers"]), any(c["channel"] == "EMAIL" for c in std["contacts"]),
                      any(c["channel"] == "PHONE" for c in std["contacts"]), any(_sk(a.get("divipola")) > 0 for a in std["addresses"])]
        else:
            org = std["org"]
            checks = [org.get("legal_name"), bool(std["identifiers"]), _sk(org.get("ciiu")) > 0, _sk(org.get("org_type")) > 0,
                      any(c["channel"] == "EMAIL" for c in std["contacts"]), any(c["channel"] == "PHONE" for c in std["contacts"]),
                      any(_sk(a.get("divipola")) > 0 for a in std["addresses"])]
        score = round(100 * sum(1 for x in checks if x) / len(checks), 2)
        self.q("UPDATE mdm.party SET completeness_score=:c, updated_at=now() WHERE party_sk=:p", c=score, p=party_sk)

    # ------------------------------------------------------------------ cierre del lote
    def finish(self) -> None:
        for party_sk, g in self.deferred_grp:
            gsk = self.q("INSERT INTO mdm.party_group (group_type_cd, group_name, source_system_cd, source_reference) VALUES (:t, :n, :s, :r) "
                         "ON CONFLICT (source_system_cd, source_reference) DO UPDATE SET group_name=EXCLUDED.group_name RETURNING group_sk",
                         t=self.K[g["group_type"]], n=f"{g['group_type']} {g['reference']}", s=self.src, r=g["reference"]).scalar_one()
            self._ins("party_group_member", "group_member_sk", {"group_sk": gsk, "party_sk": party_sk, "member_role_cd": self.member_role[g["member_role"]]},
                      on_conflict="ON CONFLICT (group_sk, party_sk, valid_from) DO NOTHING")
            if g["member_role"] == "ANCHOR":
                self.q("UPDATE mdm.party_group SET anchor_party_sk=:p WHERE group_sk=:g", p=party_sk, g=gsk)
        for from_sk, staging_ref, r in self.deferred_rel:
            rt = r["type"]
            if rt.get("unknown"):
                continue
            to_sk = self.q("SELECT party_sk FROM mdm.xref_party_source WHERE source_system_cd=:s AND external_id=:e", s=self.src, e=r["to_external_id"]).scalar()
            if to_sk is None:
                self.dq(from_sk, staging_ref, "CONSISTENCY", "relationship", "WARNING", "Party destino de la relación no existe en la fuente",
                        to_external_id=r["to_external_id"], relationship=rt.get("code"))
                continue
            types = dict(self.q("SELECT p.party_sk, v.value_code FROM mdm.party p JOIN rdm.reference_value v ON v.value_sk=p.party_type_cd WHERE p.party_sk IN (:a, :b)",
                                a=from_sk, b=to_sk).all())
            _, rsk, f_ok, t_ok, inverse = self.reltypes[rt["code"]]
            if (f_ok not in ("ANY", types[from_sk])) or (t_ok not in ("ANY", types[to_sk])):
                self.dq(from_sk, staging_ref, "VALIDITY", "relationship", "WARNING", "Tipos de party no permitidos para la relación; se rechaza",
                        relationship=rt["code"], from_type=types[from_sk], to_type=types[to_sk], expected=f"{f_ok}→{t_ok}")
                continue
            self._ins("party_relationship", "relationship_sk", {"from_party_sk": from_sk, "to_party_sk": to_sk, "relationship_type_cd": rsk, "source_system_cd": self.src},
                      on_conflict="ON CONFLICT (from_party_sk, to_party_sk, relationship_type_cd, valid_from) DO NOTHING")
            if inverse:
                self._ins("party_relationship", "relationship_sk", {"from_party_sk": to_sk, "to_party_sk": from_sk, "relationship_type_cd": self.reltypes[inverse][1], "source_system_cd": self.src},
                          on_conflict="ON CONFLICT (from_party_sk, to_party_sk, relationship_type_cd, valid_from) DO NOTHING")

    def attach_targets(self) -> None:
        """Completa los hallazgos de códigos sin homologar con la fila/columna que quedó en UNKNOWN (§7.2)."""
        for key, tgt in self.targets.items():
            self.q("UPDATE mdm.party_dq_issue SET detail = detail || CAST(:t AS jsonb), party_sk = COALESCE(party_sk, "
                   "(SELECT party_sk FROM mdm.party WHERE party_sk = CAST(:psk AS BIGINT))) WHERE detail->>'issue_key' = :k",
                   t=json.dumps(tgt), psk=tgt.get("party_sk"), k=key)
