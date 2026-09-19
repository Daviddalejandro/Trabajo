# MDM/RDM in-house · Colsubsidio · Dominio Party — Prototipo funcional

Prototipo demostrable del Master Data Management (MDM) y Reference Data Management
(RDM) del dominio Party, construido por fases según
[`SPEC_PROTOTIPO_MDM_RDM_PARTY.md`](../SPEC_PROTOTIPO_MDM_RDM_PARTY.md) (v2.1).
Opera **exclusivamente con datos sintéticos**.

## Estado por fase

| Fase | Contenido | Estado |
|---|---|---|
| F0 | Scaffolding: db + api + ui, Alembic, Makefile, healthchecks, PostgreSQL local sin Docker | ✅ tests en verde |
| F1 | RDM: 43 catálogos (263 valores), 6 sistemas fuente, 24 homologaciones, 6 vistas, trigger de inmutabilidad, auditoría por trigger, endpoints RDM | ✅ 25 tests en verde |
| F2 | Staging (5 RAW + `LOAD_BATCH`) + `mdm` (29 tablas, triggers de auditoría y de unicidad golden), generador sintético (1.592 registros, 22 casos plantados), pipeline de 7 etapas con carga de candidatos, `rehomologate`, API de parties y stats | ✅ 42 tests en verde |
| F3 | Matching (blocking + scoring con estado por atributo + política v2 afinable: grupos de suficiencia, evidencia normalizada, vetos), merge automático con snapshot, survivorship por atributo, cola de stewardship con tareas por owner, unmerge, match-preview | ✅ 56 tests en verde |
| F4 | UI: Consola de Stewardship (cola con evidencia lado a lado, tareas por owner, historial de merges con snapshot y unmerge), Admin RDM (valores, homologaciones, probador, rehomologar con conteo previo), Vista 360 (8 capas), tablero; endpoints de apoyo; e2e con Playwright | ✅ 65 tests backend + 6 e2e en verde |
| Política v2 | Decisión de matching afinable en caliente: estado por atributo, evidencia sobre lo comparable, grupos de suficiencia, vetos; `mdm.match_policy` versionada, `party_match.decision_basis`, módulo **Política de matching** (`#/matching`) con simular / publicar / recalcular; guarda de unicidad golden (§3.16) antes de toda fusión AUTO | ✅ 12 tests (`test_f6_policy.py`) · total backend 131 + 7 e2e en verde |
| F5 | Cumplimiento embebido: elegibilidad por contacto y finalidad (12 precedencias), consentimientos multi-tipo, ARCO con SLA en días hábiles, RNE, audiencias auditadas, purga simulada, feed de cambios, módulo Cumplimiento en la UI, `make demo` (21 casos verificados) y `make export-drive` | ✅ 79 tests backend + 7 e2e en verde |

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
│   ├── app/synth          generador sintético (§13) y conjunto de validación (validation.py)
│   ├── cli.py             comandos operativos (nombres de los DAGs)
│   └── tests/             pytest por fase
├── frontend/src/          pages/ (Dashboard, Stewardship, AdminRdm, Vista360), components/ui (React + Vite + Tailwind)
├── frontend/e2e/          Playwright: casos B, K, L, Admin RDM y Vista 360 desde la UI
└── scripts/e2e.sh         rebuild → API :8001 + UI :5174 → playwright
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

## Matching, survivorship y stewardship (Fase 3)

```bash
python backend/cli.py match                      # blocking → scoring → umbrales → merge/promoción → survivorship
curl "localhost:8000/api/v1/matches?status=PENDING"            # cola de stewardship (PROBABLE / POSSIBLE)
curl "localhost:8000/api/v1/matches/17"                        # score_detail atributo por atributo
curl -X POST "localhost:8000/api/v1/matches/17/decision" -H "X-Actor: steward.mdm" -H "X-Role: STEWARD" \
     -d '{"decision":"MERGE","justification":"Documento confirmado con la UES"}'
curl "localhost:8000/api/v1/review-tasks?assignee=steward.crm"  # tareas por owner de fuente (§8.5)
curl -X POST "localhost:8000/api/v1/parties/545/unmerge" -d '{"merge_sk":3,"reason":"Homónimos"}'
curl -X POST "localhost:8000/api/v1/parties/match-preview" -d '{"party_type":"PERSON","id_type":"CC","id_number":"..."}'
```

| Elemento | Implementación |
|---|---|
| Blocking | `DOC_HASH`, `EMAIL_HASH`, `PHONE_HASH` (solo OWNER + CONFIRMED_BY_TITULAR), `SURNAME_SOUNDEX` (soundex tolerante al español: LL/Y, B/V, C/S/Z, H muda); organizaciones: `NIT_HASH`, `LEGAL_NAME_TOKENS` (sin S.A.S./LTDA/de Colombia). Los buckets se persisten en `PARTY_BUCKET`/`BUCKET_CANDIDATE`. |
| Scoring | `MATCH_RULE` v1: PERSON 30/20/15/15/10/5/3/2 (documento, primer apellido, nombre, fecha de nacimiento, email, teléfono, municipio, género); ORGANIZATION 50/25/10/10/5. Cada par guarda `score_detail` (atributo, valores, algoritmo, similitud, puntos, nota). |
| Política v2 (SPEC §8.4 bis) | Cada atributo con estado `AGREE` / `PARTIAL` / `DISAGREE` / `MISSING`; **evidencia** = puntos sobre el peso comparable y **cobertura** = peso comparable sobre el total; **grupos de suficiencia** (G1 documental → AUTO; G2 demográfica → PROBABLE; G3 = G2 + un contacto confirmado → PROBABLE; G4 = G2 + correo y teléfono confirmados → AUTO); umbrales ≥ 85 / 70 / 50 sobre la evidencia (cobertura mínima 60 %, piso de 50 puntos brutos, nunca AUTO sin grupo); veto por documento/NIT contradictorio (`REVIEW`: baja a revisión; `NO_MATCH`: son distintos); un documento a un solo dígito transpuesto o sustituido es `PARTIAL` "posible error de digitación" (+12) y sigue vetado salvo que la política lo levante (`veto_typo`). Tolerancia a digitación en todos los atributos (`reason` en cada fila): fecha con día/mes intercambiados (+10) o a un dígito (+8), correo (+3) y celular (+2) a un carácter, nombres a un carácter o JW ≥ 0,85 (mitad del peso); los grupos exigen coincidencia plena, así que un error de digitación nunca fusiona solo por grupo. Versionada en `mdm.match_policy`, afinable en `#/matching` (simular sin persistir, publicar como versión nueva —solo Jefatura—, recalcular la cola). |
| Merge | `PARTY_MERGE_HISTORY.pre_merge_snapshot` con las capas 2–5 y 8 de ambos parties; reapunte fila a fila con savepoint (las que chocan por unicidad se quedan en el absorbido, nunca se borran); absorbido `MERGED`, sobreviviente `GOLDEN`; auditoría con `merge_sk`. |
| Survivorship | `SOURCE_PRIORITY` SF_EC > SAP_CRM > SAP_ECC_SD > SAP_ECC_MM > WEB_PORTAL para nombres y documento; `MOST_RECENT` para email, teléfono principal y fallecido; `MOST_COMPLETE` de respaldo. Cada atributo escribe `PARTY_SURVIVORSHIP` (valor, fuente, estrategia). |
| Stewardship | `GET /matches` cola; decisión con justificación obligatoria (422 sin ella) y cabecera `X-Role` (`STEWARD` / `JEFATURA`); par con más de una fuente → `MATCH_REVIEW_TASK` por fuente asignada a su `data_steward`; regla de cierre §8.5 (consenso → `OWNER_CONSENSUS`, desacuerdo → escalado a Jefatura). |
| Unmerge | Restaura fila a fila desde el snapshot, marca el par `NO_MATCH` (decisión vinculante para el motor), re-survivorship en ambos; si el absorbido comparte documento con un golden queda `CANDIDATE` con hallazgo `UNIQUENESS` (regla dura §3.16). |
| Prevención en origen | `POST /parties/match-preview` compara contra los goldens sin persistir nada (§8.6). |

Decisiones de implementación de la Fase 3:

- **El matching corre dentro de cada lote.** Tras la etapa 7, los parties nuevos del lote se comparan
  contra goldens y candidatos (regla dura §3.11: XREF primero, matching solo para registros nuevos).
  `cli.py match` / `POST /matching/run` reprocesan los `CANDIDATE` que quedaron pendientes.
- **Unicidad de documento golden.** Un candidato con el documento de un golden nunca se promueve
  automáticamente: se abre un par `PROBABLE` forzado y un hallazgo `UNIQUENESS` (regla dura §3.16).
- **Decisiones humanas vinculantes.** Un par resuelto `NO_MATCH` (steward o unmerge) no vuelve a
  proponerse aunque el score lo supere; el motor lo omite en corridas posteriores.
- **Actor de auditoría.** En merges `AUTO` el actor es el del pipeline y `decided_by = engine.v1.pN` (pesos v1, política N; la justificación registra evidencia, cobertura y el grupo o veto que decidió);
  en merges humanos el actor es el steward u owner que decidió (Ley 1581/2012 art. 17; ISO/IEC 27001:2022 A.8.15).
- **Corrida sobre los sintéticos** (5 fuentes, 1.592 registros): 691 merges automáticos (613 por G1 documental,
  59 por O1 NIT, 19 por G4 sin documento comparable), 900 goldens, 3 pares `PROBABLE` (casos B, K y U, cada uno por
  un grupo distinto) y 1 `POSSIBLE` (caso C); ninguna persona se compara con una organización.

### Opción C · Google Colab (sin instalar nada)

Cuaderno `colab/MDM_Prototipo_Colab.ipynb` (copia en Drive `MDM_RDM_Prototipo/08_Colab/`): instala PostgreSQL 16 en una
máquina temporal de Google, carga los datos y sirve la consola desde la API en un solo puerto (`UI_DIST_DIR=colab/ui`),
con enlace para abrirla en el navegador. Detalle en [`colab/README.md`](colab/README.md).

## Interfaz (Fase 4)

```bash
make rebuild                                   # base desde cero con B y K pendientes en la consola
make api                                       # FastAPI :8000
cd frontend && npm install && npm run dev      # UI en :5173 (VITE_API_BASE opcional)
make test-e2e                                  # Playwright: rebuild → API :8001 + UI :5174 → 7 pruebas
```

| Módulo | Ruta | Qué hace |
|---|---|---|
| Tablero | `#/` | Goldens, candidatos, fusionados, pares en cola; última carga por fuente; matching por decisión; hallazgos DQ; tareas abiertas por owner. |
| Política de matching | `#/matching` | Editor de la política v2 (grupos de suficiencia con sus atributos y decisión, umbrales, cobertura mínima, piso de puntos, vetos y su modo), **simulación** sobre todos los pares registrados (transiciones, pares que cambian, acuerdo con las decisiones humanas), **publicación como versión nueva** (solo Jefatura, con nota) y **recálculo de la cola pendiente**; historial de versiones con carga al editor. |
| Consola de Stewardship | `#/stewardship` | **Cola** (PROBABLE/POSSIBLE): evidencia sobre cobertura, desglose por atributo con estado (coincide / parcial / contradice / sin dato), barra de puntos y valores A/B resaltando diferencias, **base de la decisión** (grupo satisfecho, veto o umbral, con cada grupo de la política evaluado sobre el par), fuentes y owners, roles/segmentos/servicios/relaciones/contactos de cada party; acciones **Fusionar** / **No es la misma persona** / **Escalar** con justificación obligatoria (botones deshabilitados sin ella). **Tareas por owner**: las `MATCH_REVIEW_TASK` del actor con `due_at`, decisión y resultado de la regla de cierre. **Historial de merges**: `pre_merge_snapshot` (filas por tabla y JSON), auditoría por `merge_sk` y **unmerge** con razón. |
| Admin RDM | `#/rdm` | Dominio → catálogo → valores con jerarquía (DIVIPOLA, segmentos, servicios), alta de valor (la SK la asigna la base), deprecación con confirmación, homologaciones por sistema fuente con alta, probador sistema/campo/valor → canónico y **Rehomologar** con conteo previo de UNKNOWN corregibles. |
| Vista 360 | `#/party` y `#/party/:sk` | Búsqueda y perfil por las 8 capas en orden con la leyenda de colores: XREF y linaje, core con fuente ganadora por campo, identificadores golden, roles por UES, vínculos de servicio por UES, segmentos por tipo, relaciones con el otro extremo, contactos agrupados (propios, cobranza no confirmados, compartidos/acudiente, referencias) con finalidades por contacto vs. canal, hallazgos, retención, auditoría, survivorship, merges, consentimientos y ARCO.. Cabecera con **resumen ejecutivo**: ¿se puede contactar por finalidad y por qué no? (Ley 2300/2023 arts. 3 y 5), servicios activos por UES, hallazgos DQ abiertos, pares de matching pendientes (enlazados a la consola), fuentes, merges y autorizaciones, marcas de menor de edad y fallecido. Además: nombres por tipo con vigencia, verificación de identificadores, rol bajo el cual se sostiene cada vínculo, miembros del grupo con enlace, validez técnica del medio de contacto, geocodificación de la dirección, línea de tiempo de auditoría filtrable y quién otorgó cada autorización |

Sin SSO en el prototipo (SPEC §2): el selector **Actúa como** fija las cabeceras `X-Actor` y `X-Role`
(`STEWARD` o `JEFATURA`); los owners de fuente son los `data_steward` registrados en `SOURCE_SYSTEM`.

Decisiones de implementación de la Fase 4:

- **Herramienta de evidencia, no flujo de aprobación** (regla dura §3.12): la consola muestra el
  `score_detail` completo y las capas de ambos parties; toda decisión exige justificación y queda en
  `PARTY_AUDIT_LOG` como `REVIEW_DECISION` con el actor.
- **Regla de cierre entre owners** (§8.5) verificada desde la UI: el steward pide la fusión de un par con
  dos fuentes → una tarea por owner; el primer owner deja el par "faltan otros owners (1/2)"; el
  segundo cierra con `OWNER_CONSENSUS`. Un `NO_MATCH` de cualquier owner resuelve el par.
- **Endpoints de apoyo** añadidos a §11: `GET /merges`, `GET /merges/{sk}` (snapshot, conteos y
  auditoría), `GET /rdm/rehomologate/preview`, `GET /parties/{sk}/relationships` y `/services`.
- **Pruebas e2e reproducibles**: `scripts/e2e.sh` reconstruye la base (`cli.py rebuild --yes`) para que
  B y K estén pendientes, levanta API y UI en puertos propios y corre Playwright (Chromium).

## Cumplimiento embebido y demo (Fase 5)

```bash
make demo                                        # rebuild → rne-sync → caso Q → tabla de los 21 casos (OK/REVISAR)
python backend/cli.py rne-sync                   # marca rne_excluded (solo COMMERCIAL) y recalcula elegibilidad
python backend/cli.py purge --dry-run            # candidatos a purga; audita PURGE_SIMULATED; nunca borra
python backend/cli.py eligibility-recompute      # recalcula la caché de las 12 precedencias
make export-drive                                # docs/drive/00..07 con xlsx, csv y md por carpeta de Drive
curl "localhost:8000/api/v1/parties/545/contactability?purpose=COMMERCIAL"
curl "localhost:8000/api/v1/audiences?purpose=COMMERCIAL&channel=EMAIL&role=AFFILIATE" -H "X-Actor: campanas"
curl -X POST localhost:8000/api/v1/parties/545/arco -d '{"arco_type":"CANCELLATION","channel_received":"OFICINA"}'
curl "localhost:8000/api/v1/arco/requests?sla=OVERDUE"
curl "localhost:8000/api/v1/changes?since=2026-09-13T00:00:00Z&entity=PARTY_CONSENT"
```

| Capacidad | Implementación |
|---|---|
| Elegibilidad (§10.3) | `app/compliance/eligibility.py`: 12 precedencias en orden; el primer criterio que falla fija `reason_cd`; se persiste en `PARTY_CONTACT_ELIGIBILITY_CACHE` y se recalcula tras ingesta, merge, unmerge, promoción a golden, consentimiento, preferencia, confirmación, RNE y ARCO. Lectura en vivo en `GET /parties/{sk}/contactability`. |
| Consentimientos y preferencias | `POST /parties/{sk}/consents` (fila nueva, cierra la anterior), `PUT /parties/{sk}/preferences` (canal), `PUT /parties/{sk}/contacts/{pcs}/purposes` (contacto, una fila por finalidad), `POST .../confirmation` (gestión). Escrituras internas con sistema fuente `MDM_CONSOLE`. |
| ARCO (Ley 1581/2012 arts. 14 y 15; Decreto 1377/2013 art. 9) | `POST /parties/{sk}/arco`: `due_at` en días hábiles (festivos Ley 51/1983) según EAV `sla_business_days`; ACCESS audita `ARCO_READ`; CANCELLATION revoca los consentimientos vigentes, marca retención `PURGE_ELIGIBLE` y recalcula elegibilidad; todo con `arco_request_id`. `GET /arco/requests?sla=OVERDUE`; `PATCH /arco/requests/{sk}`. |
| RNE (Ley 2300/2023 art. 5) | `cli.py rne-sync` / `POST /rne/sync`: marca y retira `rne_excluded` por hash; solo afecta COMMERCIAL; audita `RNE_SYNC`. |
| Audiencias (§10.4) | `GET /audiences?purpose&channel&role&segment&service&enrollment_status`: solo GOLDEN + ACTIVE con contacto elegible; audita `AUDIENCE_RUN` con actor, filtros y conteo. |
| Retención y purga (§10.5) | `GET /retention/purge-candidates` y `cli.py purge --dry-run`: `purge_after` vencido, sin LEGAL_HOLD, sin vínculo activo; audita `PURGE_SIMULATED`; nunca borra. |
| Feed de cambios | `GET /changes?since&entity&limit&cursor` derivado de `PARTY_AUDIT_LOG` con `golden_version`. |
| UI | Módulo **Cumplimiento** (`#/compliance`): audiencias, ARCO y SLA, RNE, retención y purga, feed. En la Vista 360, cada contacto permite confirmar por titular y habilitar o denegar finalidades. |

Decisiones de implementación de la Fase 5:

- **Negación explícita = revocatoria** para la elegibilidad: un consentimiento `DENIED` o `REVOKED` produce `CONSENT_REVOKED`; la ausencia de fila, `PENDING` o `EXPIRED` producen `NO_CONSENT`.
- **`INVALID_CONTACT`** se añadió a `CAT_ELIGIBILITY_REASON` para los vínculos `WRONG_PERSON` / `INVALID`, que nunca son elegibles (precedencia 7).
- **Frecuencia** (precedencia 11): sin historial de envíos en el prototipo, solo `NEVER` se considera excedida.
- **Caso H** trae ahora un crédito activo en SD para que la cobranza sea legítima (precedencia 8) mientras el RNE bloquea solo lo comercial; **caso S** recibe su crédito en `data/synth/ecc_sd_delta.csv` (corrida delta) y pasa de `NO_ACTIVE_SERVICE` a `ELIGIBLE` sin tocar BENEFITS.
- **`make demo`** verifica los 21 casos sobre la base reconstruida y falla si alguno no cumple; F, L, M y N se ejecutan desde la API o la consola según el guion.
- **Caso U · vitrina 360**: una persona sintética con las ocho capas pobladas (cinco fuentes, cuatro roles, los tres tipos de segmento, servicios en tres UES y relaciones persona↔organización y persona↔persona). Se busca en la Vista 360 como `Mariana Lucía Restrepo Vanegas` y deja un par `PROBABLE` en la Consola de Stewardship (registro del portal sin documento y con correo nuevo: grupo G3); detalle en `docs/GUIA_PRUEBAS_MANUALES.md` §3 bis.

## Conjunto de validación (SAP ECC + sistema de crédito)

```bash
make test-validation                          # 37 pruebas: genera, ingiere y verifica los casos V1–V28
python backend/cli.py validation-generate     # backend/data/validation/*.csv + manifest_validacion.json
make validation-load                          # deja ECC + crédito en la consola (zona gris: V2 por G3, V18 por veto del documento, V3 por G2)
```

Dos fuentes distintas de las del escenario demo: un extracto SAP ECC (KNA1, adaptador `ecc_sd`) y un
sistema de crédito / core de cartera (`CREDITO_CORE`, adaptador nuevo con obligaciones, teléfonos de
gestión, calificación, autorizaciones y codeudor). Recorre RDM, pipeline, matching, survivorship,
stewardship, cumplimiento, feed, Vista 360, match-preview y export. Detalle y desenlaces esperados en
[`docs/validation/README.md`](docs/validation/README.md).

Para probar a mano desde la interfaz (arranque, elección del conjunto de datos, decisión de la zona gris
y construcción de casos propios): [`docs/GUIA_PRUEBAS_MANUALES.md`](docs/GUIA_PRUEBAS_MANUALES.md).
Estado del proyecto, decisiones, pendientes y cómo retomar el trabajo en una sesión nueva de Claude Code:
[`docs/ESTADO_Y_CONTINUIDAD.md`](docs/ESTADO_Y_CONTINUIDAD.md) y `CLAUDE.md` en la raíz del repositorio.

## Convenciones (reglas duras de la especificación, §3)

- Identificadores de esquema, código y API en inglés; documentación, UI y mensajes en español.
- SK `BIGINT GENERATED ALWAYS AS IDENTITY`; todo `*_cd` es FK al RDM salvo las excepciones de §3.5.
- RDM precede al MDM; estandarización y homologación son etapas separadas.
- Toda escritura en `mdm.*` audita en `PARTY_AUDIT_LOG` (Ley 1581/2012 art. 17; ISO/IEC 27001:2022 A.8.15).
- Commits por fase: `feat(fase-N): ...`.
