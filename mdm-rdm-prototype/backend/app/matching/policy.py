"""Política de matching v2 (SPEC §8, afinable en caliente): decide con tres estados por atributo
(AGREE / PARTIAL / DISAGREE / MISSING), evidencia normalizada sobre el peso realmente comparable,
cobertura, grupos de suficiencia y vetos por identificador. La política es dato versionado en
mdm.MATCH_POLICY (una activa por tipo de entidad); nunca se edita una versión publicada: cada ajuste
crea la siguiente y PARTY_MATCH.decision_basis conserva con cuál se decidió cada par.

Base estadística: Fellegi & Sunter (1969): un atributo ausente no es evidencia ni a favor ni en
contra; la contradicción de un identificador fuerte es evidencia negativa (aquí, veto). Gobierno:
Ley 1581/2012 art. 4 lit. d (veracidad o calidad) y art. 17; ISO/IEC 42001:2023 cl. 6.1;
NIST AI RMF 1.0 función MEASURE; DAMA-DMBOK2 Cap. 10."""
from __future__ import annotations

import json
from copy import deepcopy

from sqlalchemy import text
from sqlalchemy.orm import Session

DECISIONS = ("NO_MATCH", "POSSIBLE", "PROBABLE", "AUTO_MERGE")
RANK = {d: i for i, d in enumerate(DECISIONS)}
GROUP_DECISIONS = ("AUTO_MERGE", "PROBABLE", "POSSIBLE")

# Política inicial (versión 1 de cada tipo). Grupo = conjunto de atributos que, presentes en AMBOS
# registros y coincidentes, constituye identidad por sí mismo. "a|b" = basta uno de los dos.
DEFAULT_POLICIES: dict[str, dict] = {
    "PERSON": {
        "thresholds": {"AUTO_MERGE": 85, "PROBABLE": 70, "POSSIBLE": 50},
        "min_coverage": 60,
        "min_raw_points": 50,
        "auto_requires_group": True,
        "veto_attributes": ["document"],
        "veto_mode": "REVIEW",
        "veto_typo": True,
        "groups": [
            {"code": "G1", "name": "Identidad documental", "attributes": ["document", "first_surname"], "decision": "AUTO_MERGE", "active": True,
             "note": "Documento (tipo y número) y primer apellido coinciden"},
            {"code": "G2", "name": "Identidad demográfica", "attributes": ["first_name", "first_surname", "second_surname", "birth_date"],
             "decision": "PROBABLE", "active": True,
             "note": "Nombre, dos apellidos y fecha de nacimiento; sola no fusiona (riesgo de fecha heredada en grupos familiares)"},
            {"code": "G3", "name": "Demográfica + un contacto confirmado", "attributes": ["first_name", "first_surname", "second_surname", "birth_date", "email|phone"],
             "decision": "PROBABLE", "active": True, "note": "G2 más correo o teléfono del titular confirmado"},
            {"code": "G4", "name": "Demográfica + correo y teléfono confirmados", "attributes": ["first_name", "first_surname", "second_surname", "birth_date", "email", "phone"],
             "decision": "AUTO_MERGE", "active": True, "note": "G2 más dos canales confirmados por el titular: equivale a identidad documental"},
        ],
    },
    "ORGANIZATION": {
        "thresholds": {"AUTO_MERGE": 85, "PROBABLE": 70, "POSSIBLE": 50},
        "min_coverage": 60,
        "min_raw_points": 50,
        "auto_requires_group": True,
        "veto_attributes": ["nit"],
        "veto_mode": "REVIEW",
        "veto_typo": True,
        "groups": [
            {"code": "O1", "name": "NIT + nombre", "attributes": ["nit", "legal_name|trade_name"], "decision": "AUTO_MERGE", "active": True,
             "note": "NIT válido igual y razón social o nombre comercial coincidente"},
            {"code": "O2", "name": "Razón social + municipio", "attributes": ["legal_name", "municipality"], "decision": "PROBABLE", "active": True,
             "note": "Sin NIT comparable"},
        ],
    },
}


# ------------------------------------------------------------------ persistencia
def _sk(session: Session, catalog: str, code: str) -> int:
    return session.execute(text("SELECT value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code=:c AND value_code=:v"), {"c": catalog, "v": code}).scalar_one()


def ensure_default_policies(session: Session, actor: str = "engine") -> int:
    """Idempotente: siembra la versión 1 de cada tipo si no existe ninguna. Devuelve filas creadas."""
    created = 0
    for entity, params in DEFAULT_POLICIES.items():
        sk = _sk(session, "CAT_PARTY_TYPE", entity)
        if session.execute(text("SELECT 1 FROM mdm.match_policy WHERE entity_type_cd=:e"), {"e": sk}).scalar():
            continue
        session.execute(text("INSERT INTO mdm.match_policy (entity_type_cd, version, params, is_active, note, created_by) VALUES (:e, 1, CAST(:p AS jsonb), TRUE, :n, :a)"),
                        {"e": sk, "p": json.dumps(params), "n": "Política inicial (SPEC §8 v2)", "a": actor})
        created += 1
    return created


def load_policies(session: Session) -> dict[str, dict]:
    rows = session.execute(text("""SELECT t.value_code, p.version, p.params FROM mdm.match_policy p
        JOIN rdm.reference_value t ON t.value_sk=p.entity_type_cd WHERE p.is_active""")).all()
    out = {}
    for entity, version, params in rows:
        out[entity] = dict(params) | {"version": version}
    return out


def list_versions(session: Session, entity: str) -> list[dict]:
    rows = session.execute(text("""SELECT p.policy_sk, p.version, p.params, p.is_active, p.note, p.created_by, p.created_at FROM mdm.match_policy p
        JOIN rdm.reference_value t ON t.value_sk=p.entity_type_cd WHERE t.value_code=:e ORDER BY p.version DESC"""), {"e": entity}).mappings().all()
    return [dict(r) for r in rows]


def rule_attributes(session: Session, entity: str) -> list[dict]:
    from app.matching.rules import RULE_VERSION
    rows = session.execute(text("""SELECT r.attribute, r.weight, r.algorithm FROM mdm.match_rule r JOIN rdm.reference_value t ON t.value_sk=r.entity_type_cd
        WHERE t.value_code=:e AND r.version=:v AND r.is_active ORDER BY r.weight DESC"""), {"e": entity, "v": RULE_VERSION}).mappings().all()
    return [dict(r) | {"weight": float(r["weight"])} for r in rows]


def validate_policy(params: dict, attributes: list[str]) -> dict:
    """Normaliza y valida la política candidata; lanza ValueError con el motivo (mensaje para la consola)."""
    p = deepcopy(params or {})
    th = p.get("thresholds") or {}
    try:
        th = {k: float(th[k]) for k in ("AUTO_MERGE", "PROBABLE", "POSSIBLE")}
    except (KeyError, TypeError, ValueError):
        raise ValueError("thresholds debe traer AUTO_MERGE, PROBABLE y POSSIBLE numéricos")
    if not (0 < th["POSSIBLE"] < th["PROBABLE"] < th["AUTO_MERGE"] <= 100):
        raise ValueError("Los umbrales deben cumplir 0 < POSSIBLE < PROBABLE < AUTO_MERGE ≤ 100")
    p["thresholds"] = th
    cov = float(p.get("min_coverage", 60))
    if not (0 <= cov <= 100):
        raise ValueError("min_coverage debe estar entre 0 y 100")
    p["min_coverage"] = cov
    raw = float(p.get("min_raw_points", 50))
    if not (0 <= raw <= 100):
        raise ValueError("min_raw_points debe estar entre 0 y 100")
    p["min_raw_points"] = raw
    p["auto_requires_group"] = bool(p.get("auto_requires_group", True))
    known = set(attributes)
    vetoes = [str(v) for v in (p.get("veto_attributes") or [])]
    bad = [v for v in vetoes if v not in known]
    if bad:
        raise ValueError(f"veto_attributes desconocidos: {bad}")
    p["veto_attributes"] = vetoes
    mode = str(p.get("veto_mode") or "REVIEW").upper()
    if mode not in ("REVIEW", "NO_MATCH"):
        raise ValueError("veto_mode debe ser REVIEW (nunca auto-merge, a revisión) o NO_MATCH (son personas distintas)")
    p["veto_mode"] = mode
    p["veto_typo"] = bool(p.get("veto_typo", True))
    groups, codes = [], set()
    for g in p.get("groups") or []:
        code = str(g.get("code") or "").strip()
        if not code or code in codes:
            raise ValueError(f"Grupo sin código o repetido: {code!r}")
        codes.add(code)
        attrs = [str(a).strip() for a in (g.get("attributes") or []) if str(a).strip()]
        if not attrs:
            raise ValueError(f"Grupo {code} sin atributos")
        for tok in attrs:
            for alt in tok.split("|"):
                if alt not in known:
                    raise ValueError(f"Grupo {code}: atributo desconocido {alt!r}")
        dec = str(g.get("decision") or "PROBABLE").upper()
        if dec not in GROUP_DECISIONS:
            raise ValueError(f"Grupo {code}: decisión inválida {dec!r} (AUTO_MERGE, PROBABLE o POSSIBLE)")
        groups.append({"code": code, "name": str(g.get("name") or code)[:120], "attributes": attrs, "decision": dec,
                       "active": bool(g.get("active", True)), "note": str(g.get("note") or "")[:300]})
    p["groups"] = groups
    return p


def publish_policy(session: Session, entity: str, params: dict, note: str | None, actor: str) -> dict:
    """Nueva versión activa (la anterior queda inactiva, nunca se borra ni se edita)."""
    attrs = [a["attribute"] for a in rule_attributes(session, entity)]
    if not attrs:
        raise ValueError(f"Sin reglas de matching para {entity}")
    clean = validate_policy(params, attrs)
    sk = _sk(session, "CAT_PARTY_TYPE", entity)
    session.execute(text("SELECT set_config('app.actor', :a, false)"), {"a": actor})
    session.execute(text("UPDATE mdm.match_policy SET is_active=FALSE WHERE entity_type_cd=:e AND is_active"), {"e": sk})
    version = session.execute(text("SELECT COALESCE(MAX(version), 0) + 1 FROM mdm.match_policy WHERE entity_type_cd=:e"), {"e": sk}).scalar_one()
    session.execute(text("INSERT INTO mdm.match_policy (entity_type_cd, version, params, is_active, note, created_by) VALUES (:e, :v, CAST(:p AS jsonb), TRUE, :n, :a)"),
                    {"e": sk, "v": version, "p": json.dumps(clean), "n": (note or "")[:500] or None, "a": actor})
    return {"entity": entity, "version": version, "params": clean}


# ------------------------------------------------------------------ decisión
def _present(states: dict[str, str], tok: str) -> bool:
    return any(states.get(alt, "MISSING") != "MISSING" for alt in tok.split("|"))


def _agree(states: dict[str, str], tok: str) -> bool:
    return any(states.get(alt) == "AGREE" for alt in tok.split("|"))


def _threshold_decision(score: float, th: dict) -> str:
    if score >= th["AUTO_MERGE"]:
        return "AUTO_MERGE"
    if score >= th["PROBABLE"]:
        return "PROBABLE"
    if score >= th["POSSIBLE"]:
        return "POSSIBLE"
    return "NO_MATCH"


def decide_pair(rows: list[dict], policy: dict) -> tuple[str, dict]:
    """(decisión, base). `rows` es el score_detail con `state` por atributo."""
    states = {r["attribute"]: r.get("state") or infer_state(r) for r in rows}
    w_total = sum(float(r["weight"]) for r in rows)
    w_avail = sum(float(r["weight"]) for r in rows if states[r["attribute"]] != "MISSING")
    points = sum(float(r["points"]) for r in rows)
    evidence = round(100 * points / w_avail, 2) if w_avail else 0.0
    coverage = round(100 * w_avail / w_total, 2) if w_total else 0.0
    th = policy["thresholds"]
    reasons = {r["attribute"]: r.get("reason") for r in rows}
    # veto: identificador contradictorio; o a un solo error de digitación (PARTIAL/TYPO) si la política lo mantiene vetado
    vetoed = [a for a in policy.get("veto_attributes", []) if states.get(a) == "DISAGREE"
              or (states.get(a) == "PARTIAL" and reasons.get(a) == "TYPO" and policy.get("veto_typo", True))]
    typo = [a for a, r in reasons.items() if r == "TYPO"]
    groups = []
    best_group, best_rank = None, -1
    satisfied_groups: list[str] = []
    for g in policy.get("groups", []):
        applies = all(_present(states, t) for t in g["attributes"])
        satisfied = g.get("active", True) and applies and all(_agree(states, t) for t in g["attributes"])
        missing = [t for t in g["attributes"] if not _present(states, t)]
        failing = [t for t in g["attributes"] if _present(states, t) and not _agree(states, t)]
        groups.append({"code": g["code"], "name": g["name"], "decision": g["decision"], "active": g.get("active", True),
                       "applies": applies, "satisfied": bool(satisfied), "missing": missing, "failing": failing})
        if satisfied:
            satisfied_groups.append(g["code"])
        # entre grupos satisfechos con la misma decisión se muestra el primero en el orden de la política
        if satisfied and RANK[g["decision"]] > best_rank:
            best_group, best_rank = g["code"], RANK[g["decision"]]
    # Vía de umbrales: evidencia normalizada si la cobertura alcanza el mínimo, puntos brutos si no; por debajo del
    # piso de puntos brutos (SPEC §8.4: < 50 se descarta) la evidencia normalizada no crea candidatos.
    uses_evidence = coverage >= policy.get("min_coverage", 60)
    th_score = evidence if uses_evidence else round(points, 2)
    th_decision = _threshold_decision(th_score, th) if points >= policy.get("min_raw_points", 0) else "NO_MATCH"
    if th_decision == "AUTO_MERGE" and policy.get("auto_requires_group", True):
        th_decision = "PROBABLE"
    veto_mode = policy.get("veto_mode", "REVIEW")
    if best_rank >= RANK[th_decision] and best_group is not None and best_rank > RANK["NO_MATCH"]:
        decision, decided_by = DECISIONS[best_rank], f"group:{best_group}"
    else:
        decision, decided_by = th_decision, "threshold:evidence" if uses_evidence else "threshold:raw_points"
    if vetoed and veto_mode == "NO_MATCH":
        decision, decided_by = "NO_MATCH", f"veto:{','.join(vetoed)}"
    elif vetoed and RANK[decision] > RANK["PROBABLE"]:
        # un identificador contradictorio nunca se fusiona solo: baja a revisión humana (dígitos transpuestos, homónimos)
        decision, decided_by = "PROBABLE", f"{decided_by}+veto_review:{','.join(vetoed)}"
    basis = {"policy_version": policy.get("version"), "decision": decision, "decided_by": decided_by,
             "evidence": evidence, "coverage": coverage, "raw_points": round(points, 2), "weight_available": w_avail, "weight_total": w_total,
             "threshold_score": th_score, "threshold_decision": th_decision, "vetoed_by": vetoed, "veto_mode": veto_mode, "typo": typo,
             "satisfied_groups": satisfied_groups, "groups": groups, "states": states}
    return decision, basis


def infer_state(r: dict) -> str:
    """Estado de una fila v1 (sin `state`): reconstruido de valores y puntos para simular sobre pares históricos."""
    va, vb = r.get("value_a"), r.get("value_b")
    empty = lambda v: v is None or v == "" or v == []  # noqa: E731
    if empty(va) or empty(vb):
        return "MISSING"
    w, pts = float(r.get("weight") or 0), float(r.get("points") or 0)
    if w and pts >= w:
        return "AGREE"
    if pts > 0:
        return "PARTIAL"
    if r.get("attribute") == "document" and isinstance(va, list) and isinstance(vb, list):
        ta = {x[0] for x in va if isinstance(x, list) and x}; tb = {x[0] for x in vb if isinstance(x, list) and x}
        if not (ta & tb):
            return "MISSING"   # tipos de documento distintos: no comparables
    return "DISAGREE"


# ------------------------------------------------------------------ simulación y recálculo
def simulate(session: Session, entity: str, params: dict, scope: str = "all") -> dict:
    """Reevalúa la evidencia registrada de cada par bajo la política candidata, sin persistir.
    Sobre los pares RESUELTOS por humanos mide el acuerdo con la verdad conocida (calibración)."""
    attrs = [a["attribute"] for a in rule_attributes(session, entity)]
    clean = validate_policy(params, attrs) | {"version": None}
    filt = "" if scope == "all" else "AND m.match_status = 'PENDING'"
    rows = session.execute(text(f"""
        SELECT m.match_sk, m.party_a_sk, m.party_b_sk, m.total_score, m.score_detail, d.value_code AS decision, m.match_status, m.decision_basis,
               COALESCE(pa.full_name_normalized, oa.legal_name_normalized) AS name_a, COALESCE(pb.full_name_normalized, ob.legal_name_normalized) AS name_b,
               (SELECT string_agg(DISTINCT ac.value_code || ':' || (a.new_value->>'decision'), ',') FROM mdm.party_audit_log a JOIN rdm.reference_value ac ON ac.value_sk=a.action_cd
                 WHERE a.entity='PARTY_MATCH' AND a.entity_sk=m.match_sk AND ac.value_code='REVIEW_DECISION') AS human
        FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd
        JOIN mdm.party p ON p.party_sk=m.party_a_sk JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd
        LEFT JOIN mdm.party_person pa ON pa.party_sk=m.party_a_sk LEFT JOIN mdm.party_person pb ON pb.party_sk=m.party_b_sk
        LEFT JOIN mdm.party_org oa ON oa.party_sk=m.party_a_sk LEFT JOIN mdm.party_org ob ON ob.party_sk=m.party_b_sk
        WHERE t.value_code=:e {filt} ORDER BY m.match_sk"""), {"e": entity}).mappings().all()
    out, transitions, agreement = [], {}, {"human_merge": {"same": 0, "changed": 0}, "human_no_match": {"same": 0, "changed": 0}}
    for r in rows:
        new, basis = decide_pair(list(r["score_detail"]), clean)
        current = r["decision"]
        key = f"{current}→{new}"
        transitions[key] = transitions.get(key, 0) + 1
        human = r["human"] or ""
        truth = "MERGE" if "REVIEW_DECISION:MERGE" in human else ("NO_MATCH" if "REVIEW_DECISION:NO_MATCH" in human else None)
        if truth == "MERGE":
            agreement["human_merge"]["same" if new in ("AUTO_MERGE", "PROBABLE") else "changed"] += 1
        elif truth == "NO_MATCH":
            agreement["human_no_match"]["same" if new in ("NO_MATCH", "POSSIBLE") else "changed"] += 1
        out.append({"match_sk": r["match_sk"], "party_a_sk": r["party_a_sk"], "party_b_sk": r["party_b_sk"], "name_a": r["name_a"], "name_b": r["name_b"],
                    "current_decision": current, "match_status": r["match_status"], "human_decision": truth,
                    "new_decision": new, "changed": new != current, "evidence": basis["evidence"], "coverage": basis["coverage"], "decided_by": basis["decided_by"]})
    changed = [o for o in out if o["changed"]]
    pending_changed = [o for o in changed if o["match_status"] == "PENDING"]
    summary = {"pairs": len(out), "changed": len(changed), "pending_changed": len(pending_changed),
               "pending_to_auto": sum(1 for o in pending_changed if o["new_decision"] == "AUTO_MERGE"),
               "pending_to_no_match": sum(1 for o in pending_changed if o["new_decision"] == "NO_MATCH"),
               "transitions": dict(sorted(transitions.items())), "agreement_with_humans": agreement}
    return {"entity": entity, "policy": clean, "summary": summary, "pairs": changed[:500]}


def recalculate(session: Session, actor: str, entity: str | None = None) -> dict:
    """Aplica la política activa a los pares PENDIENTES (no a los decididos por humanos ni a los en revisión):
    AUTO_MERGE fusiona (merge AUTO, reversible), NO_MATCH resuelve, el resto cambia de decisión y sigue en cola."""
    from app.matching.engine import golden_conflict
    from app.matching.features import load_features
    from app.matching.rules import RULE_VERSION, load_rules
    from app.matching.scoring import score_pair
    from app.stewardship.merge import merge_parties

    session.execute(text("SELECT set_config('app.actor', :a, false)"), {"a": actor})
    policies, rules = load_policies(session), load_rules(session)
    filt = "AND t.value_code=:e" if entity else ""
    pairs = session.execute(text(f"""SELECT m.match_sk, m.party_a_sk, m.party_b_sk, d.value_code AS decision, t.value_code AS entity
        FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd JOIN mdm.party p ON p.party_sk=m.party_a_sk
        JOIN rdm.reference_value t ON t.value_sk=p.party_type_cd WHERE m.match_status='PENDING' {filt} ORDER BY m.match_sk"""), {"e": entity}).mappings().all()
    sks = sorted({sk for r in pairs for sk in (r["party_a_sk"], r["party_b_sk"])})
    feats = load_features(session, sks, any_status=True) if sks else {}
    decision_sk = {d: _sk(session, "CAT_MATCH_DECISION", d) for d in DECISIONS}
    counters = {"evaluated": 0, "unchanged": 0, "auto_merged": 0, "resolved_no_match": 0, "requeued": 0, "skipped": 0, "changes": []}
    merged: set[int] = set()
    for r in pairs:
        a, b = r["party_a_sk"], r["party_b_sk"]
        fa, fb = feats.get(a), feats.get(b)
        if not fa or not fb or "MERGED" in (fa["golden_status"], fb["golden_status"]) or a in merged or b in merged:
            counters["skipped"] += 1
            continue
        pol = policies[r["entity"]]
        score, rows = score_pair(fa, fb, rules)
        new, basis = decide_pair(rows, pol)
        if new == "AUTO_MERGE" and (third := golden_conflict(session, a, b)):
            new, basis = "PROBABLE", basis | {"decision": "PROBABLE", "decided_by": "forced_review:document_uniqueness", "conflicting_party": third}
        counters["evaluated"] += 1
        session.execute(text("""UPDATE mdm.party_match SET total_score=:s, score_detail=CAST(:d AS jsonb), decision_basis=CAST(:b AS jsonb), decision_cd=:dec, rule_version=:v
            WHERE match_sk=:k"""), {"s": basis["evidence"], "d": json.dumps(rows, default=str), "b": json.dumps(basis, default=str), "dec": decision_sk[new], "v": RULE_VERSION, "k": r["match_sk"]})
        if new == r["decision"]:
            counters["unchanged"] += 1
            continue
        counters["changes"].append({"match_sk": r["match_sk"], "from": r["decision"], "to": new, "decided_by": basis["decided_by"]})
        if new == "AUTO_MERGE":
            surviving, absorbed = (a, b) if (fa["golden_status"] == "GOLDEN" or fb["golden_status"] != "GOLDEN") else (b, a)
            just = f"evidencia {basis['evidence']} sobre cobertura {basis['coverage']} · {basis['decided_by']} (política v{pol['version']}, recálculo)"
            merge_parties(session, surviving, absorbed, r["match_sk"], "AUTO", f"engine.v{RULE_VERSION}.p{pol['version']}", just)
            session.execute(text("UPDATE mdm.party_match SET match_status='RESOLVED' WHERE match_sk=:k"), {"k": r["match_sk"]})
            merged |= {a, b}
            counters["auto_merged"] += 1
        elif new == "NO_MATCH":
            session.execute(text("UPDATE mdm.party_match SET match_status='RESOLVED' WHERE match_sk=:k"), {"k": r["match_sk"]})
            session.execute(text("""INSERT INTO mdm.party_audit_log (party_sk, entity, entity_sk, action_cd, new_value, actor) VALUES (NULL, 'PARTY_MATCH', :k, :a, CAST(:v AS jsonb), :actor)"""),
                            {"k": r["match_sk"], "a": _sk(session, "CAT_AUDIT_ACTION", "REVIEW_DECISION"), "actor": actor,
                             "v": json.dumps({"decision": "NO_MATCH", "how": "ENGINE_RECALCULATION", "justification": f"{basis['decided_by']} (política v{pol['version']})"})})
            counters["resolved_no_match"] += 1
        else:
            counters["requeued"] += 1
    return counters
