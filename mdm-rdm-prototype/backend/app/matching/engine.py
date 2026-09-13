"""Ejecución del matching (SPEC §8): XREF primero (regla dura §3.11) → solo los parties
CANDIDATE se comparan; blocking por tipo (§3.17); scoring con evidencia; umbrales; merge
automático ≥ 85 con snapshot; promoción a GOLDEN con la regla de unicidad de documento (§3.16)."""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.matching.features import blocking_keys, load_features
from app.matching.rules import RULE_VERSION, ensure_match_rules, load_rules
from app.matching.scoring import decide, score_pair


def _sk(session: Session, catalog: str, code: str) -> int:
    return session.execute(text("SELECT value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code=:c AND value_code=:v"), {"c": catalog, "v": code}).scalar_one()


class MatchingEngine:
    """Interfaz desacoplada: producción la sustituye por Splink (Fellegi-Sunter + EM) para > 10M."""

    def __init__(self, session: Session):
        self.s = session
        ensure_match_rules(session)
        self.rules = load_rules(session)

    def candidate_pairs(self, feats: dict[int, dict], candidates: list[int], batch_id: int | None) -> tuple[set[tuple[int, int]], int]:
        index: dict[tuple[str, str], set[int]] = {}
        for sk, f in feats.items():
            for key in blocking_keys(f):
                index.setdefault(key, set()).add(sk)
        cand_set = set(candidates)
        pairs: set[tuple[int, int]] = set()
        buckets_persisted = 0
        for key, members in index.items():
            if len(members) < 2 or not (members & cand_set):
                continue
            strategy, blocking_key = key
            ptype = "PERSON" if blocking_key.startswith("P|") else "ORGANIZATION"
            bsk = self.s.execute(text("INSERT INTO mdm.party_bucket (blocking_key, blocking_strategy_cd, party_type_cd, batch_id) VALUES (:k, :st, :t, :b) RETURNING bucket_sk"),
                                 {"k": blocking_key, "st": _sk(self.s, "CAT_BLOCKING_STRATEGY", strategy), "t": _sk(self.s, "CAT_PARTY_TYPE", ptype), "b": batch_id}).scalar_one()
            for m in members:
                self.s.execute(text("INSERT INTO mdm.bucket_candidate (bucket_sk, party_sk) VALUES (:b, :p)"), {"b": bsk, "p": m})
            buckets_persisted += 1
            for a in members & cand_set:
                for b in members:
                    if a != b and feats[a]["party_type"] == feats[b]["party_type"]:
                        pairs.add((min(a, b), max(a, b)))
        return pairs, buckets_persisted

    def run(self, actor: str = "matching", batch_id: int | None = None, candidate_sks: list[int] | None = None) -> dict:
        from app.compliance.eligibility import recompute_party
        from app.stewardship.merge import merge_parties
        from app.survivorship.engine import apply_survivorship

        self.s.execute(text("SELECT set_config('app.actor', :a, false)"), {"a": actor})
        feats = load_features(self.s)
        candidates = [sk for sk, f in feats.items() if f["golden_status"] == "CANDIDATE" and (candidate_sks is None or sk in candidate_sks)]
        counters = dict(candidates=len(candidates), buckets=0, compared=0, matched=0, auto_merged=0, probable=0, possible=0, promoted=0, forced_review=0)
        pairs, counters["buckets"] = self.candidate_pairs(feats, candidates, batch_id)
        decision_sk = {d: _sk(self.s, "CAT_MATCH_DECISION", d) for d in ("AUTO_MERGE", "PROBABLE", "POSSIBLE", "NO_MATCH")}
        scored: list[tuple[float, int, int, str, list]] = []
        for a, b in pairs:
            score, detail = score_pair(feats[a], feats[b], self.rules)
            counters["compared"] += 1
            d = decide(score)
            if d != "NO_MATCH":
                scored.append((score, a, b, d, detail))
        scored.sort(key=lambda x: -x[0])
        merged: dict[int, int] = {}
        for score, a, b, d, detail in scored:
            if a in merged or b in merged:
                continue   # ya absorbido en esta corrida: la siguiente corrida re-evalúa contra el sobreviviente
            # no se repite un par abierto ni uno que un humano ya resolvió como NO_MATCH (decisión vinculante)
            exists = self.s.execute(text("""SELECT match_sk FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd
                WHERE party_a_sk=:a AND party_b_sk=:b AND (match_status <> 'RESOLVED' OR d.value_code='NO_MATCH')"""), {"a": a, "b": b}).scalar()
            if exists:
                continue
            match_sk = self.s.execute(text("""
                INSERT INTO mdm.party_match (party_a_sk, party_b_sk, total_score, score_detail, decision_cd, rule_version, batch_id)
                VALUES (:a, :b, :s, CAST(:d AS jsonb), :dec, :v, :bt) RETURNING match_sk"""),
                {"a": a, "b": b, "s": score, "d": json.dumps(detail, default=str), "dec": decision_sk[d], "v": RULE_VERSION, "bt": batch_id}).scalar_one()
            counters["matched"] += 1
            if d == "AUTO_MERGE":
                # sobrevive el GOLDEN; entre candidatos, el más antiguo (SK menor)
                surviving, absorbed = (a, b) if (feats[a]["golden_status"] == "GOLDEN" or feats[b]["golden_status"] != "GOLDEN") else (b, a)
                merge_parties(self.s, surviving, absorbed, match_sk, "AUTO", "engine.v1", f"score {score} ≥ 85 (AUTO_MERGE)")
                merged[absorbed] = surviving
                counters["auto_merged"] += 1
            elif d == "PROBABLE":
                counters["probable"] += 1
            else:
                counters["possible"] += 1
        # Promoción a GOLDEN de los candidatos no absorbidos, con la regla de unicidad de documento (§3.16)
        golden = _sk(self.s, "CAT_GOLDEN_STATUS", "GOLDEN")
        for c in candidates:
            if c in merged:
                continue
            conflict = self.s.execute(text("""
                SELECT o.party_sk FROM mdm.party_identifier i JOIN mdm.party_identifier o ON o.id_type_cd=i.id_type_cd AND o.id_number=i.id_number AND o.party_sk<>i.party_sk
                WHERE i.party_sk=:c AND o.is_golden LIMIT 1"""), {"c": c}).scalar()
            if conflict:
                a, b = min(c, conflict), max(c, conflict)
                if not self.s.execute(text("""SELECT 1 FROM mdm.party_match m JOIN rdm.reference_value d ON d.value_sk=m.decision_cd
                        WHERE party_a_sk=:a AND party_b_sk=:b AND (match_status<>'RESOLVED' OR d.value_code='NO_MATCH')"""), {"a": a, "b": b}).scalar():
                    score, detail = score_pair(feats[a], feats[b], self.rules) if b in feats and a in feats else (0, [])
                    self.s.execute(text("""INSERT INTO mdm.party_match (party_a_sk, party_b_sk, total_score, score_detail, decision_cd, rule_version, batch_id)
                        VALUES (:a, :b, :s, CAST(:d AS jsonb), :dec, :v, :bt)"""),
                                   {"a": a, "b": b, "s": score, "d": json.dumps(detail, default=str), "dec": decision_sk["PROBABLE"], "v": RULE_VERSION, "bt": batch_id})
                if not self.s.execute(text("SELECT 1 FROM mdm.party_dq_issue WHERE party_sk=:c AND staging_ref='matching' AND resolved_at IS NULL"), {"c": c}).scalar():
                    self.s.execute(text("""INSERT INTO mdm.party_dq_issue (staging_ref, party_sk, dq_category_cd, field, detail, severity_cd, batch_id)
                        VALUES ('matching', :c, :cat, 'identifier', CAST(:d AS jsonb), :sev, :bt)"""),
                                   {"c": c, "cat": _sk(self.s, "CAT_DQ_CATEGORY", "UNIQUENESS"), "sev": _sk(self.s, "CAT_SEVERITY", "WARNING"), "bt": batch_id,
                                    "d": json.dumps({"message": "Documento ya asignado a un golden: matching forzado a revisión (regla dura 3.16)", "other_party": conflict})})
                counters["forced_review"] += 1
                continue
            self.s.execute(text("UPDATE mdm.party SET golden_status_cd=:g, updated_at=now() WHERE party_sk=:c"), {"g": golden, "c": c})
            apply_survivorship(self.s, c)
            recompute_party(self.s, c)
            counters["promoted"] += 1
        if batch_id:
            self.s.execute(text("UPDATE staging.load_batch SET matched=:m, auto_merged=:am, probable=:pr WHERE batch_id=:b"),
                           {"m": counters["matched"], "am": counters["auto_merged"], "pr": counters["probable"], "b": batch_id})
        return counters


def run_matching(session: Session, actor: str = "matching", batch_id: int | None = None, candidate_sks: list[int] | None = None) -> dict:
    own_batch = batch_id is None
    if own_batch:
        batch_id = session.execute(text("INSERT INTO staging.load_batch (source_system_cd, mode, actor) VALUES (NULL, 'MATCH', :a) RETURNING batch_id"), {"a": actor}).scalar_one()
    try:
        result = MatchingEngine(session).run(actor, batch_id, candidate_sks)
        if own_batch:
            session.execute(text("UPDATE staging.load_batch SET status='OK', finished_at=now(), extracted=:c, matched=:m, auto_merged=:am, probable=:pr, loaded=:p, detail=CAST(:d AS jsonb) WHERE batch_id=:b"),
                            {"c": result["candidates"], "m": result["matched"], "am": result["auto_merged"], "pr": result["probable"], "p": result["promoted"],
                             "d": json.dumps(result), "b": batch_id})
        session.commit()
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        if own_batch:
            session.execute(text("UPDATE staging.load_batch SET status='FAILED', finished_at=now(), detail=CAST(:d AS jsonb) WHERE batch_id=:b"), {"d": json.dumps({"error": str(exc)[:500]}), "b": batch_id})
            session.commit()
        raise
    return {"batch_id": batch_id, **result}


def preview(session: Session, payload: dict, limit: int = 10) -> dict:
    """§8.6 · match-preview: blocking + scoring contra los goldens sin persistir nada."""
    from app.matching.features import features_from_input

    engine = MatchingEngine(session)
    f0 = features_from_input(payload)
    feats = {sk: f for sk, f in load_features(session).items() if f["golden_status"] == "GOLDEN" and f["party_type"] == f0["party_type"]}
    index: dict[tuple[str, str], set[int]] = {}
    for sk, f in feats.items():
        for key in blocking_keys(f):
            index.setdefault(key, set()).add(sk)
    cands: set[int] = set()
    for key in blocking_keys(f0):
        cands |= index.get(key, set())
    out = []
    for sk in cands:
        score, detail = score_pair(f0, feats[sk], engine.rules)
        d = decide(score)
        if d != "NO_MATCH":
            out.append({"party_sk": sk, "score": score, "decision": d, "display_name": feats[sk].get("full_name_normalized") or feats[sk].get("legal_name_normalized"), "detail": detail})
    out.sort(key=lambda x: -x["score"])
    return {"compared": len(cands), "candidates": out[:limit], "persisted": False}
