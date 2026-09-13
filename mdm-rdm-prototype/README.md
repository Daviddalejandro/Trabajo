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
| F2 | Staging + `mdm` (29 tablas), generador sintético, etapas 1–5 | pendiente |
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

## Convenciones (reglas duras de la especificación, §3)

- Identificadores de esquema, código y API en inglés; documentación, UI y mensajes en español.
- SK `BIGINT GENERATED ALWAYS AS IDENTITY`; todo `*_cd` es FK al RDM salvo las excepciones de §3.5.
- RDM precede al MDM; estandarización y homologación son etapas separadas.
- Toda escritura en `mdm.*` audita en `PARTY_AUDIT_LOG` (Ley 1581/2012 art. 17; ISO/IEC 27001:2022 A.8.15).
- Commits por fase: `feat(fase-N): ...`.
