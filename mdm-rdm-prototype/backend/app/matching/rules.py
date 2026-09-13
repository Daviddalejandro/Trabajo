"""Pesos y reglas de matching (SPEC §8.2, §8.3) sembrados en mdm.MATCH_RULE versión 1.
`params` es JSON estructurado (umbral, puntaje parcial) para que la consola muestre la regla."""
from sqlalchemy import text
from sqlalchemy.orm import Session

RULES_V1 = {
    "PERSON": [
        ("document", 30, "EXACT", {"partial_other_type": 15, "note": "número igual con tipo distinto: +15"}),
        ("first_surname", 20, "JARO_WINKLER+SOUNDEX_ES", {"jw_min": 0.92}),
        ("first_name", 15, "JARO_WINKLER", {"jw_min": 0.90}),
        ("birth_date", 15, "EXACT_OR_1Y", {"partial_1y": 8}),
        ("second_surname", 10, "JARO_WINKLER", {"jw_min": 0.92}),
        ("email", 5, "EXACT", {}),
        ("phone", 3, "EXACT", {"requires": "OWNER+CONFIRMED_BY_TITULAR en ambos"}),
        ("municipality", 2, "EXACT", {}),
    ],
    "ORGANIZATION": [
        ("nit", 50, "EXACT+CHECK_DIGIT", {}),
        ("legal_name", 25, "JARO_WINKLER_TOKENS", {"jw_min": 0.90, "ignore": ["SAS", "S.A.S.", "LTDA", "S.A.", "SA", "DE COLOMBIA", "FUNDACION"]}),
        ("trade_name", 10, "JARO_WINKLER", {"jw_min": 0.90}),
        ("municipality", 10, "EXACT", {"fallback": "country"}),
        ("ciiu", 5, "EXACT", {}),
    ],
}
THRESHOLDS = {"AUTO_MERGE": 85, "PROBABLE": 70, "POSSIBLE": 50}
SOURCE_PRIORITY = ["SF_EC", "SAP_CRM", "SAP_ECC_SD", "SAP_ECC_MM", "CREDITO_CORE", "WEB_PORTAL"]
RULE_VERSION = 1


def ensure_match_rules(session: Session) -> int:
    """Idempotente: siembra la versión 1 si no existe. Devuelve filas creadas."""
    import json

    created = 0
    for entity, rules in RULES_V1.items():
        sk = session.execute(text("SELECT value_sk FROM rdm.vw_rdm_lookup WHERE catalog_code='CAT_PARTY_TYPE' AND value_code=:c"), {"c": entity}).scalar_one()
        for attr, weight, algo, params in rules:
            r = session.execute(text(
                "INSERT INTO mdm.match_rule (entity_type_cd, attribute, weight, algorithm, params, version) "
                "VALUES (:e, :a, :w, :alg, CAST(:p AS jsonb), :v) ON CONFLICT (entity_type_cd, attribute, version) DO NOTHING"),
                {"e": sk, "a": attr, "w": weight, "alg": algo, "p": json.dumps(params), "v": RULE_VERSION})
            created += r.rowcount
    return created


def load_rules(session: Session) -> dict[str, dict[str, dict]]:
    rows = session.execute(text("""
        SELECT t.value_code, r.attribute, r.weight, r.algorithm, r.params FROM mdm.match_rule r
        JOIN rdm.reference_value t ON t.value_sk = r.entity_type_cd WHERE r.is_active AND r.version = :v"""), {"v": RULE_VERSION}).all()
    out: dict[str, dict[str, dict]] = {"PERSON": {}, "ORGANIZATION": {}}
    for entity, attr, weight, algo, params in rows:
        out[entity][attr] = {"weight": float(weight), "algorithm": algo, "params": params or {}}
    return out
