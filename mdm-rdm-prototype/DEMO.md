# DEMO — Guion de demostración (se completa por fase)

El guion final recorre los 21 casos plantados de la especificación (§13, A–U) sobre
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

### Consola RDM (`#/rdm-consola`): las cinco capas desde la interfaz

Para mostrar cómo un usuario de Gobierno de Datos construye el RDM sin tocar la base: siete estaciones en el orden
del ciclo (dominios → catálogos → campos personalizados → listas de referencia → sistemas fuente → integraciones y
homologación → ciclo de vida y auditoría), cada una con su explicación, lo que existe y el formulario de alta.

1. **Recorrido guiado** (tarjeta «mostrar» → «Ejecutar el recorrido»): ocho pasos contra la API con datos sintéticos.
   Crea el dominio `EXPERIENCIA`, el catálogo `CAT_CANAL_PREFERIDO` (fuente oficial «Política de servicio al afiliado»),
   tres campos personalizados (`horario` texto, `costo_contacto` número, `requiere_consentimiento` sí/no obligatorio),
   cuatro valores con atributos (y muestra cómo el diccionario **rechaza** un quinto con `costo_contacto = gratis` y sin
   el obligatorio), registra el sistema fuente `APP_MOVIL` (owner y steward), declara la integración
   `APP_MOVIL.canal_pref → CAT_CANAL_PREFERIDO`, homologa `wa/mail/sms/call`, prueba `wa → WHATSAPP`, **depreca `SMS`**,
   publica `SMS_RCS` y re-apunta `sms → SMS_RCS` (la homologación anterior queda cerrada en el histórico) y termina en la
   auditoría. Repetirlo no duplica nada: lo que ya existe se reporta como «ya existía».
2. Estación **4 · Listas de referencia** con `CAT_CANAL_PREFERIDO` e «incluir deprecados»: los campos personalizados
   aparecen como columnas, `SMS` deprecado y `SMS_RCS` activo; «atributos» corrige un atributo sin tocar código ni nombre.
3. Estación **7 · Ciclo de vida**: historial de `APP_MOVIL / canal_pref / CAT_CANAL_PREFERIDO / sms` → dos versiones
   (`SMS_RCS` vigente, `SMS` cerrada); auditoría filtrable por capa con el antes y el después de cada cambio.
4. Los contadores de las estaciones (dominios, catálogos, campos, valores activos +deprecados, sistemas,
   integraciones · homologaciones, entradas de auditoría) se actualizan con cada alta.
5. **Navegación con contexto** (para mostrar el flujo de un usuario real): en **2 · Catálogos** cada fila ofrece
   «campos · valores · homologar →»; lo que se elige queda en la barra **«Trabajando sobre: Dominio › Catálogo ›
   Sistema fuente»** y en la URL (`#/rdm-consola/valores?catalogo=CAT_CANAL_PREFERIDO`), así que «atrás» y los enlaces
   compartidos vuelven al mismo punto. Cada estación termina con el **siguiente paso** ya contextualizado
   («Siguiente: Homologar CAT_CANAL_PREFERIDO con una fuente →»). En **4 · Listas de referencia**, «homologar este
   catálogo →» abre **6 · Homologación** filtrada por el catálogo (solo sus integraciones y mapeos, formularios
   prefijados). Si la fuente no existe, el selector de sistema ofrece **«＋ registrar una fuente nueva…»**: lleva a
   **5 · Sistemas fuente** con el aviso de desvío («está registrando la fuente para homologar CAT_…»), y al registrarla
   vuelve solo a Homologación con la fuente ya seleccionada y el catálogo intacto. Desde un mapeo, «historial» abre
   **7 · Ciclo de vida** con las versiones ya cargadas.

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
3. **Caso B:** usuario del portal re-registrado sin documento y con correo nuevo → `PROBABLE` por el grupo
   G3 (demográfica + celular confirmado; con el mismo correo sería G4 y fusionaría solo). El detalle muestra
   evidencia ≈ 93 % sobre cobertura 70 % y el documento como **sin dato** (no como contradicción).
   `POST /matches/{sk}/decision` sin justificación → 422; con `X-Role: STEWARD` y justificación → merge `STEWARD`.
4. **Caso C:** homónimos con fecha de nacimiento distinta → `POSSIBLE` (evidencia 55 sobre cobertura 100,
   ningún grupo satisfecho), sin merge; `score_detail` muestra el documento como **contradice** y la fecha
   como **parcial**.
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
7. **Caso U · vitrina 360** (`#/party` → `Mariana Lucía Restrepo Vanegas`): una sola persona con las ocho
   capas pobladas — cinco fuentes, cuatro roles declarados por la fuente (EMPLOYEE, AFFILIATE, VENDOR,
   DIGITAL_USER) con sub-rol y UES, servicios en CREDITO, SALUD y SUBSIDIO, los tres tipos de segmento y
   las relaciones persona↔organización (`EMPLOYEE_OF`, `LEGAL_REP_OF`, `SHAREHOLDER_OF`) y persona↔persona
   (`SPOUSE_OF`, `PARENT_OF`/`CHILD_OF`, `BENEFICIARY_OF`) con su inversa. El mismo caso deja un par
   `PROBABLE` en `#/stewardship` (registro del portal sin documento y con correo nuevo → grupo G3): la
   tarjeta **Evidencia A** muestra esos roles, segmentos, servicios y relaciones, y la **base de la decisión**
   explica por qué no fusionó solo (G4 aplica pero el correo no coincide).
8. **Política de matching** (`#/matching`): cambiar G3 a *Fusiona solo* → **Simular** muestra que B y U
   pasarían a `AUTO_MERGE` (K sigue `PROBABLE`: solo satisface G2); actuando como `jefatura.gd`, **Publicar**
   crea la versión 2 y **Recalcular pendientes** fusiona esos pares (merge `AUTO`, reversible, con
   `decided_by = engine.v1.p2`); volver a publicar la política inicial deja la v3 activa con el historial completo.
9. `make test-e2e` reproduce 2–6 con Playwright (6 pruebas).

## Fase 5 · Cumplimiento embebido

`make demo` reconstruye todo, sincroniza el RNE, radica la consulta ARCO del caso Q e imprime la tabla de
los 21 casos (todos OK). Luego, con `make api` y la UI:

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

## Vitrina · casos S1–S10 y cargas masivas/transaccionales

`make demo` termina cargando la vitrina en modo **DELTA** (también `make showcase` sola, sobre la base actual, idempotente): diez
casos sintéticos que el escenario A–U no cubre, verificados uno a uno; imprime el `party_sk` y el `match_sk` para ir directo. Con ello
la Consola de Stewardship arranca con una **variedad de zona gris**: B, K y U del escenario más S1, S2, S3, S6, S8 y S10. Los casos
responden a preguntas concretas: «¿qué pasa si *todos* los campos traen un error de digitación?» (S6, S7), «¿y si solo llegan
algunos campos?» (S8), «¿fusiona con el mismo documento aunque nombre y fecha no cuadren?» (S9), «¿y dos empresas homónimas?» (S10).

| Caso | Dónde verlo | Qué muestra |
|---|---|---|
| **S1** cédula con un dígito transpuesto (`956555954` vs `956559554`), mismo correo y celular | Consola de Stewardship, par PROBABLE | Evidencia 82: el documento aparece como **parcial · posible error de digitación**, el grupo G4 está satisfecho pero el veto de digitación lo baja a revisión (`group:G4+veto_review:document`); el steward decide |
| **S2** portal sin documento; nombre con una letra cambiada, fecha con día y mes intercambiados, correo con un carácter de más | Consola de Stewardship, par PROBABLE | Evidencia 90 sobre cobertura 70 por la **vía de umbrales**: ningún grupo se satisface con parciales; la fecha dice «día y mes intercambiados» y el correo «posible error de digitación» |
| **S3** homónimo: mismos nombres y apellidos, otra cédula, nacido un año después | Consola de Stewardship, par POSSIBLE | Evidencia 57; el documento **contradice** (veto) y la fecha es parcial: nunca fusiona solo |
| **S4** la misma persona con CC (SF_EC), pasaporte (CRM) y TI antigua (portal) | Vista 360 del `party_sk` impreso, capa 3 | Fusionó sola por G4 (correo y celular confirmados); el golden conserva los **tres identificadores** con su fuente y solo la CC marcada golden |
| **S5** organización con el mismo NIT y razón social mal digitada en MM | Vista 360 del `party_sk` impreso | Fusión automática por O1 (NIT + razón social por tokens) |
| **S6** todos los campos con un solo error de digitación: cédula (dígito transpuesto), nombre y apellidos (una vocal), fecha (día y mes intercambiados), correo (un carácter), celular (dígito transpuesto) | Consola de Stewardship, filtro **Posible** | Se compara porque el apellido conserva el Soundex; evidencia **59**: documento, fecha, correo y celular «parcial · digitación», apellidos «parcial · parecido», el nombre lo absorbe Jaro-Winkler (coincide). Ningún grupo se satisface → POSSIBLE por umbral: con todo ligeramente mal, el motor no se atreve a «probable» y menos a fusionar; lo decide el steward |
| **S7** lo mismo que S6 pero la letra cambiada del primer apellido altera el Soundex (García → Varcía) | Modelo y cargas → explorador de buckets con el `party_sk` impreso | No comparte documento, correo, celular ni Soundex: **no cae en ningún bucket común y nunca se compara**. Es el límite del bloqueo exacto; el explorador lo muestra (0 vecinos en cada clave) |
| **S8** cobertura parcial: el portal solo trae nombres, apellidos y correo (sin documento, fecha ni celular) | Consola de Stewardship, filtro **Posible** | Evidencia 100 sobre **cobertura 52**: todo lo comparable coincide, pero falta más de la mitad del peso. Por debajo de la cobertura mínima (60) la política decide sobre **puntos brutos** (52 de 100, `threshold:raw_points`) → POSSIBLE; la base de la decisión lo dice y las filas `document`, `birth_date` y `phone` aparecen «sin dato» |
| **S9** el grupo G1 manda: mismo documento y primer apellido, nombre de pila distinto (Carlos / Andrés) y fecha cinco años aparte | Vista 360 del `party_sk` impreso, capa 7 (merges) | Fusionó sola por **G1** (documento + primer apellido) con evidencia 64: el documento verificado pesa más que el nombre y la fecha. Caso para discutir con las UES si G1 debe exigir además la fecha (se cambia en `#/matching` sin tocar código) |
| **S10** organizaciones homónimas: misma razón social y municipio, NIT distinto (SD vs MM) | Consola de Stewardship, par PROBABLE (organización) | Evidencia 45 por **O2** (razón social + municipio), con el NIT en la lista de vetos de la base de la decisión (`group:O2`, vetado por `nit`): nunca fusiona sola; el steward confirma si es la misma empresa (NIT mal cargado) o dos distintas |

En **Modelo y cargas → Cargas y buckets** se ven los cinco lotes DELTA de la vitrina con sus etapas (extraídos, sin cambio por hash,
cuarentena, XREF, cargados, buckets, comparados, auto, a revisión). El simulador de **carga transaccional** envía un
registro nativo por `POST /pipeline/{fuente}/record` y muestra al instante el party creado o actualizado por XREF, los
buckets en los que cayó y la decisión; enviar el mismo ID externo con cambios = actualización por XREF, sin cambios =
`unchanged_hash` (idempotencia). El explorador de buckets responde, para cualquier `party_sk`, con quién se compararía
un registro igual (documento, correo, celular, Soundex del apellido, NIT, tokens de la razón social).

Para explicar los buckets a una audiencia no técnica, la tarjeta arranca con **«¿Cómo funcionan los buckets? Piense en un
archivador con cajones»**: cinco pasos (llega un registro → se calculan sus claves → cada clave abre un cajón → solo se compara
con los vecinos → cada par se puntúa y la política decide) sobre cuatro escenarios (datos limpios, S1 cédula transpuesta, S6 todo
mal digitado con el apellido que conserva el sonido, S7 el apellido cambia de sonido y el registro no se compara con nadie). Al
explorar un `party_sk` aparece un quinto escenario con sus cajones reales y cuántos parties de la base nunca se miran.
