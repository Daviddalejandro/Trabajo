"""Consola RDM: las cinco capas desde la API tal como las opera un usuario de Gobierno de Datos.
Recorrido completo (dominio → catálogo → campos personalizados → valores → sistema fuente → integración →
homologaciones versionadas → deprecación → auditoría), validaciones del diccionario de campos y reglas duras
(§3.4 sistema registrado, §3.7 inmutabilidad, RDM de arriba hacia abajo)."""
import pytest
from sqlalchemy import text

from app.core.db import engine

H = {"X-Actor": "pytest-rdm"}
SUF = "PYT"


@pytest.fixture(scope="module", autouse=True)
def cleanup_console_fixtures():
    """Al terminar el módulo retira lo creado (dominio, catálogo, campos, valores, sistema, integración, mapeos)
    para que los inventarios de F1 (43 catálogos, 6 dominios, 8 sistemas) valgan en cualquier orden de ejecución.
    Solo en pruebas: en operación el RDM nunca borra, depreca."""
    yield
    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.actor', 'pytest-rdm-cleanup', true)"))
        conn.execute(text("""
            DELETE FROM rdm.source_value_mapping WHERE integration_sk IN (
                SELECT i.integration_sk FROM rdm.catalog_source_integration i JOIN rdm.source_system s ON s.source_system_sk = i.source_system_sk
                WHERE s.source_system_cd = :sys)"""), {"sys": f"APP_MOVIL_{SUF}"})
        conn.execute(text("DELETE FROM rdm.catalog_source_integration WHERE source_system_sk IN (SELECT source_system_sk FROM rdm.source_system WHERE source_system_cd = :sys)"), {"sys": f"APP_MOVIL_{SUF}"})
        conn.execute(text("DELETE FROM rdm.source_system WHERE source_system_cd = :sys"), {"sys": f"APP_MOVIL_{SUF}"})
        conn.execute(text("DELETE FROM rdm.reference_field_value WHERE value_sk IN (SELECT v.value_sk FROM rdm.reference_value v JOIN rdm.catalog c ON c.catalog_sk = v.catalog_sk WHERE c.catalog_code = :cat)"), {"cat": f"CAT_CANAL_PREFERIDO_{SUF}"})
        conn.execute(text("DELETE FROM rdm.reference_value WHERE catalog_sk IN (SELECT catalog_sk FROM rdm.catalog WHERE catalog_code = :cat)"), {"cat": f"CAT_CANAL_PREFERIDO_{SUF}"})
        conn.execute(text("DELETE FROM rdm.catalog_attribute WHERE catalog_sk IN (SELECT catalog_sk FROM rdm.catalog WHERE catalog_code = :cat) OR field_code = :f"), {"cat": f"CAT_CANAL_PREFERIDO_{SUF}", "f": f"abreviatura_{SUF.lower()}"})
        conn.execute(text("DELETE FROM rdm.catalog WHERE catalog_code = :cat"), {"cat": f"CAT_CANAL_PREFERIDO_{SUF}"})
        conn.execute(text("DELETE FROM rdm.domain WHERE domain_code = :d"), {"d": f"EXPERIENCIA_{SUF}"})


def test_overview_counts_every_layer(client):
    o = client.get("/api/v1/rdm/overview").json()
    assert o["domains"] >= 6 and o["catalogs"] >= 43 and o["values_active"] > 200
    assert o["attributes"] > 0 and o["attribute_values"] > 0        # diccionario poblado desde el EAV sembrado (f7_0008)
    assert o["source_systems"] >= 8 and o["integrations"] > 0 and o["mappings_current"] > 0 and o["audit_entries"] > 0


def test_backfilled_attribute_dictionary_infers_types(client):
    attrs = {a["field_code"]: a for a in client.get("/api/v1/rdm/catalogs/CAT_ID_TYPE/attributes").json()}
    assert attrs["validation_regex"]["data_type"] == "REGEX"
    assert attrs["has_check_digit"]["data_type"] == "BOOLEAN"
    assert attrs["applies_to"]["data_type"] == "CODE"
    assert attrs["validation_regex"]["values_with_data"] >= 4
    d = client.get("/api/v1/rdm/catalogs/CAT_ID_TYPE/detail").json()
    assert d["catalog_code"] == "CAT_ID_TYPE" and d["active_values"] >= 4 and len(d["attributes"]) == 3


def test_full_rdm_lifecycle_from_the_console(client):
    # 1 · dominio
    r = client.post("/api/v1/rdm/domains", json={"domain_code": f"EXPERIENCIA_{SUF}", "domain_name": "Experiencia del afiliado"}, headers=H)
    assert r.status_code == 201, r.text
    assert client.post("/api/v1/rdm/domains", json={"domain_code": f"EXPERIENCIA_{SUF}", "domain_name": "x"}, headers=H).status_code == 409
    assert client.post("/api/v1/rdm/domains", json={"domain_code": "mal código", "domain_name": "x"}, headers=H).status_code == 422
    # 2 · catálogo (de arriba hacia abajo: el dominio debe existir; convención CAT_)
    cat = f"CAT_CANAL_PREFERIDO_{SUF}"
    assert client.post("/api/v1/rdm/catalogs", json={"catalog_code": cat, "catalog_name": "Canal preferido", "domain_code": "NO_EXISTE"}, headers=H).status_code == 404
    assert client.post("/api/v1/rdm/catalogs", json={"catalog_code": "CANAL", "catalog_name": "x", "domain_code": f"EXPERIENCIA_{SUF}"}, headers=H).status_code == 422
    r = client.post("/api/v1/rdm/catalogs", json={"catalog_code": cat, "catalog_name": "Canal preferido de atención", "domain_code": f"EXPERIENCIA_{SUF}",
                                                 "official_source": "Política de servicio al afiliado"}, headers=H)
    assert r.status_code == 201, r.text
    # 3 · campos personalizados
    for body in ({"field_code": "horario", "field_name": "Horario de atención", "data_type": "TEXT"},
                 {"field_code": "costo_contacto", "field_name": "Costo por contacto (COP)", "data_type": "NUMBER"},
                 {"field_code": "requiere_consentimiento", "field_name": "Requiere consentimiento previo", "data_type": "BOOLEAN", "is_required": True}):
        assert client.post(f"/api/v1/rdm/catalogs/{cat}/attributes", json=body, headers=H).status_code == 201
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/attributes", json={"field_code": "horario", "field_name": "dup"}, headers=H).status_code == 409
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/attributes", json={"field_code": "MAL", "field_name": "x"}, headers=H).status_code == 422
    # 4 · valores: el diccionario valida tipos y obligatorios
    ok = {"value_code": "WHATSAPP", "value_name": "WhatsApp", "attributes": {"horario": "07:00-19:00", "costo_contacto": "120", "requiere_consentimiento": "true"}}
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/values", json=ok, headers=H).status_code == 201
    bad_type = {"value_code": "EMAIL", "value_name": "Correo", "attributes": {"costo_contacto": "barato", "requiere_consentimiento": "false"}}
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/values", json=bad_type, headers=H).status_code == 409
    missing = {"value_code": "EMAIL", "value_name": "Correo", "attributes": {"costo_contacto": "15"}}
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/values", json=missing, headers=H).status_code == 409
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/values", json={"value_code": "EMAIL", "value_name": "Correo electrónico", "attributes": {"requiere_consentimiento": "false"}}, headers=H).status_code == 201
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/values", json={"value_code": "SMS", "value_name": "Mensaje de texto", "attributes": {"requiere_consentimiento": "true"}}, headers=H).status_code == 201
    # atributos corregibles; código y nombre no (regla dura §3.7)
    r = client.put(f"/api/v1/rdm/catalogs/{cat}/values/EMAIL/attributes", json={"attributes": {"costo_contacto": "15", "horario": ""}}, headers=H)
    assert r.status_code == 200 and r.json()["attributes"] == {"costo_contacto": "15", "requiere_consentimiento": "false"}
    assert client.put(f"/api/v1/rdm/catalogs/{cat}/values/EMAIL/attributes", json={"attributes": {"costo_contacto": "x"}}, headers=H).status_code == 422
    # 5 · sistema fuente (regla dura §3.4: la integración exige el sistema registrado)
    assert client.post("/api/v1/rdm/integrations", json={"catalog": cat, "system": f"APP_MOVIL_{SUF}", "source_field": "canal_pref"}, headers=H).status_code == 404
    r = client.post("/api/v1/rdm/source-systems", json={"source_system_cd": f"APP_MOVIL_{SUF}", "name": "App móvil", "data_owner": "Canales Digitales", "data_steward": "steward.app"}, headers=H)
    assert r.status_code == 201, r.text
    # 6 · integración y homologaciones
    r = client.post("/api/v1/rdm/integrations", json={"catalog": cat, "system": f"APP_MOVIL_{SUF}", "source_field": "canal_pref"}, headers=H)
    assert r.status_code == 201 and r.json()["created"] is True
    assert client.post("/api/v1/rdm/integrations", json={"catalog": cat, "system": f"APP_MOVIL_{SUF}", "source_field": "canal_pref"}, headers=H).json()["created"] is False
    for sv, code in (("wa", "WHATSAPP"), ("mail", "EMAIL"), ("sms", "SMS")):
        assert client.post("/api/v1/rdm/mappings", json={"system": f"APP_MOVIL_{SUF}", "field": "canal_pref", "catalog": cat, "source_value": sv, "value_code": code}, headers=H).status_code == 201
    h = client.get("/api/v1/rdm/homologate", params={"system": f"APP_MOVIL_{SUF}", "field": "canal_pref", "value": "wa"}).json()
    assert h["value_code"] == "WHATSAPP" and h["catalog_code"] == cat
    ints = client.get("/api/v1/rdm/integrations", params={"catalog": cat}).json()
    assert len(ints) == 1 and ints[0]["mappings_current"] == 3
    # 7 · ciclo de vida: deprecar SMS, crear SMS_RCS y re-apuntar la homologación (versionada, nunca editada)
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/values/SMS/deprecate", headers=H).status_code == 200
    assert client.post("/api/v1/rdm/mappings", json={"system": f"APP_MOVIL_{SUF}", "field": "canal_pref", "catalog": cat, "source_value": "sms", "value_code": "SMS"}, headers=H).status_code == 404   # canónico deprecado
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/values", json={"value_code": "SMS_RCS", "value_name": "Mensajería RCS", "attributes": {"requiere_consentimiento": "true"}}, headers=H).status_code == 201
    assert client.post("/api/v1/rdm/mappings", json={"system": f"APP_MOVIL_{SUF}", "field": "canal_pref", "catalog": cat, "source_value": "sms", "value_code": "SMS_RCS"}, headers=H).status_code == 201
    hist = client.get("/api/v1/rdm/mappings/history", params={"system": f"APP_MOVIL_{SUF}", "field": "canal_pref", "catalog": cat, "source_value": "sms"}).json()
    assert [x["value_code"] for x in hist] == ["SMS_RCS", "SMS"] and hist[0]["valid_to"] is None and hist[1]["valid_to"] is not None
    # cerrar una homologación: el valor fuente vuelve a UNKNOWN
    assert client.post("/api/v1/rdm/mappings/retire", json={"system": f"APP_MOVIL_{SUF}", "field": "canal_pref", "catalog": cat, "source_value": "mail"}, headers=H).status_code == 200
    assert client.get("/api/v1/rdm/homologate", params={"system": f"APP_MOVIL_{SUF}", "field": "canal_pref", "value": "mail"}).status_code == 404
    assert client.post("/api/v1/rdm/mappings/retire", json={"system": f"APP_MOVIL_{SUF}", "field": "canal_pref", "catalog": cat, "source_value": "mail"}, headers=H).status_code == 404
    # retirar un campo personalizado conserva los datos EAV
    assert client.post(f"/api/v1/rdm/catalogs/{cat}/attributes/horario/retire", headers=H).status_code == 200
    assert [a["field_code"] for a in client.get(f"/api/v1/rdm/catalogs/{cat}/attributes").json()] == ["costo_contacto", "requiere_consentimiento"]
    v = {x["value_code"]: x for x in client.get(f"/api/v1/rdm/catalogs/{cat}/values").json()["items"]}
    assert v["WHATSAPP"]["attributes"]["horario"] == "07:00-19:00"
    # 8 · auditoría: las cinco capas quedaron con el actor de la sesión
    audit = client.get("/api/v1/rdm/audit/detail", params={"limit": 200}).json()
    mine = {(a["entity"], a["action"]) for a in audit if a["actor"] == "pytest-rdm"}
    for expected in (("DOMAIN", "INSERT"), ("CATALOG", "INSERT"), ("CATALOG_ATTRIBUTE", "INSERT"), ("CATALOG_ATTRIBUTE", "UPDATE"),
                     ("REFERENCE_VALUE", "INSERT"), ("REFERENCE_VALUE", "UPDATE"), ("REFERENCE_FIELD_VALUE", "INSERT"),
                     ("SOURCE_SYSTEM", "INSERT"), ("CATALOG_SOURCE_INTEGRATION", "INSERT"), ("SOURCE_VALUE_MAPPING", "INSERT"), ("SOURCE_VALUE_MAPPING", "UPDATE")):
        assert expected in mine, expected
    assert all("new_value" in a for a in audit[:5])


def test_required_attribute_cannot_be_declared_over_incomplete_values(client):
    # CAT_GENDER no tiene EAV: exigir un campo nuevo a valores existentes se rechaza hasta cargarlo
    r = client.post("/api/v1/rdm/catalogs/CAT_GENDER/attributes", json={"field_code": f"abreviatura_{SUF.lower()}", "field_name": "Abreviatura", "is_required": True}, headers=H)
    assert r.status_code == 422 and "obligatorio" in r.text
    r = client.post("/api/v1/rdm/catalogs/CAT_GENDER/attributes", json={"field_code": f"abreviatura_{SUF.lower()}", "field_name": "Abreviatura"}, headers=H)
    assert r.status_code == 201 and r.json()["is_required"] is False
