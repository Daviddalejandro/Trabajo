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

## Fase 3 · Matching, survivorship y stewardship

1. `python backend/cli.py match` (o el matching implícito de `ingest`) → `candidates`, `buckets`,
   `compared`, `matched`, `auto_merged`, `probable`, `possible`, `promoted`, `forced_review`.
2. **Caso A:** las tres fuentes (SD, CRM, SF_EC) apuntan al mismo golden; `PARTY_MERGE_HISTORY`
   con `merge_type=AUTO`, `decided_by=engine.v1` y `pre_merge_snapshot`; `PARTY_SURVIVORSHIP`
   registra la fuente ganadora por atributo (nombre desde SF_EC, email más reciente).
3. **Caso B:** usuario del portal sin documento vs. golden CRM → `PROBABLE` en `GET /matches`;
   `POST /matches/{sk}/decision` sin justificación → 422; con `X-Role: STEWARD` y justificación → merge `STEWARD`.
4. **Caso C:** homónimos con fecha de nacimiento distinta → `POSSIBLE`, sin merge; `score_detail`
   muestra 0 puntos en documento y fecha.
5. **Caso D:** proveedor MM `LA ESPIGA` y cliente SD `La Espiga S.A.S.` con el mismo NIT → merge
   automático (NIT 50 + razón social 25 + municipio 10).
6. **Caso G:** `POST /pipeline/ecc_sd/run?mode=delta` → `loaded=0`, `matched=0`, `auto_merged=0`.
7. **Caso J:** el celular compartido madre/hijo (GUARDIAN) no aporta puntos ni bloquea (solo OWNER confirmado).
8. **Caso K:** par con fuentes de dos owners → dos `MATCH_REVIEW_TASK`; ambos owners aprueban →
   merge `OWNER_CONSENSUS`; un desacuerdo escala a Jefatura.
9. **Caso L:** `POST /parties/{sk}/unmerge` → filas restauradas desde el snapshot, par `NO_MATCH`
   resuelto, audit `UNMERGE`; una nueva corrida de matching no vuelve a fusionarlos.
10. **Caso N:** `POST /parties/match-preview` con el documento de un golden → candidato con
    `AUTO_MERGE` y evidencia, sin persistir (`persisted=false`).

## Fase 4 · Interfaz

Requisito: `make rebuild` (deja B y K pendientes) y `make api` + `cd frontend && npm run dev`.

1. **Tablero** (`#/`): goldens, candidatos, fusionados, pares en cola, última carga por fuente.
2. **Caso B desde la consola** (`#/stewardship`, actor `steward.mdm`): seleccionar el par con solo
   `WEB_PORTAL`; el desglose muestra 0 en documento y puntos plenos en apellido, nombre, fecha y
   correo; el botón **Fusionar** está deshabilitado hasta escribir la justificación; al fusionar
   aparece "Fusionado (STEWARD)" y el par sale de la cola.
3. **Caso K desde la consola**: el par `SF_EC · SAP_CRM` ofrece **Fusionar (pedir a owners)** →
   "En revisión: tareas creadas para SAP_CRM, SF_EC". Cambiar **Actúa como** a `steward.sfec`,
   pestaña **Tareas por owner**, decidir MERGE → "faltan otros owners (1/2)". Cambiar a
   `steward.crm`, decidir MERGE → "Fusionado (OWNER_CONSENSUS)". Variante: NO_MATCH de un owner
   resuelve el par; decisiones divididas escalan a `jefatura.gd` (rol JEFATURA, MANUAL_OVERRIDE).
4. **Unmerge desde la UI** (pestaña **Historial de merges**): abrir un merge `AUTO`, revisar las
   filas por tabla del `pre_merge_snapshot` y la auditoría por `merge_sk`, escribir la razón y
   **Deshacer merge** → filas restauradas, merge marcado REVERTIDO, par `NO_MATCH`.
5. **Admin RDM** (`#/rdm`): Contactabilidad → `CAT_CONTACT_FREQUENCY` → **Nuevo valor canónico**
   (la SK la asigna la base) → **deprecar** (confirmación; el código no se recicla). Homologaciones
   `SAP_CRM` → **Nueva homologación** `RLTYP` / `CAT_PARTY_ROLE` / `ZPRV` → `VENDOR`. **Rehomologar**:
   elegir `CAT_PARTY_ROLE`, el conteo previo muestra "Se corregirían ahora 1", ejecutar → "corregidos 1"
   (caso P). **Probador**: `SAP_CRM` / `GESCHL` / `1` → `CAT_GENDER.M`.
6. **Vista 360** (`#/party`): buscar `ESPIGA` (caso D) → las 8 capas en orden; la capa Core muestra
   la fuente ganadora por campo; Golden Record lista survivorship y el merge AUTO. Buscar el afiliado
   del caso R para ver roles por UES y vínculos de servicio debajo; el del caso T para ver los
   teléfonos de cobranza agrupados y marcados con sus finalidades por contacto.
7. `make test-e2e` reproduce 2–6 con Playwright (6 pruebas).

## Fase 5 · Cumplimiento embebido

`make demo` reconstruye todo, sincroniza el RNE, radica la consulta ARCO del caso Q e imprime la tabla de
los 20 casos (todos OK). Luego, con `make api` y la UI:

1. **Caso E** (`GET /parties/{sk}/contactability?purpose=COMMERCIAL`): todo contacto comercial → `CONSENT_REVOKED`.
2. **Caso H** (Vista 360 del titular): el celular muestra la marca RNE; PHONE/COMMERCIAL `RNE_EXCLUSION`,
   PHONE/COLLECTIONS y BENEFITS `ELIGIBLE` (crédito vigente; Ley 2300/2023 arts. 3 y 5).
3. **Caso J**: un solo `CONTACT_POINT` compartido; madre BENEFITS `ELIGIBLE` y COMMERCIAL
   `SHARED_CONTACT_RESTRICTED`; hijo COMMERCIAL `MINOR`.
4. **Caso T**: grupo "Aportados por cobranza" en la Vista 360; email COMMERCIAL `CONTACT_PURPOSE_DENIED`
   pese al canal permitido; referencia COMMERCIAL `THIRD_PARTY_CONTACT`; WRONG_PERSON `INVALID_CONTACT`.
   Acciones **confirmar por titular** y **habilitar COMMERCIAL** sobre el de cobranza → `ELIGIBLE`, auditado.
   `Cumplimiento → Audiencias` COMMERCIAL/PHONE devuelve un único número del titular; EMAIL ninguno.
5. **Caso S**: PHONE/COLLECTIONS `NO_ACTIVE_SERVICE`; `python backend/cli.py ingest --source ecc_sd --mode delta
   --file data/synth/ecc_sd_delta.csv` carga el crédito, fusiona por documento y deja COLLECTIONS `ELIGIBLE`.
6. **Caso M** (`Cumplimiento → Audiencias`): COMMERCIAL / EMAIL / AFFILIATE → excluye fallecidos, menores,
   sin consentimiento y canal denegado; el feed muestra la fila `AUDIENCE_RUN` con filtros y conteo.
7. **Caso F** (`Cumplimiento → ARCO`): CANCELLATION sobre el golden del caso A → vence en 15 días hábiles,
   consentimientos revocados, retención PURGE_ELIGIBLE, auditoría filtrable por `arco_request_id`;
   `Retención y purga` lo lista solo cuando no conserva vínculos de servicio activos; nada se borra.
8. **Caso Q** (`Cumplimiento → ARCO`, filtro Vencidas): la consulta radicada hace 12 días hábiles aparece
   OVERDUE; el fallecido tiene toda elegibilidad `DECEASED`.
9. **Feed de cambios**: `GET /changes?since=…` entrega party, entidad, acción y `golden_version` para SAP CDP.
10. `make export-drive` genera `docs/drive/` (diccionario, catálogos, matching, cumplimiento, evidencia,
    demo y resumen ejecutivo) para subir a la carpeta `MDM_RDM_Prototipo` de Google Drive.
