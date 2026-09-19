"""F1 · criterios de aceptación (SPEC §14): prueba canónica por vista y endpoint, UPDATE a
canónico activo rechazado, deprecar funciona, crosswalk SEXKZ=1 ↔ GESCHL=1, vista tipada
de relaciones, ningún mapeo a sistema no registrado, 43 catálogos poblados."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.db import engine
from app.rdm import seed_data
from app.rdm.seed import seed_rdm
from app.core.db import SessionLocal


def q(sql, **p):
    with engine.connect() as conn:
        return conn.execute(text(sql), p)


# ------------------------------------------------------------------ inventario
def test_43_catalogs_created_and_populated():
    assert q("SELECT count(*) FROM rdm.catalog").scalar_one() == 43
    empty = q("""SELECT c.catalog_code FROM rdm.catalog c
                 WHERE NOT EXISTS (SELECT 1 FROM rdm.reference_value v WHERE v.catalog_sk=c.catalog_sk)""").scalars().all()
    assert empty == [], f"catálogos sin valores: {empty}"


def test_technical_members_global():
    rows = q("SELECT value_sk, value_code, catalog_sk FROM rdm.reference_value WHERE value_sk <= 0 ORDER BY value_sk").all()
    assert [(r[0], r[1], r[2]) for r in rows] == [(-1, "NOT_APPLICABLE", None), (0, "UNKNOWN", None)]
    # ningún valor de negocio puede carecer de catálogo
    assert q("SELECT count(*) FROM rdm.reference_value WHERE value_sk > 0 AND catalog_sk IS NULL").scalar_one() == 0


def test_seed_is_idempotent():
    with SessionLocal() as s:
        rep = seed_rdm(s); s.commit()
    assert rep.values == 0 and rep.catalogs == 0 and rep.mappings == 0, rep.as_dict()


def test_mdm_entity_catalog_has_29_values():
    assert q("""SELECT count(*) FROM rdm.vw_rdm_lookup WHERE catalog_code='CAT_MDM_ENTITY' AND is_active""").scalar_one() == 29
    assert len(seed_data.MDM_ENTITIES) == 29


# ------------------------------------------------------------------ prueba canónica
def test_canonical_view_geschl_1_is_M():
    r = q("""SELECT value_code FROM rdm.vw_rdm_source_to_canonical
             WHERE source_system_cd='SAP_CRM' AND source_field='GESCHL' AND source_value='1'""").scalar_one()
    assert r == "M"


def test_canonical_endpoint_geschl_1_is_M(client):
    r = client.get("/api/v1/rdm/homologate", params={"system": "SAP_CRM", "field": "GESCHL", "value": "1"})
    assert r.status_code == 200, r.text
    assert r.json()["value_code"] == "M" and r.json()["catalog_code"] == "CAT_GENDER"


def test_unmapped_code_returns_404_unknown(client):
    r = client.get("/api/v1/rdm/homologate", params={"system": "SAP_CRM", "field": "RLTYP", "value": "ZPRV"})
    assert r.status_code == 404 and "UNKNOWN" in r.text


# ------------------------------------------------------------------ crosswalk
def test_crosswalk_sexkz_geschl():
    rows = q("""SELECT to_system_cd, to_field, to_value FROM rdm.vw_rdm_crosswalk
                WHERE from_system_cd='SAP_ECC_HCM' AND from_field='SEXKZ' AND from_value='1'""").all()
    assert ("SAP_CRM", "GESCHL", "1") in {tuple(r) for r in rows}
    rows = q("""SELECT to_system_cd, to_field, to_value FROM rdm.vw_rdm_crosswalk
                WHERE from_system_cd='SAP_CRM' AND from_field='GESCHL' AND from_value='1'""").all()
    assert ("SAP_ECC_HCM", "SEXKZ", "1") in {tuple(r) for r in rows}


def test_crosswalk_endpoint(client):
    r = client.get("/api/v1/rdm/crosswalk", params={"from_system": "SAP_ECC_HCM", "field": "SEXKZ", "value": "1", "to_system": "SF_EC"})
    assert r.status_code == 200 and r.json()[0]["to_value"] == "M"


# ------------------------------------------------------------------ inmutabilidad
def test_update_active_canonical_is_rejected():
    with pytest.raises(DBAPIError) as e, engine.begin() as conn:
        conn.execute(text("UPDATE rdm.reference_value SET value_name='Masculino (editado)' "
                          "WHERE value_code='M' AND catalog_sk=(SELECT catalog_sk FROM rdm.catalog WHERE catalog_code='CAT_GENDER')"))
    assert "inmutable" in str(e.value)


def test_deprecate_then_cannot_reactivate_and_audited(client):
    r = client.post("/api/v1/rdm/catalogs/CAT_CONTACT_FREQUENCY/values", json={"value_code": "QUARTERLY", "value_name": "Trimestral"},
                    headers={"X-Actor": "steward.pruebas"})
    assert r.status_code == 201, r.text
    r = client.post("/api/v1/rdm/catalogs/CAT_CONTACT_FREQUENCY/values/QUARTERLY/deprecate", headers={"X-Actor": "steward.pruebas"})
    assert r.status_code == 200 and r.json()["is_active"] is False and r.json()["valid_to"] is not None
    # deprecar dos veces → 404; recrear el mismo código → 409 (no se recicla)
    assert client.post("/api/v1/rdm/catalogs/CAT_CONTACT_FREQUENCY/values/QUARTERLY/deprecate").status_code == 404
    r = client.post("/api/v1/rdm/catalogs/CAT_CONTACT_FREQUENCY/values", json={"value_code": "QUARTERLY", "value_name": "Otra vez"})
    assert r.status_code == 409
    with pytest.raises(DBAPIError), engine.begin() as conn:
        conn.execute(text("UPDATE rdm.reference_value SET is_active = TRUE WHERE value_code='QUARTERLY'"))
    audit = q("""SELECT action, actor FROM rdm.rdm_audit_log a
                 JOIN rdm.reference_value v ON v.value_sk = a.entity_sk
                 WHERE a.entity='REFERENCE_VALUE' AND v.value_code='QUARTERLY' ORDER BY a.audit_sk""").all()
    assert [tuple(r) for r in audit] == [("INSERT", "steward.pruebas"), ("UPDATE", "steward.pruebas")]


# ------------------------------------------------------------------ vistas tipadas y jerarquías
def test_relationship_typed_view():
    rows = {r[0]: (r[1], r[2], r[3]) for r in q(
        "SELECT value_code, from_party_type, to_party_type, inverse_code FROM rdm.vw_rdm_cat_relationship_type").all()}
    assert len(rows) == 12                                   # 10 de §6 + GUARANTOR_OF / GUARANTEED_BY (codeudor, conjunto de validación)
    assert rows["PARENT_OF"] == ("PERSON", "PERSON", "CHILD_OF")
    assert rows["GUARANTOR_OF"] == ("ANY", "ANY", "GUARANTEED_BY")
    assert rows["LEGAL_REP_OF"] == ("PERSON", "ORGANIZATION", "")
    assert rows["SUBSIDIARY_OF"] == ("ORGANIZATION", "ORGANIZATION", "")


def test_divipola_rule_11_is_bogota_not_cundinamarca():
    rows = {r[0]: (r[1], r[2], r[3]) for r in q(
        "SELECT value_code, level_code, department_code, locality_type FROM rdm.vw_rdm_cat_geo_divipola").all()}
    assert rows["11"] == ("DEPARTAMENTO", "11", None)
    assert rows["11001"] == ("MUNICIPIO", "11", "CABECERA")
    assert rows["25754"][1] == "25" and rows["11001"][1] != "25"


def test_id_type_view_nit_check_digit():
    rows = {r[0]: (r[1], r[2]) for r in q("SELECT value_code, applies_to, has_check_digit FROM rdm.vw_rdm_cat_id_type").all()}
    assert rows["NIT"] == ("ORGANIZATION", True) and rows["CC"] == ("PERSON", False)


def test_service_hierarchy_and_kind():
    rows = q("""SELECT l.value_code, l.parent_value_code, f.field_value FROM rdm.vw_rdm_lookup l
                JOIN rdm.reference_field_value f ON f.value_sk=l.value_sk AND f.field_code='service_kind'
                WHERE l.catalog_code='CAT_SERVICE'""").all()
    kinds = {r[0]: (r[1], r[2]) for r in rows}
    assert kinds["CREDITO_SOCIAL"] == ("CREDITO", "PERSISTENT") and kinds["PISCILAGO"] == ("RECREACION", "TRANSACTIONAL")
    assert kinds["HOTEL"] == ("HOTELERIA_TURISMO", "TRANSACTIONAL")


def test_purpose_requires_consent_type_eav():
    rows = {r[0]: (r[1], r[2]) for r in q("""
        SELECT l.value_code, a.field_value, b.field_value FROM rdm.vw_rdm_lookup l
        JOIN rdm.reference_field_value a ON a.value_sk=l.value_sk AND a.field_code='required_consent_type'
        JOIN rdm.reference_field_value b ON b.value_sk=l.value_sk AND b.field_code='rne_applies'
        WHERE l.catalog_code='CAT_CONTACT_PURPOSE'""").all()}
    assert rows == {"COLLECTIONS": ("DATA_PROCESSING", "false"), "BENEFITS": ("DATA_PROCESSING", "false"),
                    "COMMERCIAL": ("COMMERCIAL", "true")}


# ------------------------------------------------------------------ regla 3.4: sistema exacto
def test_no_mapping_to_unregistered_system():
    systems = set(q("SELECT source_system_cd FROM rdm.source_system").scalars().all())
    assert "SAP_ECC" not in systems and {"SAP_ECC_HCM", "SAP_ECC_SD", "SAP_ECC_MM", "SAP_CRM", "SF_EC", "WEB_PORTAL", "MDM_CONSOLE", "CREDITO_CORE"} == systems   # MDM_CONSOLE (F5) y CREDITO_CORE (validación)
    used = set(q("SELECT DISTINCT source_system_cd FROM rdm.vw_rdm_source_to_canonical").scalars().all())
    assert used <= systems
    assert q("SELECT is_prototype_active FROM rdm.source_system WHERE source_system_cd='SAP_ECC_HCM'").scalar_one() is False


def test_mapping_api_rejects_unknown_system_and_replaces_current(client):
    r = client.post("/api/v1/rdm/mappings", json={"system": "SAP_ECC", "field": "LAND1", "catalog": "CAT_COUNTRY",
                                                   "source_value": "CO", "value_code": "COL"})
    assert r.status_code == 404
    # nuevo mapeo (caso P): RLTYP=ZPRV → VENDOR
    r = client.post("/api/v1/rdm/mappings", json={"system": "SAP_CRM", "field": "RLTYP", "catalog": "CAT_PARTY_ROLE",
                                                   "source_value": "ZPRV", "value_code": "VENDOR"}, headers={"X-Actor": "steward.crm"})
    assert r.status_code == 201 and r.json()["created"] is True
    assert client.get("/api/v1/rdm/homologate", params={"system": "SAP_CRM", "field": "RLTYP", "value": "ZPRV"}).json()["value_code"] == "VENDOR"
    # cambiar el canónico cierra el vigente y crea uno nuevo (nunca edita)
    r = client.post("/api/v1/rdm/mappings", json={"system": "SAP_CRM", "field": "RLTYP", "catalog": "CAT_PARTY_ROLE",
                                                   "source_value": "ZPRV", "value_code": "CUSTOMER"})
    assert r.status_code == 201
    hist = q("""SELECT count(*) FILTER (WHERE valid_to IS NULL), count(*) FROM rdm.source_value_mapping m
                JOIN rdm.catalog_source_integration i ON i.integration_sk=m.integration_sk
                WHERE i.source_field='RLTYP' AND m.source_value='ZPRV'""").one()
    assert tuple(hist) == (1, 2)


# ------------------------------------------------------------------ navegación y paginación
def test_labels_endpoint_gives_spanish_names_per_catalog(client):
    lab = client.get("/api/v1/rdm/labels").json()
    assert lab["CAT_PARTY_ROLE"]["EMPLOYEE"] == "Empleado" and lab["CAT_RELATIONSHIP_TYPE"]["SPOUSE_OF"]
    assert lab["CAT_SEGMENT_TYPE"]["FINANCIAL_RISK"] == "Riesgo financiero" and lab["CAT_SEGMENT_TYPE"]["LOW"] == "Bajo"
    assert lab["SOURCE_SYSTEM"]["SAP_CRM"].startswith("SAP CRM") and len(lab) >= 44


def test_navigation_endpoints(client):
    d = client.get("/api/v1/rdm/domains").json()
    assert {x["domain_code"] for x in d} == {"DEMOGRAPHICS", "GEOGRAPHY", "GOVERNANCE", "CONTACT", "MDM_OPS", "BUSINESS"}
    c = client.get("/api/v1/rdm/catalogs", params={"domain": "GEOGRAPHY"}).json()
    assert {x["catalog_code"] for x in c} == {"CAT_GEO_DIVIPOLA", "CAT_COUNTRY", "CAT_GEOCODING_STATUS"}
    v = client.get("/api/v1/rdm/catalogs/CAT_MDM_ENTITY/values", params={"limit": 10}).json()
    assert v["items"][0]["value_code"] == "UNKNOWN" and v["items"][1]["value_code"] == "NOT_APPLICABLE"
    assert len(v["items"]) == 12 and v["next_cursor"] is not None
    v2 = client.get("/api/v1/rdm/catalogs/CAT_MDM_ENTITY/values", params={"limit": 10, "cursor": v["next_cursor"]}).json()
    assert v2["items"][0]["technical"] is False
    assert client.get("/api/v1/rdm/catalogs/CAT_NOPE/values").status_code == 404
    r = client.post("/api/v1/rdm/rehomologate", params={"catalog": "CAT_GENDER"})
    assert r.status_code == 200 and r.json()["candidates"] == 0   # F2: sin UNKNOWN de género pendientes
