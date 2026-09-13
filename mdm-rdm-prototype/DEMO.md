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
   → el probador devuelve VENDOR; `POST /rdm/rehomologate` responde 501 hasta la Fase 2.
8. **Regla del sistema exacto:** el mismo POST con `system: SAP_ECC` → 404.

## Fases 2–5 (pendiente)

Casos A–T según §13.
