# DEMO — Guion de demostración (se completa por fase)

El guion final recorre los 20 casos plantados de la especificación (§13, A–T) sobre
`make demo`. Cada fase agrega su tramo.

## Fase 0 · Plataforma

1. `make up` (o `make db-local && make migrate && make api`).
2. `curl localhost:8000/health` → `{"status":"ok","db":"ok","schemas_missing":[]}`.
3. Abrir `http://localhost:5173`: banner "Prototipo — datos sintéticos", estado del
   servicio en verde, módulos listados con su fase, leyenda de colores de las 8 capas.
4. `make test` → suite F0 en verde (salud, esquemas `rdm`/`mdm`/`staging`, `pg_trgm`,
   CLI con compuertas por fase).

## Fase 1 · RDM

1. `make seed` → "RDM sembrado" (segunda ejecución: 0 creados, la semilla es idempotente).
2. **Prueba canónica:** `GET /api/v1/rdm/homologate?system=SAP_CRM&field=GESCHL&value=1`
   → `{"catalog_code":"CAT_GENDER","value_code":"M"}`.
3. **Crosswalk:** `GET /api/v1/rdm/crosswalk?from_system=SAP_ECC_HCM&field=SEXKZ&value=1`
   → filas hacia `SAP_CRM/GESCHL/1` y `SF_EC/gender/M` (auto-join por `value_sk`).
4. **Inmutabilidad:** en `psql`, `UPDATE rdm.reference_value SET value_name='x' WHERE value_code='M'`
   → error "es inmutable; deprecar y crear uno nuevo (regla dura 3.7)".
5. **Deprecar:** `POST /api/v1/rdm/catalogs/CAT_CONTACT_FREQUENCY/values` con `QUARTERLY`,
   luego `POST .../QUARTERLY/deprecate` → `is_active=false`, `valid_to` fijado; recrear
   `QUARTERLY` → 409; `GET /api/v1/rdm/audit?entity=REFERENCE_VALUE` muestra INSERT y UPDATE con el actor.
6. **DIVIPOLA:** `GET /api/v1/rdm/catalogs/CAT_GEO_DIVIPOLA/values` → `11001 Bogotá D.C.`
   cuelga de `11 Bogotá D.C.`, nunca de `25 Cundinamarca` (regla dura 3.9).
7. **Homologación nueva (anticipo del caso P):** `POST /api/v1/rdm/mappings`
   `{system: SAP_CRM, field: RLTYP, catalog: CAT_PARTY_ROLE, source_value: ZPRV, value_code: VENDOR}`
   → el probador devuelve VENDOR; `POST /rdm/rehomologate` reprocesa los UNKNOWN (ver Fase 2).
8. **Regla del sistema exacto:** el mismo POST con `system: SAP_ECC` → 404.

## Fase 2 · Staging, MDM y pipeline

1. `python backend/cli.py synth-generate` → 1.580 registros en 5 fuentes, `manifest.json` con los casos.
2. `python backend/cli.py ingest --source all` → 5 lotes `OK` en `staging.load_batch`; una
   cuarentena (cliente SD sin documento) y dos códigos sin homologar en CRM (ZPRV y DIVIPOLA 99999).
3. `GET /api/v1/stats` → parties por estado (todos `CANDIDATE`), hallazgos por categoría, último
   lote por fuente.
4. **Caso I:** `GET /parties?external_id=<crm I>` → segmento AFFILIATION=A con fuente SAP_CRM;
   el candidato SD trae FINANCIAL_RISK=HIGH y el del portal COMMERCIAL=PREMIUM.
5. **Caso O:** golden del representante → relación `LEGAL_REP_OF` hacia la organización; la
   subsidiaria muestra `SUBSIDIARY_OF`; madre e hijo `PARENT_OF` y `CHILD_OF` (inversa generada);
   el `SPOUSE_OF` persona→organización aparece como hallazgo `VALIDITY` rechazado.
6. **Caso P:** el party con `RLTYP=ZPRV` tiene rol `UNKNOWN` y hallazgo con `target_table`;
   `POST /rdm/mappings` (ZPRV→VENDOR) y `POST /rdm/rehomologate?catalog=CAT_PARTY_ROLE` → rol
   VENDOR, hallazgo cerrado, audit `REHOMOLOGATE`, lote `REHOMOLOGATE` en la bitácora.
7. **Caso R:** cliente SD con `CR-1001` (activo), `CR-0990` (cerrado, con retención
   FINANCIAL_10Y a 10 años del cierre) y `EPS-77`; HOTEL y SUPERMERCADO rechazados como
   transaccionales; el candidato CRM trae CUOTA_MONETARIA.
8. **Caso G (anticipo):** `ingest --source ecc_sd --mode delta` → `unchanged_hash=287`, `loaded=0`.
9. **Caso J (anticipo):** el celular compartido es un solo `CONTACT_POINT` con dos vínculos:
   hijo OWNER y madre GUARDIAN; grupo familiar FAM-0007 con la madre como ancla.
10. **Caso T (anticipo):** cuatro teléfonos con origen, uso y confirmación; los de cobranza nacen
    con finalidades por contacto (COLLECTIONS sí, BENEFITS y COMMERCIAL no).

## Fases 3–5 (pendiente)

Casos A–H, K–N, Q, S según §13.
