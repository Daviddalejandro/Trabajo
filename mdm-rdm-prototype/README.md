# MDM/RDM in-house · Colsubsidio · Dominio Party — Prototipo funcional

Prototipo demostrable del Master Data Management (MDM) y Reference Data Management
(RDM) del dominio Party, construido por fases según
[`SPEC_PROTOTIPO_MDM_RDM_PARTY.md`](../SPEC_PROTOTIPO_MDM_RDM_PARTY.md) (v2.0).
Opera **exclusivamente con datos sintéticos**.

## Estado por fase

| Fase | Contenido | Estado |
|---|---|---|
| F0 | Scaffolding: db + api + ui, Alembic, Makefile, healthchecks, PostgreSQL local sin Docker | ✅ tests en verde |
| F1 | RDM: 43 catálogos (263 valores), 6 sistemas fuente, 24 homologaciones, 6 vistas, trigger de inmutabilidad, auditoría por trigger, endpoints RDM | ✅ 25 tests en verde |
| F2 | Staging (5 RAW + `LOAD_BATCH`) + `mdm` (29 tablas, triggers de auditoría y de unicidad golden), generador sintético (1.580 registros, 21 casos plantados), pipeline de 7 etapas con carga de candidatos, `rehomologate`, API de parties y stats | ✅ 42 tests en verde |
| F3 | Matching, survivorship, merge/unmerge, match-preview | pendiente |
| F4 | Consola de Stewardship, Admin RDM, Vista 360 | pendiente |
| F5 | Cumplimiento, audiencias, ARCO, RNE, `make demo`, export a Drive | pendiente |

## Arranque

### Opción A · Docker (máquina del autor)

```bash
cp .env.example .env
make up            # db (PostgreSQL 16) + api (FastAPI :8000) + ui (Vite :5173)
curl localhost:8000/health
```

### Opción B · Sin Docker (entorno remoto de Claude Code o cualquier Linux con PostgreSQL 16)

```bash
make db-local      # clúster local en 127.0.0.1:5433 con initdb/pg_ctl (.pgdata/)
pip install -r backend/requirements.txt
make migrate       # alembic upgrade head
make api           # uvicorn en :8000
cd frontend && npm install && npm run dev   # UI en :5173
```

`DATABASE_URL` por defecto: `postgresql+psycopg://mdm@127.0.0.1:5433/mdm_prototype`.

## Pruebas

```bash
make test          # pytest del backend (migra a head y valida criterios de la fase)
make test-frontend # build de la UI
```

## Estructura

```
mdm-rdm-prototype/
├── docker-compose.yml     db + api + ui
├── Makefile               up | db-local | migrate | seed | demo | test | export-drive
├── scripts/db_local.sh    PostgreSQL 16 local sin Docker
├── docs/reference/        diccionario maestro y diagramas (solo lectura)
├── docs/drive/            entregables exportados a Google Drive por fase (§17)
├── backend/
│   ├── alembic/versions/  una migración por fase (f0_0000_schemas, ...)
│   ├── app/api            routers FastAPI (§11)
│   ├── app/core           config, db, auditoría
│   ├── app/models         SQLAlchemy: rdm / mdm / staging
│   ├── app/pipeline       7 etapas (§7)
│   ├── app/matching       blocking, scoring, umbrales, preview (§8)
│   ├── app/stewardship    decisiones, tareas por owner, merge/unmerge (§8.5)
│   ├── app/survivorship   estrategias (§9)
│   ├── app/compliance     elegibilidad, audiencias, ARCO, retención (§10)
│   ├── app/synth          generador sintético (§13)
│   ├── cli.py             comandos operativos (nombres de los DAGs)
│   └── tests/             pytest por fase
└── frontend/src/          Stewardship, Admin RDM, Vista 360 (React + Vite + Tailwind)
```

## RDM (Fase 1)

```bash
make migrate && make seed          # crea rdm.* y siembra 43 catálogos (idempotente)
curl "localhost:8000/api/v1/rdm/homologate?system=SAP_CRM&field=GESCHL&value=1"   # → M
curl "localhost:8000/api/v1/rdm/crosswalk?from_system=SAP_ECC_HCM&field=SEXKZ&value=1"
curl "localhost:8000/api/v1/rdm/catalogs?domain=GEOGRAPHY"
curl "localhost:8000/api/v1/rdm/catalogs/CAT_SERVICE/values"
```

Decisiones de implementación de la Fase 1 (todas dentro de las reglas duras):

- **Miembros técnicos globales.** `value_sk 0 = UNKNOWN` y `-1 = NOT_APPLICABLE` son dos
  filas únicas sin catálogo (`CHECK (value_sk <= 0) = (catalog_sk IS NULL)`), insertadas una
  sola vez con `OVERRIDING SYSTEM VALUE`. Todo `_cd` del MDM tiene `DEFAULT 0` y FK a ellas;
  la API los antepone en la lista de valores de cualquier catálogo (regla dura §3.3).
- **Inmutabilidad por trigger.** `UPDATE` de `value_code`/`value_name`/`catalog_sk` sobre un
  valor activo falla; deprecar fija `valid_to`; un valor deprecado no se reactiva ni se
  recicla (regla dura §3.7).
- **Auditoría por trigger**, no por aplicación: `catalog`, `reference_value`,
  `reference_field_value` y `source_value_mapping` escriben `rdm_audit_log` con el actor
  de `SET LOCAL app.actor` (cabecera `X-Actor` en la API).
- **Un mapeo vigente por (integración, valor fuente)**: cambiar el canónico cierra el
  vigente (`valid_to`) y crea uno nuevo; nunca se edita.
- **Sistema fuente exacto** (regla dura §3.4): `SAP_ECC` no existe; SEXKZ se registra bajo
  `SAP_ECC_HCM` (inactivo en el prototipo) para que el crosswalk SEXKZ ↔ GESCHL sea verificable.
- `CAT_PARTY_SUB_ROLE` siembra 12 sub-roles (2 por rol principal) para coincidir con la
  cifra del diccionario maestro.

## Staging, MDM y pipeline (Fase 2)

```bash
make migrate && make seed                       # rdm + staging + mdm (29 tablas)
python backend/cli.py synth-generate            # data/synth/*.csv + manifest.json (seed fija)
python backend/cli.py ingest --source all       # 5 fuentes, 7 etapas, bitácora LOAD_BATCH
python backend/cli.py ingest --source ecc_sd --mode delta   # segunda corrida: todo UNCHANGED por hash
python backend/cli.py rehomologate --catalog CAT_PARTY_ROLE  # reprocesa los UNKNOWN (§7.2)
python backend/cli.py reset-mdm --yes           # vacía staging y mdm; el RDM se conserva
curl "localhost:8000/api/v1/parties?external_id=0007000012"
curl "localhost:8000/api/v1/parties/12/golden"   # las 8 capas
curl "localhost:8000/api/v1/stats"
```

Decisiones de implementación de la Fase 2:

- **Crosswalk sin matching.** En F2 la etapa 6 resuelve solo por XREF: hit → actualización directa
  del party (regla dura §3.11, "replace source slice" de las filas de esa fuente); miss → el
  registro se crea como party `CANDIDATE` con su XREF. El matching de F3 decide merges entre
  candidatos y goldens. Por eso una misma persona presente en tres fuentes son hoy tres
  candidatos; el caso I se verifica por candidato y se re-verifica sobre el golden en F3.
- **Idempotencia por hash en la landing zone.** Si `XREF.source_hash` coincide, la fila queda
  `UNCHANGED` en staging y no atraviesa las etapas 3 a 7 (caso G: 287 de 288 sin reproceso).
- **Auditoría por trigger en las 22 tablas con party.** El contexto viaja en la sesión
  (`app.actor`, `app.batch_id`, `app.source_system_sk`, `app.audit_action`); `PARTY_AUDIT_LOG`
  guarda fila antes y después, actor, fuente, lote y, en F3/F5, `merge_sk` y `arco_request_id`.
- **Códigos sin homologar son reprocesables.** El hallazgo `VALIDITY` guarda la fila y la
  columna que quedaron en `0 = UNKNOWN`; `rehomologate` los resuelve cuando aparece el mapeo,
  cierra el hallazgo (`resolved_at`) y audita `REHOMOLOGATE` (caso P).
- **1NF sobre fuentes multivaluadas.** `RLTYP`, `TELEFONOS`, `RELACIONES`, `ZZ_CONTRATOS`,
  `ZZ_SERVICIOS` y `ZZ_PREF` se abren en filas; el DQ rechaza los servicios transaccionales
  (regla dura §3.18) y las relaciones con tipos de party no permitidos (caso O), y genera la
  inversa cuando el tipo la declara.
- **Documento obligatorio salvo en el portal.** `WEB_PORTAL` admite usuarios sin documento
  (caso B) con hallazgo `COMPLETENESS` de advertencia; en las demás fuentes es bloqueante.
- **Estructuras fuente sintéticas.** Los CSV replican campos nativos (KNA1, LFA1, BUT000,
  OData de SF_EC); los campos `ZZ_*` de CRM y SD son campos Z ilustrativos que deben confirmarse
  con cada UES (SPEC §7.1).

## Convenciones (reglas duras de la especificación, §3)

- Identificadores de esquema, código y API en inglés; documentación, UI y mensajes en español.
- SK `BIGINT GENERATED ALWAYS AS IDENTITY`; todo `*_cd` es FK al RDM salvo las excepciones de §3.5.
- RDM precede al MDM; estandarización y homologación son etapas separadas.
- Toda escritura en `mdm.*` audita en `PARTY_AUDIT_LOG` (Ley 1581/2012 art. 17; ISO/IEC 27001:2022 A.8.15).
- Commits por fase: `feat(fase-N): ...`.
