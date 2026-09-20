# ESPECIFICACIÓN DE PROTOTIPO FUNCIONAL — MDM/RDM in-house · Dominio Party
**Colsubsidio · Jefatura de Gobierno de Datos (ARC)** · Versión 2.0 · 2026-09-13
**Documento de handoff para Claude Code** — autor del modelo: David Alejandro Ballesteros Díaz

> **Versión 2.0 consolidada.** Integra y depura las versiones 1.0 a 1.5 (historial en
> el Anexo B). Cifras vigentes: **29 tablas núcleo** en 8 capas + **1 tabla de bitácora
> de carga** en `staging`; **43 catálogos RDM** creados y poblados (universo de 44);
> **21 casos demo** (A–U); **6 fases** de construcción. Cubre las 10 necesidades
> funcionales del autor y 12 capacidades MDM adicionales (matriz de cobertura en §15).
>
> **Pendiente de reconciliación con el diccionario maestro de la Jefatura (41 tablas):**
> las cuatro tablas nuevas (`PARTY_SEGMENT`, `CONTACT_POINT`, `MATCH_REVIEW_TASK`,
> `PARTY_SERVICE_ENROLLMENT`) y los campos agregados en §5 deben incorporarse al
> diccionario y al diagrama `mdm_party_diagram.mermaid`. Hasta entonces, esta
> especificación es la fuente de verdad del prototipo.

---

## 0. INSTRUCCIONES PARA CLAUDE CODE (leer primero)

Eres el implementador de un **prototipo funcional demostrable** del MDM/RDM in-house
de Colsubsidio, dominio Party. El diseño lógico YA ESTÁ RESUELTO y está descrito en
este documento. Tu trabajo es materializarlo, no rediseñarlo.

**Reglas de trabajo:**

1. Trabaja por **fases en orden estricto** (§14). No avances a la siguiente fase sin
   cumplir los criterios de aceptación de la actual y sin sus tests en verde.
2. **No inventes tablas, catálogos ni campos** fuera del inventario de §5 y §6. El
   modelo completo tiene 41 tablas (en reconciliación, ver registro de cambios); el
   prototipo implementa el subconjunto núcleo listado. Lo que no está listado queda
   como migración futura, no lo crees.
3. Respeta las **reglas duras de §3 sin excepción**. Si una decisión de implementación
   entra en conflicto con una regla dura, gana la regla dura.
4. Idiomas: **identificadores de esquema, código y APIs en inglés** (`PARTY`,
   `party_sk`, `id_type_cd`); **documentación, UI y mensajes al usuario en español**.
   Todo endpoint de lista pagina con `limit` y `cursor`; ningún endpoint devuelve
   colecciones sin acotar.
5. Cada fase termina con: tests `pytest` en verde, un commit con mensaje
   `feat(fase-N): ...`, y actualización del `README.md`.
6. El prototipo opera **exclusivamente con datos sintéticos** (Faker `es_CO`, seed
   fija). Ningún dato personal real, nunca. Los ejemplos narrativos del modelo
   (María, `party_sk 18452`; La Espiga S.A.S.) son ficticios e ilustrativos.
7. Entregables finales: repositorio funcionando con `docker compose up`, suite de
   tests, `README.md` (arranque), `DEMO.md` (guion de demostración paso a paso) y
   `make demo` que deja el sistema poblado con los casos de §13.
8. El diccionario maestro de la Jefatura (41 tablas) y el diagrama
   `mdm_party_diagram.mermaid` se adjuntan al repositorio en `docs/reference/` como
   **solo lectura**; sirven para resolver dudas de alcance, nunca para ampliar el
   inventario del prototipo.

---

## 1. CONTEXTO Y OBJETIVO

Colsubsidio (caja de compensación familiar colombiana) construye in-house su
plataforma de **Master Data Management (MDM)** y **Reference Data Management (RDM)**
para el dominio **Party**: Afiliados, Empleados, Empresas Afiliadoras, Proveedores,
Clientes y Usuarios Digitales. El objetivo del programa es un **golden record**
(registro maestro único) por persona/organización, consolidado desde 4 fuentes SAP,
con cumplimiento embebido de la regulación colombiana de protección de datos.

**Objetivo del prototipo:** demostrar end-to-end, con datos sintéticos, que el diseño
funciona: RDM operativo → ingesta multi-fuente → estandarización y homologación →
matching y survivorship → golden record → consola de stewardship (incluido el
workflow entre owners de fuente) → contactabilidad, audiencias y derechos del
titular, con trazabilidad completa y reversibilidad de merges.

**Anclaje normativo del diseño** (jerarquía: norma colombiana primero, framework
internacional como complemento técnico):

- Ley 1581/2012 arts. 4, 5, 6, 7, 8, 14, 15 y 17 (principios, datos sensibles,
  derechos de los niños, autorización, consultas, reclamos, deberes del responsable).
- Decreto 1377/2013 arts. 9 y 12 (revocatoria y supresión; tratamiento de datos de
  menores de edad).
- Ley 1266/2008 art. 6 (autorización para dato financiero — Habeas Data financiero).
- Ley 23/1981 art. 34 y Res. 1995/1999 art. 15 (reserva y conservación de la historia
  clínica: el MDM solo administra la autorización, nunca el contenido clínico).
- Ley 2300/2023 art. 3 (canales, horarios y frecuencia), art. 5 (Registro de Números
  Excluidos, RNE) y art. 9 (vigilancia SIC); Resolución CRC 7356/2024 (armonización
  del RNE).
- DAMA-DMBOK2 Cap. 5 (Data Modeling & Design) y Cap. 10 (Reference & Master Data).
- ISO/IEC 27001:2022 A.8.15 (Logging) — bitácoras de carga y auditoría.
- NIST AI RMF 1.0 (funciones GOVERN/MAP/MEASURE) e ISO/IEC 42001:2023 cl. 6.1 — el
  matching es un sistema algorítmico de decisión sobre datos personales: cada merge
  queda trazado con su evidencia y con supervisión humana identificable.

---

## 2. ALCANCE DEL PROTOTIPO

**Dentro del alcance:**
- Esquema `rdm` completo (5 capas) + semilla de catálogos (§6) + vistas de consumo.
- Esquema `mdm` con las **29 tablas núcleo** de las 8 capas (§5.2).
- Esquema `staging` con 5 tablas RAW (una por fuente) + `LOAD_BATCH` (bitácora de
  carga, §5.3).
- Pipeline batch de 7 etapas por fuente, ejecutable por CLI (§7) + comandos
  operativos (`rne-sync`, `rehomologate`, `purge --dry-run`).
- Motor de matching con pesos y umbrales exactos (§8) + survivorship (§9) +
  workflow de revisión entre owners de fuente (§8.5) + `match-preview` (§8.6).
- API REST (FastAPI) con el contrato de §11.
- UI web: Consola de Stewardship (con tareas por owner) + Admin RDM + Vista 360 (§12).
- Generador de datos sintéticos con casos de demo plantados (§13).
- Auditoría y cumplimiento embebido (§10).

**Fuera del alcance (producción, NO implementar):**
- Conectores reales a SAP. Los extractores nativos quedan documentados como
  **contrato de entrada** (§7.1): los CSV sintéticos replican las estructuras fuente.
- Apache Airflow, Kafka, Redis, Great Expectations, Splink (el prototipo usa
  equivalentes ligeros; producción los usa — dejar interfaces limpias).
- SAP HANA Cloud como capa física (el DDL debe mantenerse portable/ANSI-friendly).
- SSO/seguridad enterprise, alta disponibilidad, volúmenes > 10M registros.
- Consumo real por SAP CDP: el prototipo expone la API de audiencias (§11); la
  integración con el CDP es producción.
- **Datos transaccionales de los servicios** (saldos, cuotas, consumos, estadías,
  compras): pertenecen a los sistemas transaccionales y al dominio Acuerdo/Producto.
  El MDM de Party conserva únicamente la **cabecera del vínculo** (qué servicio,
  desde cuándo, en qué estado, con qué referencia en la fuente).

---

## 3. REGLAS DURAS (decisiones de arquitectura vigentes — NO negociables)

1. **RDM precede al MDM.** La ingesta MDM no puede validar ni homologar sin catálogos
   RDM poblados. El orden de construcción y de ejecución del pipeline lo refleja.
2. **Claves sustitutas (SK):** `BIGINT GENERATED ALWAYS AS IDENTITY` por tabla,
   secuencia 1..∞, **inmutables y no reutilizables**.
3. **Miembros técnicos reservados** en cada catálogo para joins del MDM:
   `0 = UNKNOWN`, `-1 = NOT_APPLICABLE` (sembrar siempre).
4. **Las integraciones nunca referencian SKs.** Toda resolución externa/entre
   ambientes se hace por `CATALOG_CODE + VALUE_CODE` (los SKs difieren entre
   dev/QA/prod). **Todo mapeo de `SOURCE_VALUE_MAPPING` se registra bajo el
   `source_system_cd` exacto de la fuente que lo emite; no existen códigos de sistema
   agregados** (no existe `SAP_ECC`; existen `SAP_ECC_HCM`, `SAP_ECC_SD`, `SAP_ECC_MM`).
5. **Regla de los `_cd`:** todo campo `*_cd` es **FK del RDM**, con exactamente dos
   mecanismos de excepción, documentados aquí (nunca implícitos):
   **(a)** los campos que referencian un sistema fuente (`source_system_cd`,
   `winning_source_cd`) apuntan a `rdm.SOURCE_SYSTEM` (capa Integration), no a un
   catálogo de `REFERENCE_VALUE`: el sistema fuente es metadato de integración con
   atributos operativos propios (owner, steward, actividad), distinción consistente
   con DAMA-DMBOK2 Cap. 10.
   **(b)** El modelo completo gobierna 6 campos como `ENUM/CHECK` con justificación
   documentada; el prototipo instancia ese mismo mecanismo en dos columnas de estado
   interno de máquina, **sin sufijo `_cd`**: `staging.raw_status`,
   `mdm.PARTY_MATCH.match_status` y `mdm.PARTY_DATA_RETENTION.purge_status`.
   Ninguna otra excepción está permitida.
6. **1NF estricta:** ningún campo multivaluado (nunca `"102/103"` en una celda; una
   fila por valor). Aplica a segmentos, roles, consentimientos y contactos: una fila
   por tipo/valor.
7. **Inmutabilidad del valor canónico:** publicado un código (p. ej. `M = Masculino`)
   no cambia nunca. Los valores se deprecan (`is_active = false`, `valid_to`), jamás
   se editan ni se reciclan.
8. **Estandarización ≠ homologación:** limpieza (TRIM, normalización Unicode, parsing
   de nombres y direcciones, teléfonos E.164) es una etapa separada del mapeo de
   códigos fuente→canónico (`SOURCE_VALUE_MAPPING`). No mezclarlas en el código.
9. **Geografía DIVIPOLA (DANE):** la ciudad es un **tipo de localidad** (CABECERA),
   no un nivel jerárquico adicional (jerarquía: país → departamento → municipio →
   localidad). Correcciones documentadas: código DANE `11 = Bogotá D.C.` (NO es
   Cundinamarca, que es `25`). Los códigos de divisiones administrativas
   internacionales se namespacean por país para evitar colisión con códigos DANE.
10. **Vistas RDM en dos familias:** (a) **motor genérico** — una vista por función
    para todo el RDM, nombradas `VW_RDM_<FUNCIÓN>`; el dominio NO va en el nombre,
    viaja como columna `DOMAIN_CODE`; (b) **vistas tipadas** `VW_RDM_<CATALOG_CODE>`
    como capa delgada sobre el motor, SOLO cuando hay que pivotar atributos EAV, dar
    un contrato estable o restringir exposición. Un catálogo nuevo NO implica una
    vista nueva, solo una fila en `CATALOG`. La vista cruzada (fuente A → fuente B)
    se construye sobre la vista fuente→canónico (auto-join por `VALUE_SK`), no sobre
    las tablas base.
11. **XREF como caché de matching:** si el `external_id + source_system_cd` ya existe
    en `XREF_PARTY_SOURCE`, el registro NO pasa por matching completo (esto evita
    ~80% del costo en cargas recurrentes). Implementarlo y probarlo (§14, F3).
12. **La consola de stewardship no es un workflow de aprobación simple.** Decidir si
    dos registros similares son la misma persona requiere juicio experto: la UI debe
    presentar evidencia comparativa (score desglosado por atributo, fuentes, fechas)
    y exigir justificación en cada decisión. Cuando la decisión afecta a más de una
    fuente, el juicio se distribuye entre los **owners de las fuentes afectadas**
    (§8.5); el MDM nunca decide por ellos.
13. **Trazabilidad total:** todo insert/update/merge/unmerge y todo acceso ARCO
    escribe en `PARTY_AUDIT_LOG` (Ley 1581/2012 art. 17; ISO/IEC 27001:2022 A.8.15).
    Los merges/unmerges quedan reversibles y auditables en `PARTY_MERGE_HISTORY`,
    con snapshot previo al merge (§5.2, capa 7).
14. **Linaje por fila:** toda tabla de hechos de las capas 2 a 5 (`PARTY_ROLE`,
    `PARTY_SEGMENT`, `PARTY_IDENTIFIER`, `PARTY_NAME`, `PARTY_RELATIONSHIP`,
    `PARTY_SERVICE_ENROLLMENT`, `PARTY_CONTACT_POINT`, `PARTY_ADDRESS`) lleva `source_system_cd` y
    `captured_at`. La pregunta "¿de qué fuente viene este dato?" se responde con la
    fila, sin reconstrucción desde auditoría.
15. **El punto de contacto es una entidad propia, no un atributo del party.**
    `CONTACT_POINT` tiene identidad (SK) e invariantes del valor (canal, valor
    normalizado, hash, exclusión RNE); `PARTY_CONTACT_POINT` es la relación N:M con el
    party y su rol de uso (titular, compartido, acudiente). El mismo celular puede
    estar vinculado a varios miembros de un grupo familiar sin duplicar el valor.
16. **Unicidad de documento entre goldens:** dos parties en estado `GOLDEN` no pueden
    compartir (`id_type_cd`, `id_number`). Se implementa como índice único parcial y,
    si la carga lo viola, el registro entra a matching forzado con hallazgo
    `UNIQUENESS` en `PARTY_DQ_ISSUE` (nunca se descarta silenciosamente).
17. **Nunca matching cruzado de tipo:** una PERSON nunca se compara con una
    ORGANIZATION. El blocking parte por `party_type_cd`.
18. **Solo los servicios de relación persistente entran al MDM.** Un servicio con
    `service_kind = TRANSACTIONAL` (hotel, Piscilago, supermercado, droguería) existe
    en el RDM como referencia corporativa, pero **nunca** genera un
    `PARTY_SERVICE_ENROLLMENT`: la carga lo rechaza con hallazgo `VALIDITY`. La
    transacción puntual no define la relación del titular con Colsubsidio; el
    vínculo sostenido sí (DAMA-DMBOK2 Cap. 10, separación Party / Agreement).

---

## 4. ARQUITECTURA Y STACK DEL PROTOTIPO

**Stack (subconjunto del stack objetivo de producción):**

| Componente | Prototipo | Producción (referencia, no implementar) |
|---|---|---|
| Base de datos | PostgreSQL 16 (Docker; alternativa sin Docker: `make db-local` levanta un clúster con `initdb`/`pg_ctl` en `.pgdata/`, mismo DDL) | PostgreSQL / evaluación SAP HANA Cloud |
| Backend / API | Python 3.11+, FastAPI, SQLAlchemy 2, Alembic | Igual |
| Matching | RapidFuzz (Jaro-Winkler), Jellyfish (Soundex/Metaphone) | Splink (Fellegi-Sunter, EM, DuckDB/Spark) para >10M |
| Estandarización | `phonenumbers` (E.164), `nameparser`; direcciones con normalizador propio simple | + libpostal |
| Calidad de datos | Validaciones propias categorizadas por `CAT_DQ_CATEGORY` | Great Expectations |
| Orquestación | CLI `typer` (comandos que replican los nombres lógicos de los DAGs) | Apache Airflow |
| Eventos/caché | — (fuera de alcance) | Kafka, Redis |
| Frontend | React + Vite + Tailwind (SPA servida por contenedor propio) | Igual |
| Datos sintéticos | Faker `es_CO`, seed fija | N/A |

**Estructura de repositorio:**

```
mdm-rdm-prototype/
├── docker-compose.yml            # db + api + ui
├── Makefile                      # make up | db-local / migrate / seed / demo / test / export-drive
├── README.md                     # arranque y operación
├── DEMO.md                       # guion de demostración
├── docs/reference/               # diccionario maestro y .mermaid (solo lectura)
├── docs/drive/                   # entregables exportados a Google Drive por fase (§17)
├── backend/
│   ├── alembic/                  # migraciones (una por fase)
│   ├── app/
│   │   ├── api/                  # routers FastAPI (§11)
│   │   ├── core/                 # config, db, audit middleware
│   │   ├── models/               # SQLAlchemy: schemas rdm / mdm / staging
│   │   ├── pipeline/             # 7 etapas (§7) — una función por etapa
│   │   ├── matching/             # blocking, scoring, umbrales, preview (§8)
│   │   ├── stewardship/          # decisiones, review tasks, merge/unmerge (§8.5)
│   │   ├── survivorship/         # estrategias (§9)
│   │   ├── compliance/           # elegibilidad, audiencias, ARCO, retención (§10)
│   │   └── synth/                # generador de datos sintéticos (§13)
│   ├── cli.py                    # typer: rdm-seed, ingest, match, rne-sync, rehomologate, purge, demo
│   └── tests/                    # pytest por fase
└── frontend/
    └── src/                      # Stewardship, Admin RDM, Vista 360
```

**Convención de esquemas PostgreSQL:** `rdm`, `mdm`, `staging` (tres esquemas en una
misma base `mdm_prototype`).

---

## 5. MODELO DE DATOS

### 5.1 Esquema `rdm` — Reference Data Management (5 capas)

El RDM es genérico (modelo catálogo/valor con extensión EAV), no una tabla por
catálogo.

**Capa Master Data:**

| Tabla | Propósito | Campos clave |
|---|---|---|
| `rdm.DOMAIN` | Dominios de referencia (DEMOGRAPHICS, GEOGRAPHY, GOVERNANCE, CONTACT, MDM_OPS, BUSINESS) | `domain_sk`, `domain_code`, `domain_name` |
| `rdm.CATALOG` | Los catálogos (§6) | `catalog_sk`, `domain_sk FK`, `catalog_code`, `catalog_name`, `official_source` (DANE, DIAN, Interno...), `is_hierarchical` |
| `rdm.REFERENCE_VALUE` | Valores canónicos | `value_sk`, `catalog_sk FK`, `value_code`, `value_name`, `parent_value_sk FK` (jerarquías: DIVIPOLA, segmentos, servicios), `is_active`, `valid_from`, `valid_to` |
| `rdm.REFERENCE_FIELD_VALUE` | Atributos extendidos EAV por valor (dígito de verificación, tipo de localidad, tipos de party permitidos en una relación, consentimiento requerido por finalidad) | `field_value_sk`, `value_sk FK`, `field_code`, `field_value` |

**Capa Integration:**

| Tabla | Propósito | Campos clave |
|---|---|---|
| `rdm.SOURCE_SYSTEM` | Sistemas fuente registrados | `source_system_sk`, `source_system_cd` (`SAP_ECC_HCM`, `SAP_ECC_SD`, `SAP_ECC_MM`, `SAP_CRM`, `SF_EC`, `WEB_PORTAL`), `name`, `is_prototype_active` (`SAP_ECC_HCM` en `false`), **`data_owner`** (rol de negocio dueño de la fuente, p. ej. "Gerencia de Gestión Humana"), **`data_steward`** (identificador del steward que recibe tareas de revisión, §8.5) |
| `rdm.CATALOG_SOURCE_INTEGRATION` | Qué campo de qué fuente alimenta qué catálogo | `integration_sk`, `catalog_sk FK`, `source_system_sk FK`, `source_field` (`SEXKZ`, `GESCHL`, `RLTYP`...) |
| `rdm.SOURCE_VALUE_MAPPING` | **La tabla más crítica**: mapeo código fuente → canónico | `mapping_sk`, `integration_sk FK`, `source_value`, `value_sk FK` (canónico), `valid_from`, `valid_to` |

**Capa Audit:** `rdm.RDM_AUDIT_LOG` (`audit_sk`, `entity`, `entity_sk`, `action`,
`old_value`, `new_value`, `actor`, `occurred_at`) — trazabilidad de cambios de
referencia conforme Ley 1581/2012 art. 17 y DAMA-DMBOK2 Cap. 10.

**Vistas de consumo (regla dura §3.10):**

- `VW_RDM_LOOKUP` — motor genérico canónico: `DOMAIN_CODE, CATALOG_CODE, VALUE_SK,
  VALUE_CODE, VALUE_NAME, PARENT_VALUE_CODE, IS_ACTIVE`.
- `VW_RDM_SOURCE_TO_CANONICAL` — fuente→canónico: `SOURCE_SYSTEM_CD, SOURCE_FIELD,
  SOURCE_VALUE, DOMAIN_CODE, CATALOG_CODE, VALUE_SK, VALUE_CODE, VALUE_NAME`.
- `VW_RDM_CROSSWALK` — fuente A→fuente B: **auto-join de
  `VW_RDM_SOURCE_TO_CANONICAL` por `VALUE_SK`** (no sobre tablas base).
- Tipadas (solo estas tres en el prototipo, porque pivotan EAV):
  `VW_RDM_CAT_GEO_DIVIPOLA` (tipo de localidad y jerarquía),
  `VW_RDM_CAT_ID_TYPE` (reglas de validación del documento) y
  `VW_RDM_CAT_RELATIONSHIP_TYPE` (tipos de party permitidos origen/destino e inverso).

### 5.2 Esquema `mdm` — Dominio Party: 8 capas, subconjunto núcleo de 29 tablas

El modelo lógico completo son **41 tablas en 8 capas** (referencia: diagrama ER
`mdm_party_diagram.mermaid` y diccionario maestro de la Jefatura, derivados del
modelo IBM InfoSphere; en reconciliación con esta versión). El prototipo implementa
las 29 siguientes (Core 6 · Identity 2 · Roles y Relaciones 4 · Contactability 5 ·
Governance 4 · Golden Record 6 · Consents 2); **no crear ninguna otra**.

Convención de linaje (regla dura §3.14): donde la tabla dice **[linaje]** lleva
`source_system_cd FK` y `captured_at`.

**Capa 1 · Sources** → materializada en el esquema `staging` (§5.3).

**Capa 2 · Core (azul):**

| Tabla | Propósito y campos clave |
|---|---|
| `PARTY` | Registro maestro (el golden record vive aquí). `party_sk`, `party_type_cd FK` (PERSON/ORGANIZATION), `golden_status_cd FK` (ciclo MDM `CANDIDATE → GOLDEN → MERGED`, §6), **`party_status_cd FK`** (ciclo de negocio `ACTIVE / INACTIVE / DECEASED`, independiente del ciclo MDM), **`golden_version`** (entero, +1 en cada cambio del golden), **`completeness_score`** (0–100, % de campos de identidad y contacto poblados; recalculado en survivorship), `created_at`, `updated_at` |
| `PARTY_PERSON` | Extensión persona natural. `party_sk PK/FK`, `first_name`, `middle_name`, `first_surname`, `second_surname`, `birth_date`, `gender_cd FK`, `full_name_normalized`, **`death_date`** (NULL si vive; al poblarse, `party_status_cd = DECEASED`). La condición de **menor de edad** se deriva de `birth_date` (< 18 años a la fecha de consulta) y nunca se almacena. |
| `PARTY_ORG` | Extensión persona jurídica. `party_sk PK/FK`, `legal_name`, `trade_name`, `legal_name_normalized`, `ciiu_cd FK`, `org_type_cd FK` |
| `PARTY_ROLE` **[linaje]** | Roles del party en el negocio. `party_role_sk`, `party_sk FK`, `role_cd FK` (AFFILIATE/EMPLOYEE/VENDOR/CUSTOMER/DIGITAL_USER/AFFILIATING_COMPANY), `sub_role_cd FK`, `business_unit_cd FK` (UES en la que se ejerce el rol), `valid_from`, `valid_to`. Un party tiene N filas: una por combinación rol + UES + vigencia. El detalle de **qué servicio persistente** sostiene ese rol vive en `PARTY_SERVICE_ENROLLMENT` (capa 4). **El rol lo declara el sistema fuente, nunca el adaptador**: SAP ECC SD lo homologa desde `BPROL` (multivalor como BUT100: afiliado, beneficiario, proveedor, empresa afiliadora), SAP CRM desde `RLTYP`, SF_EC desde su división y `CREDITO_CORE` aporta `CUSTOMER` (cliente de crédito) con la UES CREDITO. Cuando la fuente no envía UES se toma `default_business_unit` del valor en `CAT_PARTY_ROLE` (AFFILIATE y AFFILIATING_COMPANY → SUBSIDIO); en los demás roles queda `NOT_APPLICABLE` |
| **`PARTY_SEGMENT`** **[linaje]** | Segmentación multi-tipo. `party_segment_sk`, `party_sk FK`, `segment_type_cd FK` (nivel 1 de `CAT_SEGMENT_TYPE`: AFFILIATION, FINANCIAL_RISK, COMMERCIAL...), `segment_cd FK` (nivel 2 del mismo catálogo; debe ser hijo de `segment_type_cd`, validado en carga), `valid_from`, `valid_to`. **UNIQUE(`party_sk`, `segment_type_cd`, `valid_from`)**: un party tiene a lo sumo un segmento vigente por tipo, y tantos tipos como necesite (afiliación = A, riesgo financiero = MEDIUM, comercial = PREMIUM) |
| `XREF_PARTY_SOURCE` | Crosswalk fuente↔maestro y caché de matching. `xref_sk`, `party_sk FK`, `source_system_cd FK`, `external_id` (**el identificador original de la fuente, sin transformación**: PERNR, KUNNR, LIFNR, PARTNER, user_id), `source_hash`, `first_seen_at`, `last_seen_at`. UNIQUE(`source_system_cd`,`external_id`). Un party puede tener varias filas por fuente si la fuente le asignó más de un ID (p. ej. cliente re-creado) |

**Capa 3 · Identity (amarillo):**

| Tabla | Propósito y campos clave |
|---|---|
| `PARTY_IDENTIFIER` **[linaje]** | Documentos de identidad. `identifier_sk`, `party_sk FK`, `id_type_cd FK` (CC/CE/TI/NIT/PAS/PPT), `id_number`, `verification_source_cd FK` (RNEC_API/DIAN_API/MANUAL/MIGR_COLOM/NOT_VERIFIED), `is_verified`, `verified_at`. Para NIT: validar dígito de verificación. **Índice único parcial** sobre (`id_type_cd`, `id_number`) restringido a parties con `golden_status_cd = GOLDEN` (regla dura §3.16) |
| `PARTY_NAME` **[linaje]** | Nombres por tipo. `party_name_sk`, `party_sk FK`, `name_type_cd FK` (LEGAL/SOCIAL/ALIAS/PREVIOUS/TRADE), `name_value`, `valid_from`, `valid_to` |

**Capa 4 · Roles & Relationships (verde):**

| Tabla | Propósito y campos clave |
|---|---|
| `PARTY_RELATIONSHIP` **[linaje]** | Relaciones direccionales party↔party. `relationship_sk`, `from_party_sk FK`, `to_party_sk FK`, `relationship_type_cd FK` (con dirección), `valid_from`, `valid_to`. Como `PARTY` es supertipo, cubre **persona↔persona, organización↔persona y organización↔organización**. La carga valida los tipos de party permitidos por relación contra los atributos EAV `from_party_type` / `to_party_type` del catálogo (p. ej. `SPOUSE_OF` solo PERSON→PERSON; `LEGAL_REP_OF` solo PERSON→ORGANIZATION; `SUBSIDIARY_OF` solo ORGANIZATION→ORGANIZATION) y persiste automáticamente la relación inversa cuando `inverse_code` existe (`PARENT_OF` ↔ `CHILD_OF`) |
| `PARTY_GROUP` | **Decisión vigente: grupo genérico** (reemplaza tablas específicas de grupo familiar). `group_sk`, `group_type_cd FK` (FAMILY / CORPORATE_GROUP), `group_name`, `anchor_party_sk FK` |
| `PARTY_GROUP_MEMBER` | Miembros del grupo. `group_member_sk`, `group_sk FK`, `party_sk FK`, `member_role_cd FK`, `valid_from`, `valid_to` |
| **`PARTY_SERVICE_ENROLLMENT`** **[linaje]** | **Vínculo de servicio persistente** del party con una UES (regla dura §3.18). `enrollment_sk`, `party_sk FK`, `party_role_sk FK` (rol bajo el cual se sostiene el vínculo, p. ej. CUSTOMER en CREDITO), `business_unit_cd FK`, `service_cd FK` (`CAT_SERVICE`, solo valores con `service_kind = PERSISTENT`; la carga valida que el servicio pertenezca a la UES), `enrollment_status_cd FK` (`CAT_ENROLLMENT_STATUS`: ACTIVE / SUSPENDED / CLOSED), `enrolled_at`, `closed_at`, `source_reference` (número de crédito, contrato o afiliación **tal como lo conoce la fuente**; nunca saldos ni contenido clínico), `valid_from`, `valid_to`. UNIQUE(`party_sk`, `service_cd`, `source_reference`). Un party puede sostener varios vínculos del mismo servicio (dos créditos vigentes) y varios servicios a la vez. Es la cabecera del Acuerdo; el detalle transaccional queda fuera del MDM |

**Capa 5 · Contactability (púrpura):**

| Tabla | Propósito y campos clave |
|---|---|
| **`CONTACT_POINT`** | **Identidad del punto de contacto, independiente del party** (regla dura §3.15). `contact_point_sk`, `channel_cd FK` (EMAIL/PHONE/SMS/WHATSAPP/PHYSICAL_MAIL), `contact_value` (E.164 para teléfono, lowercase para email, dirección normalizada para PHYSICAL_MAIL), **`address_sk FK NULL`** (solo cuando `channel_cd = PHYSICAL_MAIL`, apunta a `PARTY_ADDRESS`), `contact_hash`, **`rne_excluded`** bool, **`rne_synced_at`** (Ley 2300/2023 art. 5: la exclusión del RNE es del **número**, no de la persona), `is_verified` (validez **técnica** del medio: formato, existencia, entregabilidad; la confianza de la relación con la persona vive en el vínculo), `verified_at`, `created_at`. UNIQUE(`channel_cd`, `contact_hash`). Cualquier extensión futura (rebotes, verificación, historial de uso) cuelga de `contact_point_sk` |
| `PARTY_CONTACT_POINT` **[linaje]** | **Relación N:M** party ↔ punto de contacto. `party_contact_sk`, `party_sk FK`, `contact_point_sk FK`, `usage_role_cd FK` (`CAT_CONTACT_USAGE_ROLE`: OWNER = titular del medio; SHARED = lo usa pero no es el titular; GUARDIAN = acudiente que recibe comunicaciones por un menor; REFERENCE = medio de un tercero dado como referencia), **`confirmation_status_cd FK`** (`CAT_CONTACT_CONFIRMATION`: grado de confianza de que el medio pertenece o llega a esta persona; se actualiza desde la gestión y se audita), **`origin_cd FK`** (reutiliza `CAT_PREF_ORIGIN`: TITULAR, LEGAL_REP, INTERNAL_POLICY, COLLECTIONS_MANAGEMENT, THIRD_PARTY_REFERENCE), `is_primary`, `valid_from`, `valid_to`. UNIQUE(`party_sk`, `contact_point_sk`, `valid_from`). El celular del hijo puede estar vinculado al hijo como OWNER y a la madre como GUARDIAN sin duplicar el número; un teléfono aportado por cobranza queda vinculado con `origin_cd = COLLECTIONS_MANAGEMENT` y `confirmation_status_cd = UNCONFIRMED` hasta que una gestión lo confirme. **Las finalidades para las que sirve cada vínculo no viven aquí**: se declaran como filas de `PARTY_CONTACT_PREF` con `party_contact_sk` (una por finalidad, §5.2 capa 5), de modo que un mismo email puede tener una o varias finalidades habilitadas y otras denegadas |
| `PARTY_ADDRESS` **[linaje]** | Direcciones con geografía DIVIPOLA. `address_sk`, `party_sk FK`, `address_line`, `country_cd FK`, `divipola_cd FK` (municipio), `locality_type` vía RDM, `geocoding_status_cd FK`, **`address_hash`** (línea normalizada + país + DIVIPOLA). **UNIQUE(`party_sk`, `address_hash`)**: la misma dirección aportada por varias fuentes es una sola fila del party (conserva el linaje de la primera fuente); **una sola `is_primary` por party** (índice único parcial). Igual que `CONTACT_POINT`, nunca se duplica por fuente |
| `PARTY_CONTACT_PREF` | Preferencias por finalidad, **a nivel de canal o de contacto concreto** (Ley 2300/2023 art. 3). `pref_sk`, `party_sk FK`, `channel_cd FK`, **`party_contact_sk FK NULL`** (NULL = la preferencia aplica a todo el canal; con valor = aplica solo a ese vínculo party↔contacto, y su `channel_cd` debe coincidir con el del contacto), `purpose_cd FK`, `allowed` bool, `frequency_cd FK`, `origin_cd FK` (`CAT_PREF_ORIGIN`), `declared_at`, `valid_from`, `valid_to`. **UNIQUE(`party_sk`, `channel_cd`, `party_contact_sk`, `purpose_cd`, `valid_from`)** (una fila por finalidad; 1NF). **Precedencia:** la fila de contacto prevalece sobre la de canal para la misma finalidad; si un contacto no tiene fila para una finalidad, hereda la del canal; si tampoco existe, se asume permitido salvo lo que dicten las precedencias de §10.3. Ejemplo: email `maria@…` con filas (BENEFITS, true), (COLLECTIONS, true), (COMMERCIAL, false) → sirve para dos finalidades y no para la tercera, aunque el canal EMAIL esté permitido para COMMERCIAL |
| `PARTY_CONTACT_ELIGIBILITY_CACHE` | Caché materializada de elegibilidad. Clave compuesta **`(party_contact_sk, purpose_cd)`** (el vínculo party↔contacto ya fija party, contacto, canal, rol de uso y confirmación), campos `party_sk` (desnormalizado para consultas de audiencia), `is_eligible`, `reason_cd FK`, `computed_at`. Se recalcula al cambiar consents, prefs, vínculos de contacto, `rne_excluded`, `party_status_cd`, `birth_date`, el estado de un vínculo de servicio, la confirmación de un vínculo de contacto o una preferencia de canal o de contacto |

**Capa 6 · Governance (naranja):**

| Tabla | Propósito y campos clave |
|---|---|
| `MATCH_RULE` | Reglas y pesos de matching versionados (los de §8 se siembran aquí). `rule_sk`, `entity_type_cd FK` (reutiliza `CAT_PARTY_TYPE`), `attribute`, `weight`, `algorithm`, **`params JSONB`** (umbral, puntaje parcial, tolerancia: p. ej. `{"jw_min":0.92,"partial":15}`; estructurado para que la consola muestre la regla aplicada sin texto libre), `version`, `is_active` |
| `PARTY_DQ_ISSUE` | Hallazgos de calidad de la etapa DQ. `dq_issue_sk`, `staging_ref`, `party_sk FK NULL`, `dq_category_cd FK`, `field`, `detail`, `severity_cd FK`, `detected_at`, **`resolved_at`** (se puebla cuando `rehomologate` o una carga posterior corrige el hallazgo) |
| `PARTY_AUDIT_LOG` | Bitácora central (Ley 1581/2012 art. 17). `audit_sk`, `party_sk FK NULL`, `entity`, `entity_sk`, `action_cd FK`, `old_value JSONB`, `new_value JSONB`, `actor`, `source_system_cd FK NULL`, `batch_id NULL`, `arco_request_id FK NULL` (trazabilidad ARCO, Ley 1581/2012 arts. 14–15), **`merge_sk FK NULL`** (agrupa todos los reapuntamientos de un merge/unmerge), `occurred_at` |
| `PARTY_DATA_RETENTION` | Política de retención aplicada por party/entidad. `retention_sk`, `party_sk FK`, `entity`, `retention_rule_cd FK`, `purge_after`, `legal_basis`, **`purge_status`** (`CHECK ('SCHEDULED','HOLD','PURGED')`, columna de estado de máquina, excepción §3.5(b)) |

*Nota de diseño abierta (del autor): la ubicación editorial de `PARTY_AUDIT_LOG` y
`PARTY_DATA_RETENTION` entre la capa 6 y la 8 está en revisión. Para el prototipo se
implementan en Governance con FKs desde Consents; no cambiar sin instrucción.*

**Capa 7 · Golden Record (rosa) — motor de matching, revisión y merge:**

| Tabla | Propósito y campos clave |
|---|---|
| `PARTY_BUCKET` | Bloques de comparación (blocking §8.1). `bucket_sk`, `blocking_key`, `blocking_strategy_cd FK`, `party_type_cd FK` (regla dura §3.17), `created_at` |
| `BUCKET_CANDIDATE` | Candidatos por bloque. `candidate_sk`, `bucket_sk FK`, `staging_ref` o `party_sk FK` |
| `PARTY_MATCH` | Resultado de cada comparación. `match_sk`, `party_a_sk FK`, `party_b_sk FK`, `total_score`, `score_detail JSONB` (desglose por atributo — evidencia para la consola), `decision_cd FK` (`CAT_MATCH_DECISION`), `match_status` con `CHECK ('PENDING','IN_REVIEW','RESOLVED')` (excepción §3.5(b)), `rule_version` (versión de `MATCH_RULE` usada), `matched_at` |
| **`MATCH_REVIEW_TASK`** | **Workflow de zona gris entre owners de fuente** (§8.5). `task_sk`, `match_sk FK`, `source_system_cd FK` (fuente afectada), `assignee` (tomado de `SOURCE_SYSTEM.data_steward` al crear la tarea), `task_status_cd FK` (reutiliza `CAT_REQUEST_STATUS`: RECEIVED / IN_PROGRESS / RESOLVED / REJECTED), `decision_cd FK` (`CAT_STEWARD_DECISION`: MERGE / NO_MATCH / ESCALATE), `justification` (obligatoria al decidir), `created_at`, `due_at`, `decided_at`, `decided_by` |
| `PARTY_MERGE_HISTORY` | Trazabilidad de merges. `merge_sk`, `surviving_party_sk FK`, `merged_party_sk FK`, `merge_type_cd FK`, `match_sk FK`, `justification`, `decided_by`, `merged_at`, **`pre_merge_snapshot JSONB`** (estado completo de ambos parties y de sus filas hijas de las capas 2–5 y 8 antes del merge; hace el unmerge determinista), campos de unmerge: `unmerged` bool, `unmerged_by`, `unmerged_at`, `unmerge_reason` |
| `PARTY_SURVIVORSHIP` | Regla ganadora por campo del golden. `survivorship_sk`, `party_sk FK`, `field_name`, `strategy_cd FK`, `winning_source_cd FK`, `winning_value`, `decided_at` |

**Capa 8 · Consents — Habeas Data (rojo):**

| Tabla | Propósito y campos clave |
|---|---|
| `PARTY_CONSENT` | Autorizaciones de tratamiento, **una fila por finalidad/tipo** (Ley 1581/2012 art. 8; Ley 1266/2008 art. 6; Decreto 1377/2013). `consent_sk`, `party_sk FK`, `consent_type_cd FK` (`CAT_CONSENT_TYPE`: DATA_PROCESSING / COMMERCIAL / FINANCIAL_HABEAS_DATA / CLINICAL_RECORDS / CREDIT_BUREAU), `consent_status_cd FK` (GRANTED/DENIED/REVOKED/EXPIRED/PENDING), `granted_at`, `revoked_at`, `expires_at`, `evidence_ref`, **`granted_by_party_sk FK NULL`** (representante legal cuando el titular es menor de edad, Decreto 1377/2013 art. 12), `source_system_cd FK`. Un party puede tener simultáneamente N autorizaciones vigentes de distinto tipo; un cambio de estado crea fila nueva y cierra la anterior (nunca se edita el histórico) |
| `DATA_SUBJECT_REQUEST` | Solicitudes ARCO (Ley 1581/2012 arts. 14–15; Decreto 1377/2013 art. 9). `request_sk` (= `arco_request_id`), `party_sk FK`, `arco_type_cd FK` (ACCESS/RECTIFICATION/CANCELLATION/OPPOSITION), `request_status_cd FK`, `requested_at`, **`due_at`** (consultas: 10 días hábiles, Ley 1581/2012 art. 14; reclamos: 15 días hábiles, art. 15; calculado al crear), `resolved_at`, `resolution_note`, `channel_received`. El estado de SLA (`ON_TIME` / `AT_RISK` / `OVERDUE`) se **deriva** en la API, nunca se almacena |

### 5.3 Esquema `staging` — Capa 1 · Sources

Una tabla RAW por fuente, misma estructura operativa:

`STG_SF_EC_RAW` (Empleados · SuccessFactors), `STG_ECC_SD_RAW` (Interlocutores comerciales · KNA1),
`STG_ECC_MM_RAW` (Proveedores · LFA1), `STG_CRM_BP_RAW` (Business Partner ·
BUT000/BUT020/ADRC), `STG_WEB_PORTAL_RAW` (Usuarios Digitales).

Campos comunes: `raw_sk`, `batch_id FK`, `external_id`, `payload JSONB` (registro fuente
completo), `source_hash`, `raw_status` (`PENDING` → `STANDARDIZED` → `HOMOLOGATED` →
`DQ_PASSED` / `DQ_QUARANTINE` → `LOADED`), `loaded_at`, `processed_at`.

**`staging.LOAD_BATCH` — bitácora de carga** (ISO/IEC 27001:2022 A.8.15; es la
evidencia operativa de cada ejecución del pipeline): `batch_id`, `source_system_cd FK`,
`mode` (`CHECK ('FULL','DELTA','RNE_SYNC','REHOMOLOGATE')`, estado de máquina,
excepción §3.5(b)), `started_at`, `finished_at`, `status` (`CHECK ('RUNNING','OK',
'FAILED')`), y contadores por etapa: `extracted`, `unchanged_hash`, `standardized`,
`homologated`, `unknown_codes`, `dq_passed`, `dq_quarantined`, `xref_hits`,
`matched`, `auto_merged`, `probable`, `loaded`, `actor`. `GET /stats` y el caso G
(caché XREF) se verifican leyendo esta tabla, no contando filas a mano.

### 5.4 DDL de referencia (patrones obligatorios)

```sql
-- Patrón de SK (regla dura §3.2)
party_sk BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY

-- Patrón de _cd (regla dura §3.5): FK al valor canónico del RDM
gender_cd BIGINT NOT NULL DEFAULT 0
    REFERENCES rdm.reference_value(value_sk)
-- 0 = UNKNOWN, -1 = NOT_APPLICABLE (miembros técnicos sembrados en cada catálogo,
-- insertados con OVERRIDING SYSTEM VALUE una sola vez en la migración semilla)

-- Linaje por fila (regla dura §3.14)
source_system_cd BIGINT NOT NULL REFERENCES rdm.source_system(source_system_sk),
captured_at      TIMESTAMPTZ NOT NULL DEFAULT now()

-- Unicidad de documento entre goldens (regla dura §3.16)
CREATE UNIQUE INDEX ux_identifier_golden
  ON mdm.party_identifier (id_type_cd, id_number)
  WHERE party_sk IN (SELECT party_sk FROM mdm.party WHERE golden_status_cd = <GOLDEN>);
-- (en PostgreSQL implementar con columna desnormalizada is_golden mantenida por
--  trigger, ya que un índice parcial no admite subconsulta)

-- Inmutabilidad del canónico (regla dura §3.7): trigger que rechaza UPDATE de
-- value_code/value_name en rdm.reference_value cuando is_active = true;
-- el cambio permitido es deprecar (is_active=false, valid_to=now()) y crear valor nuevo.
```

**Índices obligatorios (rendimiento del matching y de las audiencias):**
`pg_trgm` GIN sobre `PARTY_PERSON.full_name_normalized` y
`PARTY_ORG.legal_name_normalized`; B-tree sobre `PARTY_IDENTIFIER (id_type_cd,
id_number)`, `CONTACT_POINT (channel_cd, contact_hash)`, `XREF_PARTY_SOURCE
(source_system_cd, external_id)`, `PARTY_BUCKET (blocking_strategy_cd,
blocking_key)`, `PARTY_CONTACT_ELIGIBILITY_CACHE (purpose_cd, is_eligible,
party_sk)` y `PARTY_AUDIT_LOG (occurred_at)` (alimenta el feed de cambios, §11).

**Orden de migración (FKs cruzadas entre capas):** crear primero todas las tablas
y agregar al final de la migración, vía `ALTER TABLE`, las FKs que cruzan capas —
en particular `PARTY_AUDIT_LOG.arco_request_id → DATA_SUBJECT_REQUEST`
(Governance → Consents), `PARTY_AUDIT_LOG.merge_sk → PARTY_MERGE_HISTORY`,
`PARTY_MERGE_HISTORY.match_sk → PARTY_MATCH`, `MATCH_REVIEW_TASK.match_sk →
PARTY_MATCH`, `PARTY_CONSENT.granted_by_party_sk → PARTY` y
`PARTY_SERVICE_ENROLLMENT.party_role_sk → PARTY_ROLE`. Así el orden de creación
no depende de la ubicación editorial de las tablas.

---

## 6. CATÁLOGOS RDM — SEMILLA DEL PROTOTIPO

**Universo RDM: 44 catálogos** = 37 del diccionario maestro (22 base + 15
adicionales) + 7 incorporados por las versiones 1.2 a 1.4 (`CAT_SERVICE`,
`CAT_CONTACT_USAGE_ROLE`, `CAT_PARTY_STATUS`, `CAT_STEWARD_DECISION`,
`CAT_SERVICE_KIND`, `CAT_ENROLLMENT_STATUS`, `CAT_CONTACT_CONFIRMATION`), todos
gobernados en `rdm.CATALOG` con miembros técnicos, inmutabilidad y auditoría. El
prototipo **crea 43 y puebla 43**;
el restante queda reservado al diccionario maestro
de la Jefatura (no inventar su nombre). Fuentes oficiales colombianas donde aplica:
DANE/DIVIPOLA (geografía), DIAN (CIIU), MinSalud, Supersalud.

**Tabla A · Catálogos de negocio (21):**

| Catálogo | Dominio | Valores canónicos semilla |
|---|---|---|
| `CAT_GENDER` | DEMOGRAPHICS | `M` (Masculino), `F` (Femenino) — homologa `SEXKZ=1`/`GESCHL=1` |
| `CAT_ID_TYPE` | DEMOGRAPHICS | `CC`, `CE`, `TI`, `NIT`, `PAS`, `PPT` (EAV: regex de validación, `applies_to` PERSON/ORGANIZATION) |
| `CAT_NAME_TYPE` | DEMOGRAPHICS | `LEGAL`, `SOCIAL`, `ALIAS`, `PREVIOUS`, `TRADE` |
| `CAT_VERIFICATION_SOURCE` | GOVERNANCE | `RNEC_API`, `DIAN_API`, `MANUAL`, `MIGR_COLOM`, `NOT_VERIFIED` |
| `CAT_PARTY_ROLE` | BUSINESS | `AFFILIATE`, `EMPLOYEE`, `VENDOR`, `CUSTOMER`, `DIGITAL_USER`, `AFFILIATING_COMPANY` |
| `CAT_PARTY_SUB_ROLE` | BUSINESS | 12 sub-roles — sembrar 3 ilustrativos por rol principal (EAV `parent_role`) |
| `CAT_RELATIONSHIP_TYPE` | DEMOGRAPHICS | 10 tipos con dirección, **sembrar los 10** con EAV `from_party_type`, `to_party_type`, `inverse_code`: `SPOUSE_OF` (P→P, inverso sí mismo), `PARENT_OF` (P→P, inv. `CHILD_OF`), `CHILD_OF` (P→P), `GUARDIAN_OF` (P→P, acudiente de menor), `BENEFICIARY_OF` (P→P), `LEGAL_REP_OF` (P→O), `EMPLOYEE_OF` (P→O), `SHAREHOLDER_OF` (P/O→O), `SUBSIDIARY_OF` (O→O), `BRANCH_OF` (O→O) |
| `CAT_CONSENT_STATUS` | GOVERNANCE | `GRANTED`, `DENIED`, `REVOKED`, `EXPIRED`, `PENDING` |
| `CAT_CONSENT_TYPE` | GOVERNANCE | `DATA_PROCESSING` (Ley 1581/2012 art. 8), `COMMERCIAL` (finalidad comercial/publicitaria), `FINANCIAL_HABEAS_DATA` (Ley 1266/2008 art. 6), `CLINICAL_RECORDS` (dato sensible, Ley 1581/2012 art. 6; Ley 23/1981 art. 34), `CREDIT_BUREAU` (reporte a centrales, Ley 1266/2008) |
| `CAT_CONTACT_CHANNEL` | CONTACT | `EMAIL`, `PHONE`, `SMS`, `WHATSAPP`, `PHYSICAL_MAIL` |
| `CAT_CONTACT_FREQUENCY` | CONTACT | `ANY`, `WEEKLY`, `MONTHLY`, `NEVER` |
| `CAT_CONTACT_PURPOSE` | CONTACT | `COLLECTIONS`, `BENEFITS`, `COMMERCIAL` (Ley 2300/2023 art. 3). **EAV obligatorio `required_consent_type`**: COMMERCIAL → `COMMERCIAL`; BENEFITS → `DATA_PROCESSING`; COLLECTIONS → `DATA_PROCESSING`. **EAV `rne_applies`**: solo COMMERCIAL = true (Ley 2300/2023 art. 5) |
| `CAT_MERGE_TYPE` | MDM_OPS | `AUTO`, `STEWARD`, `OWNER_CONSENSUS`, `MANUAL_OVERRIDE` |
| `CAT_ARCO_REQUEST_TYPE` | GOVERNANCE | `ACCESS`, `RECTIFICATION`, `CANCELLATION`, `OPPOSITION` (EAV `sla_business_days`: ACCESS = 10, resto = 15) |
| `CAT_REQUEST_STATUS` | GOVERNANCE | `RECEIVED`, `IN_PROGRESS`, `RESOLVED`, `REJECTED` |
| `CAT_DQ_CATEGORY` | GOVERNANCE | `COMPLETENESS`, `VALIDITY`, `CONSISTENCY`, `UNIQUENESS`, `TIMELINESS` |
| `CAT_MDM_ENTITY` | MDM_OPS | Un valor por tabla mdm núcleo (29) |
| `CAT_GEOCODING_STATUS` | GEOGRAPHY | `PENDING`, `GEOCODED`, `FAILED`, `NOT_APPLICABLE` |
| `CAT_COUNTRY` | GEOGRAPHY | `COL` (Colombia), `VEN`, `USA`, `ESP` — homologa `LAND1=CO→COL` |
| `CAT_GEO_DIVIPOLA` | GEOGRAPHY | Jerárquico DANE. Semilla mínima obligatoria: `11` Bogotá D.C. → `11001` Bogotá D.C. (CABECERA); `05` Antioquia → `05001` Medellín; `25` Cundinamarca → `25286` Funza, `25754` Soacha; `76` Valle del Cauca → `76001` Cali. **Verificación de la regla §3.9: `11` NUNCA es Cundinamarca** |
| `CAT_SEGMENT_TYPE` | BUSINESS | **Jerárquico (`is_hierarchical = true`)**. Nivel 1 = tipo de segmento; nivel 2 = valor. Semilla: `AFFILIATION` → `A`, `B`, `C` (categorías de afiliado); `FINANCIAL_RISK` → `LOW`, `MEDIUM`, `HIGH`; `COMMERCIAL` → `BASIC`, `PREMIUM`. Un party puede tener un valor vigente por cada tipo |

**Tabla B · Catálogos operativos (22), FK obligatorias de las tablas núcleo desde la
Fase 2 — sembrar exactamente estos valores mínimos:**

| Catálogo | Dominio | Valores mínimos |
|---|---|---|
| `CAT_PARTY_TYPE` | MDM_OPS | `PERSON`, `ORGANIZATION` |
| `CAT_GOLDEN_STATUS` | MDM_OPS | `CANDIDATE`, `GOLDEN`, `MERGED` — todo party nace `CANDIDATE`, consolida a `GOLDEN` tras matching/survivorship, y pasa a `MERGED` al ser absorbido (nunca se borra) |
| `CAT_PARTY_STATUS` | BUSINESS | `ACTIVE`, `INACTIVE`, `DECEASED` (ciclo de negocio; `DECEASED` bloquea toda elegibilidad de contacto y se propaga desde cualquier fuente que informe fallecimiento) |
| `CAT_MATCH_DECISION` | MDM_OPS | `AUTO_MERGE`, `PROBABLE`, `POSSIBLE`, `NO_MATCH` |
| `CAT_STEWARD_DECISION` | MDM_OPS | `MERGE`, `NO_MATCH`, `ESCALATE` (decisión humana en consola y en tareas de revisión) |
| `CAT_SEVERITY` | GOVERNANCE | `BLOCKING`, `WARNING`, `INFO` |
| `CAT_SURVIVORSHIP_STRATEGY` | MDM_OPS | `SOURCE_PRIORITY`, `MOST_RECENT`, `MOST_COMPLETE`, `MOST_FREQUENT`, `MANUAL_OVERRIDE` |
| `CAT_AUDIT_ACTION` | GOVERNANCE | `INSERT`, `UPDATE`, `MERGE`, `UNMERGE`, `REVIEW_DECISION`, `ARCO_READ`, `ARCO_UPDATE`, `REHOMOLOGATE`, `PURGE_MARK`, `PURGE_SIMULATED` |
| `CAT_ELIGIBILITY_REASON` | CONTACT | `ELIGIBLE`, `DECEASED`, `MINOR`, `RNE_EXCLUSION`, `THIRD_PARTY_CONTACT`, `CONTACT_PURPOSE_DENIED`, `UNCONFIRMED_CONTACT`, `NO_ACTIVE_SERVICE`, `NO_CONSENT`, `CONSENT_REVOKED`, `CHANNEL_DENIED`, `FREQUENCY_EXCEEDED`, `SHARED_CONTACT_RESTRICTED`, `NO_CONTACT_POINT` |
| `CAT_PREF_ORIGIN` | CONTACT | Origen de una preferencia o de un vínculo de contacto: `TITULAR`, `LEGAL_REP`, `INTERNAL_POLICY`, `COLLECTIONS_MANAGEMENT` (aportado por la gestión de cobranza), `THIRD_PARTY_REFERENCE` (aportado por un tercero como referencia) |
| `CAT_CONTACT_USAGE_ROLE` | CONTACT | `OWNER`, `SHARED`, `GUARDIAN`, `REFERENCE` (el medio pertenece a un tercero; nunca elegible para finalidades distintas de COLLECTIONS) |
| `CAT_CONTACT_CONFIRMATION` | CONTACT | `CONFIRMED_BY_TITULAR` (el titular declaró el medio), `CONFIRMED_BY_CONTACT` (alguien contestó y confirmó la relación con la persona), `UNCONFIRMED` (aportado sin verificación, estado inicial de todo contacto de cobranza o de tercero), `WRONG_PERSON` (contestó otra persona sin relación), `INVALID` (no existe o no entrega). Solo `CONFIRMED_BY_TITULAR` habilita finalidades distintas a la de origen y puntúa en matching |
| `CAT_BLOCKING_STRATEGY` | MDM_OPS | `DOC_HASH`, `EMAIL_HASH`, `PHONE_HASH`, `SURNAME_SOUNDEX`, `NIT_HASH`, `LEGAL_NAME_TOKENS` |
| `CAT_GROUP_TYPE` | DEMOGRAPHICS | `FAMILY`, `CORPORATE_GROUP` |
| `CAT_GROUP_MEMBER_ROLE` | DEMOGRAPHICS | `ANCHOR`, `MEMBER`, `BENEFICIARY` |
| `CAT_ORG_TYPE` | BUSINESS | `SAS`, `LTDA`, `SA`, `ESAL` |
| `CAT_BUSINESS_UNIT` | BUSINESS | `SUBSIDIO`, `SALUD`, `EDUCACION`, `VIVIENDA`, `CREDITO`, `RECREACION`, `HOTELERIA_TURISMO`, `MERCADEO` (UES ilustrativas) |
| `CAT_SERVICE_KIND` | BUSINESS | `PERSISTENT` (relación sostenida en el tiempo: genera vínculo en el MDM), `TRANSACTIONAL` (consumo puntual: solo referencia, nunca vínculo) |
| `CAT_SERVICE` | BUSINESS | **Jerárquico bajo la UES** (`parent_value_sk` → valor de `CAT_BUSINESS_UNIT` replicado como nivel 1) con EAV obligatorios `service_kind` y `collections_applies`. Semilla PERSISTENT: `CUOTA_MONETARIA` (SUBSIDIO, beneficiario de subsidio familiar), `SALUD_EPS` y `SALUD_PLAN_COMPLEMENTARIO` (SALUD, usuarios de salud), `COLEGIO_MATRICULA` (EDUCACION), `SUBSIDIO_VIVIENDA` (VIVIENDA), `CREDITO_SOCIAL` y `TARJETA_CREDITO` (CREDITO, clientes de crédito; `collections_applies = true`), `CLUB_SOCIO` (RECREACION). Semilla TRANSACTIONAL: `PISCILAGO` (RECREACION), `HOTEL` (HOTELERIA_TURISMO), `SUPERMERCADO`, `DROGUERIA` (MERCADEO). La carga valida que `service_cd` pertenezca a la UES del rol y que sea PERSISTENT (regla dura §3.18) |
| `CAT_ENROLLMENT_STATUS` | BUSINESS | `ACTIVE`, `SUSPENDED`, `CLOSED` (estado del vínculo de servicio; `CLOSED` dispara el conteo de retención) |
| `CAT_RETENTION_RULE` | GOVERNANCE | Reglas de la política corporativa con EAV `years` y `trigger`: `AFFILIATE_5Y` (5 años desde fin de afiliación), `HR_5Y_POST_EXIT` (5 años post-egreso), `VENDOR_7Y`, `FINANCIAL_10Y` (10 años desde `closed_at` del último vínculo de CREDITO), `HEALTH_20Y` (20 años desde `closed_at` del último vínculo de SALUD; Res. 1995/1999 art. 15), `LEGAL_HOLD`, `PURGE_ELIGIBLE`. La regla aplicable se resuelve por UES del vínculo cerrado; prevalece la de mayor plazo |
| `CAT_CIIU` | BUSINESS | 5 códigos DIAN ilustrativos (necesarios para el peso CIIU del matching ORG) |

**Reutilizaciones declaradas (prohibido crear catálogos duplicados):** `purpose_cd`
→ `CAT_CONTACT_PURPOSE`; `MATCH_RULE.entity_type_cd` y `PARTY_BUCKET.party_type_cd`
→ `CAT_PARTY_TYPE`; `member_role_cd` → `CAT_GROUP_MEMBER_ROLE`;
`MATCH_REVIEW_TASK.task_status_cd` → `CAT_REQUEST_STATUS`;
`PARTY_CONTACT_PREF.purpose_cd` (canal y contacto) → `CAT_CONTACT_PURPOSE`;
`PARTY_CONTACT_POINT.origin_cd` → `CAT_PREF_ORIGIN`; `segment_type_cd` y
`segment_cd` → `CAT_SEGMENT_TYPE` (niveles 1 y 2); `PARTY_SERVICE_ENROLLMENT.business_unit_cd`
→ `CAT_BUSINESS_UNIT` (mismo valor que el nivel 1 de `CAT_SERVICE`).

**Homologaciones semilla en `rdm.SOURCE_VALUE_MAPPING`** (criterio de salida del RDM;
regla dura §3.4: sistema fuente exacto):

| Sistema | Campo fuente | Valor fuente | Canónico | Catálogo |
|---|---|---|---|---|
| SAP_ECC_HCM (`is_prototype_active=false`; se registra para que el crosswalk SEXKZ↔GESCHL sea verificable) | `SEXKZ` | `1` / `2` | `M` / `F` | CAT_GENDER |
| SAP_CRM | `GESCHL` | `1` / `2` | `M` / `F` | CAT_GENDER |
| SAP_CRM | `RLTYP` | `ZAFI` | `AFFILIATE` | CAT_PARTY_ROLE |
| SAP_CRM | `RLTYP` | `ZEMP` | `AFFILIATING_COMPANY` | CAT_PARTY_ROLE |
| SAP_ECC_SD | `LAND1` | `CO` | `COL` | CAT_COUNTRY |
| SAP_ECC_SD | `REGIO` | `ANT` | `05` | CAT_GEO_DIVIPOLA |
| SAP_ECC_MM | `LAND1` | `CO` | `COL` | CAT_COUNTRY |
| SAP_ECC_MM | `REGIO` | `ANT` | `05` | CAT_GEO_DIVIPOLA |
| SF_EC | `gender` | `M` / `F` | `M` / `F` | CAT_GENDER |
| SF_EC | `employmentStatus` | `T` (terminated) | `INACTIVE` | CAT_PARTY_STATUS |
| WEB_PORTAL | `tipo_doc` | `cedula` | `CC` | CAT_ID_TYPE |
| WEB_PORTAL | `categoria` | `A` / `B` / `C` | `AFFILIATION.A` / `.B` / `.C` | CAT_SEGMENT_TYPE |
| SAP_ECC_SD | `KTOKD` (grupo de cuentas) | `ZCRE` / `ZSAL` | `CREDITO_SOCIAL` / `SALUD_EPS` | CAT_SERVICE |
| SAP_ECC_SD | `LOEVM` (marca de borrado) | `X` | `CLOSED` | CAT_ENROLLMENT_STATUS |
| SAP_CRM | `RLTYP` | `ZSUB` | `CUOTA_MONETARIA` | CAT_SERVICE |
| SAP_CRM | `ZZ_ORIGEN_TEL` (origen del teléfono en BUT020/ADR2, campo Z) | `TIT` / `COB` / `REF` | `TITULAR` / `COLLECTIONS_MANAGEMENT` / `THIRD_PARTY_REFERENCE` | CAT_PREF_ORIGIN |

**Prueba canónica de salida del RDM (test obligatorio):** dado
(`SAP_CRM`, `GESCHL`, `1`), la vista `VW_RDM_SOURCE_TO_CANONICAL` y el endpoint
`GET /rdm/homologate` retornan `M`.

---

## 7. PIPELINE DE INGESTA — 7 ETAPAS (idéntico para toda fuente; solo cambia la Etapa 1)

```
1. Extracción  →  2. Landing Zone  →  3. Estandarización  →  4. Homologación
→  5. Calidad (DQ)  →  6. Crosswalk (XREF)  →  7. Carga MDM
```

1. **Extracción** — en el prototipo: lectura de CSV sintéticos que replican la
   estructura fuente (§7.1). Interfaz limpia `Extractor` por fuente para que en
   producción se sustituya por el conector real sin tocar las etapas 2–7. El
   `external_id` se toma **tal cual** del identificador nativo de la fuente
   (PERNR, KUNNR, LIFNR, PARTNER, user_id), sin ceros eliminados ni prefijos.
2. **Landing Zone** — insertar en `staging.STG_*_RAW` con `payload JSONB`,
   `source_hash` y `raw_status = PENDING`. Idempotencia por (`external_id`,
   `source_hash`): si el hash no cambió, no reprocesar.
3. **Estandarización** — TRIM, normalización Unicode NFC, mayúsculas consistentes,
   `nameparser` para nombres, `phonenumbers` a E.164 (+57...), email lowercase,
   dirección normalizada simple. **Sin tocar códigos** (regla dura §3.8).
4. **Homologación** — resolver cada código fuente contra
   `VW_RDM_SOURCE_TO_CANONICAL`. Código sin mapeo → el campo queda en `0 = UNKNOWN`
   y se registra `PARTY_DQ_ISSUE` categoría `VALIDITY` (reprocesable con
   `rehomologate`, §7.2).
5. **Calidad (DQ)** — validaciones categorizadas por `CAT_DQ_CATEGORY`
   (completitud de documento y nombre, validez de fecha de nacimiento, formato
   E.164, dígito de verificación NIT, DIVIPOLA existente, segmento hijo de su tipo,
   servicio perteneciente a su UES y de tipo PERSISTENT (regla dura §3.18), tipos
   de party permitidos en la relación).
   Registro que falla reglas bloqueantes → `raw_status = DQ_QUARANTINE`; el resto
   continúa con sus hallazgos registrados.
6. **Crosswalk** — lookup en `XREF_PARTY_SOURCE` por (`source_system_cd`,
   `external_id`): si existe → actualización directa del party vinculado (sin
   matching, regla dura §3.11); si no existe → pasa a matching (§8). Si el documento
   ya pertenece a un GOLDEN distinto (regla dura §3.16) → matching forzado con
   hallazgo `UNIQUENESS`.
7. **Carga MDM** — upsert en las tablas de las capas 2–5 y 8 con linaje por fila
   (los vínculos de servicio se crean o cierran según el estado en la fuente y
   generan/actualizan su `PARTY_DATA_RETENTION` al cerrarse),
   resolución de puntos de contacto contra `CONTACT_POINT` por (`channel_cd`,
   `contact_hash`) (si el número ya existe se vincula, nunca se duplica; el vínculo
   nace con `origin_cd` homologado desde la fuente; cuando el origen es cobranza o
   tercero, `confirmation_status_cd = UNCONFIRMED` y la carga escribe sus
   **preferencias por contacto**: (COLLECTIONS, true), (BENEFITS, false),
   (COMMERCIAL, false), con `origin_cd` igual al del vínculo; cuando lo declaró el
   titular, `CONFIRMED_BY_TITULAR` y sin filas de contacto, es decir, hereda las
   preferencias del canal), aplicación
   de survivorship (§9), recálculo de `completeness_score`, materialización de
   elegibilidad de contacto, y escritura en `PARTY_AUDIT_LOG` por cada cambio (con
   `source_system_cd` y `batch_id`).

**CLI (simula los DAGs de producción, mismos nombres lógicos):**
`python cli.py ingest --source sf_ec --mode full` · `--mode delta` ·
equivalentes `ecc_sd`, `ecc_mm`, `crm_bp`, `web_portal` ·
`python cli.py rne-sync --file app/synth/rne_sample.csv` (§10.3) ·
`python cli.py rehomologate --catalog CAT_GENDER` (§7.2) ·
`python cli.py purge --dry-run` (§10.5). En producción estos son DAGs de Airflow
(`sf_ec_full_load`, `sf_ec_delta_nightly` 02:00, `ecc_sd_delta_nightly` 02:30,
`rne_sync_daily`, streams de eventos) — mantener nombres.

### 7.1 Contrato de entrada — extractores nativos SAP (documentación, no implementación)

Los CSV sintéticos del prototipo replican estas estructuras; en producción los
extractores son (las versiones legacy **no** exponen REST — solo RFC/BAPI, IDoc vía
ALE y extractores ABAP/BW; JDBC directo a tablas solo DEV/auditoría, nunca
producción):

| Fuente | Entidad | ID nativo (`external_id`) | Carga masiva | Delta | Tiempo real |
|---|---|---|---|---|---|
| SuccessFactors EC | Empleados | `personIdExternal` | Compound Employee API (OAuth2, paginación) | OData v2/v4 por `lastModifiedDateTime` (`PerPerson`, `PerPersonal`, `PerNationalId`, `PerPhone`, `PerEmail`...) | Integration Center/BTP: eventos `NewHire`, `DataChange`, `Termination`, `Transfer`, `Rehire` |
| SAP ECC 6.0 SD | Interlocutores comerciales (`KNA1`; roles en `BPROL`) | `KUNNR` | `BAPI_CUSTOMER_GETLIST/GET_DETAIL/GET_DETAIL2` + DataSource `0CUSTOMER_ATTR` | `KNA1.AEDAT` | IDoc `DEBMAS08` (ALE) |
| SAP ECC 6.0 MM | Proveedores (`LFA1`) | `LIFNR` | BAPIs de vendor + DataSource `0VENDOR_ATTR` | — | IDoc `CREMAS08` (ALE) |
| SAP CRM | Business Partner (`BUT000`/`BUT020`/`ADRC`) | `PARTNER` | `BAPI_BUPA_GET_DETAIL` + DataSource `0CRM_BUPA_MAIN_ATTR` | — | IDocs `CRMBUPA01`/`CRMBUPA02`; roles por `RLTYP` con códigos Z (`ZAFI`, `ZEMP`) |
| Portal web | Usuarios digitales | `user_id` | Export CSV | por `updated_at` | Webhook |

### 7.2 Rehomologación tras cambios en el RDM

Cuando se agrega una homologación en `SOURCE_VALUE_MAPPING` (Admin RDM o
`POST /rdm/mappings`), los registros que quedaron en `0 = UNKNOWN` por ese campo se
reprocesan sin nueva extracción: `rehomologate --catalog <code>` relee el `payload`
de staging, resuelve el código, actualiza el party, cierra el `PARTY_DQ_ISSUE`
(`resolved_at`) y audita con acción `REHOMOLOGATE`. Es la materialización operativa
de la regla dura §3.1: el RDM gobierna al MDM también después de la carga.

---

## 8. MATCHING (motor de deduplicación)

### 8.1 Blocking
Por `party_type_cd` (regla dura §3.17). PERSON: hash exacto de documento, hash
exacto de email, hash exacto de teléfono E.164, más **Soundex del primer apellido**
(variante tolerante al español). ORGANIZATION: hash de NIT y tokens de razón social
(sin `S.A.S.`, `LTDA`, `de Colombia`). Registrar bloques en `PARTY_BUCKET` /
`BUCKET_CANDIDATE`. Recordar: XREF primero (§3.11).

### 8.2 Pesos PERSON (sembrar en `MATCH_RULE`, versión 1)

| Atributo | Peso | Regla |
|---|---|---|
| Documento | 30 | exacto; si coincide número con distinto tipo: +15 en lugar de +30 |
| Primer apellido | 20 | Jaro-Winkler ≥ 0.92 + Soundex español |
| Primer nombre | 15 | Jaro-Winkler ≥ 0.90 |
| Fecha de nacimiento | 15 | exacto / ±1 año (puntaje parcial) |
| Segundo apellido | 10 | Jaro-Winkler ≥ 0.92 |
| Email | 5 | exacto normalizado |
| Teléfono E.164 | 3 | exacto **solo si el vínculo es OWNER y `CONFIRMED_BY_TITULAR` en ambos** (un celular compartido, de referencia o no confirmado no suma evidencia de identidad) |
| Municipio DIVIPOLA | 2 | exacto |

### 8.3 Pesos ORGANIZATION

| Atributo | Peso | Regla |
|---|---|---|
| NIT | 50 | exacto; validar dígito de verificación |
| Razón social | 25 | JW + tokenización, ignorando `S.A.S.`, `LTDA`, `de Colombia` |
| Nombre comercial | 10 | JW |
| Municipio / País | 10 | exacto |
| CIIU | 5 | exacto |

### 8.4 Umbrales de decisión (0–100)

| Rango | Decisión | Acción |
|---|---|---|
| ≥ 85 | `AUTO_MERGE` | merge automático + `PARTY_MERGE_HISTORY` (`merge_type=AUTO`) |
| 70–84 | `PROBABLE` | cola de la Consola de Stewardship (§8.5) |
| 50–69 | `POSSIBLE` | registrar en `PARTY_MATCH`, sin acción |
| < 50 | `NO_MATCH` | descartar (opcionalmente registrar el mejor score) |

Cada comparación guarda en `PARTY_MATCH.score_detail` el **desglose por atributo**
(valor A, valor B, algoritmo, similitud, puntos) y la `rule_version` — es la
evidencia que consume la consola y la trazabilidad exigida como sistema algorítmico
de decisión sobre datos personales (Ley 1581/2012; NIST AI RMF 1.0 MAP/MEASURE;
ISO/IEC 42001:2023 cl. 6.1).

### 8.5 Zona gris: decisión del steward y workflow entre owners de fuente

1. Todo `PROBABLE` entra a la cola de la consola con `match_status = PENDING`.
2. El steward del MDM puede decidir directamente (`MERGE` / `NO_MATCH`, justificación
   obligatoria) **solo si ambos parties provienen de una única fuente**.
3. Si los parties involucran **dos o más fuentes** (según `XREF_PARTY_SOURCE`), o el
   steward elige `ESCALATE`, el sistema crea **una `MATCH_REVIEW_TASK` por fuente
   afectada**, asignada al `data_steward` de esa fuente (`SOURCE_SYSTEM`), con
   `due_at = created_at + 5 días hábiles` y `match_status = IN_REVIEW`.
4. Regla de cierre: **todos** los owners deciden `MERGE` → merge con
   `merge_type = OWNER_CONSENSUS`; **cualquiera** decide `NO_MATCH` → el match se
   resuelve `NO_MATCH` y se registra la justificación de cada owner; decisiones
   divididas o tarea vencida → escalamiento a la Jefatura de Gobierno de Datos (owner
   del MDM), que decide con `merge_type = MANUAL_OVERRIDE` y justificación. Cada
   decisión escribe `PARTY_AUDIT_LOG` con acción `REVIEW_DECISION`.
5. Fundamento: la decisión sobre identidad de un titular es responsabilidad del
   responsable del tratamiento (Ley 1581/2012 art. 17) y exige supervisión humana
   identificable sobre un sistema algorítmico (ISO/IEC 42001:2023 cl. 6.1; NIST AI
   RMF 1.0 función GOVERN).

### 8.6 Prevención de duplicados en origen (`match-preview`)

`POST /parties/match-preview` recibe los atributos de un registro que una fuente está
a punto de crear, corre blocking + scoring contra los goldens **sin persistir nada**
y devuelve los candidatos con score y desglose. Permite que un sistema fuente (o el
portal web) advierta "esta persona ya existe" antes de crear un duplicado. Misma
`MatchingEngine` que el batch; ninguna lógica duplicada.

**Implementación del prototipo:** RapidFuzz (JW) + Jellyfish (Soundex). Dejar la
interfaz `MatchingEngine` desacoplada: producción la sustituye por Splink
(Fellegi-Sunter + EM, backend DuckDB/Spark) para >10M registros.

---

## 9. SURVIVORSHIP (construcción del golden record)

Estrategias soportadas: `SOURCE_PRIORITY`, `MOST_RECENT`, `MOST_COMPLETE`,
`MOST_FREQUENT`, `MANUAL_OVERRIDE`. Configuración base (sembrar):

| Campo | Estrategia | Detalle |
|---|---|---|
| nombre | `SOURCE_PRIORITY` | `SF_EC > SAP_CRM > SAP_ECC_SD > SAP_ECC_MM > WEB_PORTAL` |
| documento | `SOURCE_PRIORITY` | `SF_EC > SAP_CRM > SAP_ECC_SD > SAP_ECC_MM > WEB_PORTAL` |
| fecha de nacimiento | `SOURCE_PRIORITY` | `SF_EC > SAP_CRM > SAP_ECC_SD > SAP_ECC_MM > WEB_PORTAL` |
| fecha de fallecimiento / estado DECEASED | `MOST_RECENT` | cualquier fuente que lo informe prevalece sobre ACTIVE (principio de veracidad, Ley 1581/2012 art. 4 lit. d) |
| email / teléfono (vínculo primario) | `MOST_RECENT` | por `captured_at` del vínculo `PARTY_CONTACT_POINT` |
| segmentos | por tipo | cada `segment_type_cd` tiene fuente autoritativa (EAV `authoritative_source` en el valor de nivel 1): AFFILIATION → SAP_CRM; FINANCIAL_RISK → SAP_ECC_SD; COMMERCIAL → WEB_PORTAL; sin fuente autoritativa → `MOST_RECENT` |
| roles | `UNION` | los roles no compiten: se conservan todos con su linaje (una persona es empleado y afiliado a la vez) |
| vínculos de servicio | `UNION` por `source_reference` | cada vínculo pertenece a la fuente que lo administra (CREDITO_SOCIAL → SAP_ECC_SD; CUOTA_MONETARIA → SAP_CRM); nunca compiten entre fuentes; el estado lo fija su fuente administradora |
| resto | `MOST_COMPLETE` | fallback sin prioridad de fuente definida |

Justificación de la prioridad (mantener en la documentación): el rango 1 pertenece
al sistema de registro de RR. HH. — en producción `SAP_ECC_HCM` — porque el nombre
legal está validado contra RNEC y los documentos están validados para la
vinculación laboral. **En el prototipo ese rango lo hereda `SF_EC`**;
`SAP_ECC_HCM` permanece registrado con `is_prototype_active = false`. Cada campo
ganador queda registrado en `PARTY_SURVIVORSHIP` (estrategia, fuente ganadora,
valor, timestamp) y cada ejecución incrementa `PARTY.golden_version`. Un merge
decidido en la consola re-ejecuta survivorship sobre el party sobreviviente; un
unmerge restaura desde `pre_merge_snapshot` y re-ejecuta survivorship en ambos.

---

## 10. CUMPLIMIENTO EMBEBIDO (no opcional)

1. **Auditoría** — middleware/servicio único de auditoría: todo
   insert/update/merge/unmerge/decisión en `mdm.*` escribe `PARTY_AUDIT_LOG` (Ley
   1581/2012 art. 17; ISO/IEC 27001:2022 A.8.15). Cambios de referencia →
   `RDM_AUDIT_LOG`. Los reapuntamientos de filas hijas durante merge/unmerge llevan
   `merge_sk`.
2. **ARCO con SLA** — `DATA_SUBJECT_REQUEST` implementa consultas y reclamos con
   `due_at` calculado en días hábiles (consultas 10, Ley 1581/2012 art. 14; reclamos
   15, art. 15; supresión/revocatoria conforme Decreto 1377/2013 art. 9). Toda
   lectura o cambio derivado de una solicitud lleva `arco_request_id` en el audit.
   `GET /arco/requests?sla=OVERDUE` lista las vencidas. La cancelación en el
   prototipo = revocar consents + marcar retención `PURGE_ELIGIBLE` (no borrado
   físico inmediato: trazabilidad primero).
3. **Contactabilidad (Ley 2300/2023 arts. 3 y 5; Res. CRC 7356/2024)** — la
   elegibilidad se computa por `(party_contact_sk, purpose_cd)` en este
   orden de precedencia, y el primer criterio que falla fija `reason_cd`:
   **(1)** `party_status_cd = DECEASED` → `DECEASED`;
   **(2)** titular menor de edad (derivado de `birth_date`) y finalidad COMMERCIAL →
   `MINOR` (Ley 1581/2012 art. 7; Decreto 1377/2013 art. 12);
   **(3)** `CONTACT_POINT.rne_excluded = true` y finalidad con `rne_applies = true`
   (solo COMMERCIAL) → `RNE_EXCLUSION`, prevalece sobre cualquier consentimiento
   (Ley 2300/2023 art. 5);
   **(4)** el vínculo del party con el contacto es SHARED o GUARDIAN y el OWNER del
   contacto es menor de edad y la finalidad es COMMERCIAL →
   `SHARED_CONTACT_RESTRICTED`;
   **(5)** vínculo con `usage_role_cd = REFERENCE` y finalidad distinta de
   COLLECTIONS → `THIRD_PARTY_CONTACT` (el medio de un tercero solo existe para la
   gestión que lo originó; Ley 1581/2012 art. 4 lit. b, principio de finalidad);
   **(6)** existe preferencia **de contacto** (`PARTY_CONTACT_PREF.party_contact_sk`
   = este vínculo) para la finalidad con `allowed = false` → `CONTACT_PURPOSE_DENIED`
   (prevalece sobre la preferencia de canal);
   **(7)** `confirmation_status_cd` distinto de `CONFIRMED_BY_TITULAR` y la finalidad
   consultada **no** tiene preferencia de contacto con `allowed = true` →
   `UNCONFIRMED_CONTACT` (un contacto no confirmado solo sirve para las finalidades
   que se le habilitaron explícitamente); `WRONG_PERSON` e `INVALID` → no elegible
   para ninguna finalidad;
   **(8)** finalidad COLLECTIONS sin ningún `PARTY_SERVICE_ENROLLMENT` en estado
   ACTIVE o SUSPENDED cuyo servicio tenga `collections_applies = true` →
   `NO_ACTIVE_SERVICE` (la cobranza solo es legítima sobre una obligación vigente,
   Ley 2300/2023 art. 3);
   **(9)** sin consent `GRANTED` del tipo requerido por la finalidad (EAV
   `required_consent_type`) → `NO_CONSENT` / `CONSENT_REVOKED`;
   **(10)** sin preferencia de contacto para la finalidad y preferencia **de canal**
   con `allowed = false` → `CHANNEL_DENIED`;
   **(11)** frecuencia excedida → `FREQUENCY_EXCEEDED`;
   **(12)** en otro caso → `ELIGIBLE`.
   La sincronización del RNE se simula con `python cli.py rne-sync --file
   app/synth/rne_sample.csv`: marca `rne_excluded = true` en los `CONTACT_POINT`
   cuyo hash coincide y **nunca toca preferencias ni finalidades distintas de
   COMMERCIAL** (la cobranza y los beneficios se rigen por el art. 3, no por el
   registro). Este numeral materializa el compromiso del caso financiero ante el
   Comité con fuente declarada y trazable.
4. **Audiencias (caso financiero 3 y habilitación de SAP CDP)** —
   `GET /audiences?purpose=COMMERCIAL&channel=EMAIL&role=AFFILIATE&segment=AFFILIATION.A&service=CREDITO_SOCIAL&enrollment_status=ACTIVE`
   devuelve únicamente parties `GOLDEN`, `ACTIVE`, con contacto elegible para esa
   finalidad y canal (y, si se filtra por servicio, con vínculo en ese estado), con el valor de contacto y el `reason_cd = ELIGIBLE`. Toda
   ejecución se audita (`actor`, filtros, conteo) porque es un tratamiento con
   finalidad declarada (Ley 1581/2012 art. 4 lit. b). Reemplaza la consolidación
   manual de bases de campaña descrita en el caso de negocio.
5. **Retención y purga simulada** — `PARTY_DATA_RETENTION` se puebla en la carga
   según el rol (`CAT_RETENTION_RULE`, EAV `years`/`trigger`). `python cli.py purge
   --dry-run` lista los parties cuyo `purge_after` venció, sin `LEGAL_HOLD` y sin
   relación activa, y audita `PURGE_SIMULATED`. El prototipo **nunca borra**; la
   purga real es producción.
6. **Datos sintéticos únicamente** — el generador jamás usa datos reales; los
   documentos sintéticos usan rangos no plausibles marcados como ficticios en la UI.
   El MDM **no almacena contenido clínico ni financiero**: solo la autorización
   (`PARTY_CONSENT`) y su evidencia.

---

## 11. API — CONTRATO DE ENDPOINTS (FastAPI, prefijo `/api/v1`)

| Método y ruta | Función |
|---|---|
| `GET /parties?q=&role=&segment=&service=&status=&limit=` | Búsqueda de parties (nombre normalizado, documento, email, ID externo por fuente) |
| `GET /parties/{party_sk}/golden` | Vista 360 del golden record: las 8 capas + survivorship por campo + `golden_version` + `completeness_score` |
| `GET /parties/{party_sk}/sources` | Fuentes que alimentan el party (`XREF`) y, por cada fila de hechos, su `source_system_cd` y `captured_at` |
| `GET /parties/{party_sk}/relationships?direction=both` | Relaciones directas e inversas con tipo, dirección y tipo de party en cada extremo |
| `GET /parties/{party_sk}/services?status=` | Vínculos de servicio persistentes con UES, rol, estado, fechas, referencia en la fuente y linaje |
| `GET /parties/{party_sk}/audit?merge_sk=&arco_request_id=` | Trazabilidad del party, filtrable por merge o por solicitud ARCO |
| `POST /pipeline/{source}/run?mode=full\|delta` | Ejecutar ingesta de una fuente |
| `POST /parties/match-preview` | Body con atributos de un registro → candidatos y score sin persistir (§8.6) |
| `GET /matches?decision=PROBABLE&status=PENDING` | Cola de stewardship |
| `GET /matches/{match_sk}` | Detalle con `score_detail` desglosado, fuentes de cada party y tareas de revisión |
| `POST /matches/{match_sk}/decision` | Body: `{action: MERGE\|NO_MATCH\|ESCALATE, justification}` (justificación obligatoria) → decide o crea tareas por owner (§8.5) |
| `GET /review-tasks?assignee=&status=` | Tareas de revisión por owner de fuente |
| `POST /review-tasks/{task_sk}/decision` | Body: `{decision: MERGE\|NO_MATCH\|ESCALATE, justification}` → aplica la regla de cierre |
| `POST /parties/{party_sk}/unmerge` | Body: `{merge_sk, reason}` → restaura desde `pre_merge_snapshot`, reapunta filas hijas, re-survivorship, audita |
| `GET /rdm/domains` · `GET /rdm/catalogs` · `GET /rdm/catalogs/{code}/values` | Navegación RDM (jerarquías incluidas) |
| `POST /rdm/catalogs/{code}/values` | Alta de valor canónico (nunca edita códigos publicados) |
| `POST /rdm/catalogs/{code}/values/{value_code}/deprecate` | Deprecación (inmutabilidad §3.7) |
| `GET /rdm/homologate?system=SAP_CRM&field=GESCHL&value=1` | → `M` (prueba canónica RDM) |
| `POST /rdm/mappings` | Alta de homologación fuente→canónico |
| `POST /rdm/rehomologate?catalog=` | Reprocesa los `UNKNOWN` del catálogo (§7.2) |
| `GET /parties/{party_sk}/contactability?contact_point_sk=&purpose=COMMERCIAL` | → `{is_eligible, reason, usage_role, origin, confirmation_status, purposes: [{purpose, allowed, level: CONTACT\|CHANNEL\|DEFAULT}]}` por punto de contacto; sin `contact_point_sk` devuelve todos los vínculos del party |
| `GET /parties/{party_sk}/contacts?purpose=COLLECTIONS&confirmation=UNCONFIRMED` | Vínculos de contacto filtrables por finalidad habilitada, origen, rol de uso y confirmación (lista de trabajo de cobranza) |
| `PUT /parties/{party_sk}/contacts/{party_contact_sk}/purposes` | Body: `[{purpose, allowed, frequency?}]` → escribe/cierra las preferencias de contacto (una fila por finalidad), recalcula elegibilidad y audita; nunca borra el histórico |
| `POST /parties/{party_sk}/contacts/{party_contact_sk}/confirmation` | Body: `{status: CONFIRMED_BY_TITULAR\|CONFIRMED_BY_CONTACT\|WRONG_PERSON\|INVALID, evidence}` → actualiza el estado desde la gestión, recalcula elegibilidad y audita |
| `GET /audiences?purpose=&channel=&role=&segment=&service=&enrollment_status=` | Audiencia elegible (§10.4) |
| `POST /parties/{party_sk}/consents` | Alta/cambio de autorización por tipo (crea fila nueva, cierra la anterior) |
| `PUT /parties/{party_sk}/preferences` | Body: `[{channel, purpose, allowed, frequency?}]` → preferencias **de canal** (`party_contact_sk` NULL) |
| `POST /parties/{party_sk}/arco` · `GET /arco/requests?sla=OVERDUE` | Solicitudes ARCO con `due_at` y estado de SLA derivado |
| `POST /rne/sync` | Equivalente API de `rne-sync` |
| `GET /retention/purge-candidates` | Simulación de purga (§10.5) |
| `GET /changes?since=&entity=&limit=&cursor=` | **Feed de cambios del golden** para consumidores (SAP CDP, campañas, analítica): derivado de `PARTY_AUDIT_LOG` (sin tabla nueva), devuelve `party_sk`, entidad, acción, `golden_version` y `occurred_at`; en producción es el mismo contrato que el tópico Kafka |
| `GET /stats` | Contadores para el dashboard desde `LOAD_BATCH` y las tablas núcleo (parties por estado, goldens, matches por decisión, tareas abiertas, DQ, ARCO vencidas, última carga por fuente) |

---

## 12. UI (React + Vite + Tailwind) — TRES MÓDULOS

1. **Consola de Stewardship** (la pieza central — regla dura §3.12):
   cola de casos `PROBABLE` → vista de comparación **lado a lado** de los dos
   registros con: score total, desglose por atributo (barra de puntos, valores A/B
   resaltando diferencias), fuente y fecha de cada valor, roles, segmentos,
   relaciones y contactos compartidos de cada party. Acciones: **Fusionar** / **No es
   la misma persona** / **Escalar**, siempre con justificación obligatoria. Pestaña
   **Tareas por owner** (las `MATCH_REVIEW_TASK` asignadas al usuario, con `due_at`
   y estado de la regla de cierre). Pestaña de historial de merges con acción de
   **unmerge** trazable y vista del `pre_merge_snapshot`. Esto NO es un flujo de
   aprobación: es una herramienta de evidencia para juicio experto de dominio.
2. **Admin RDM**: navegación dominio → catálogo → valores (con jerarquía para
   DIVIPOLA, segmentos y servicios), alta de valores, deprecación (nunca edición de
   códigos publicados), gestión de homologaciones por sistema fuente, **probador de
   homologación** (inputs sistema/campo/valor → canónico) y botón **Rehomologar**
   que muestra cuántos registros `UNKNOWN` se corregirán.
3. **Vista 360 del golden record**: cabecera con resumen ejecutivo (elegibilidad por finalidad
   con su razón, servicios activos por UES, hallazgos DQ abiertos, pares de matching pendientes,
   fuentes, merges y autorizaciones; marcas de menor de edad y fallecido) y perfil recorriendo las 8 capas en
   orden (Sources → Core → Identity → Roles y Relaciones → Contactability →
   Governance → Golden Record → Consents), con la fuente ganadora por campo
   (survivorship) visible, el linaje de cada fila, los segmentos por tipo, los
   vínculos de servicio por UES con su estado y referencia, el grafo de relaciones
   (persona/organización), los contactos con su rol de uso (propio,
   compartido, acudiente, referencia), origen, **finalidades habilitadas y denegadas
   por contacto** (con indicación de si vienen del contacto o del canal), estado de
   confirmación y la elegibilidad por contacto y finalidad (los de cobranza no
   confirmados se muestran agrupados y marcados). Usar la
   leyenda de colores del modelo: Core azul, Identity amarillo, Contactability
   púrpura, Relationships verde, Governance naranja, Golden Record rosa, Consents
   rojo, Reference gris.

Estética: limpia, corporativa, en español; banner visible "Prototipo — datos
sintéticos".

---

## 13. DATOS SINTÉTICOS Y ESCENARIO DEMO

Generador (`app/synth/`) con **seed fija** (reproducible): ~800 personas y ~120
organizaciones distribuidas en las 5 fuentes con solapamiento controlado, incluidos
~60 grupos familiares con contactos compartidos y ~10 grupos empresariales. Casos
plantados (cada uno con test que verifica su desenlace):

| Caso | Construcción | Desenlace esperado |
|---|---|---|
| A · Auto-merge | Misma persona en ECC_SD y CRM: mismo documento, nombre con variación tipográfica leve | score ≥ 85 → merge automático + survivorship aplicado + `golden_version` incrementado |
| B · Probable, una fuente | Misma persona dos veces en WEB_PORTAL (usuario re-registrado): sin documento común, JW alto + misma fecha de nacimiento | 70–84 → consola; el steward decide MERGE directamente (una sola fuente) → merge + audit |
| C · Posible | Homónimos con fecha de nacimiento distinta | 50–69 → queda en `PARTY_MATCH`, sin acción |
| D · Org duplicada | Mismo NIT, razón social `"La Espiga S.A.S."` vs `"LA ESPIGA"` | ≥ 85 → auto-merge de organización |
| E · No contacto | Titular con consent `COMMERCIAL` REVOKED y pref `WHATSAPP` denegada | `contactability` → `is_eligible=false`, `reason=CONSENT_REVOKED` |
| F · ARCO | Solicitud de supresión sobre un party fusionado | `DATA_SUBJECT_REQUEST` creada con `due_at` a 15 días hábiles; audit con `arco_request_id`; consents revocados; retención `PURGE_ELIGIBLE` |
| G · Caché XREF | Segunda corrida delta de ECC_SD con los mismos `KUNNR` | 0 comparaciones de matching (todo resuelto por XREF) |
| H · Exclusión RNE | Titular con consent `COMMERCIAL` GRANTED cuyo celular está en el RNE simulado | PHONE/COMMERCIAL → `RNE_EXCLUSION`; **PHONE/COLLECTIONS del mismo titular sigue `ELIGIBLE`** |
| I · Segmentos multi-tipo | Afiliado con segmento AFFILIATION=A (CRM), FINANCIAL_RISK=HIGH (ECC_SD) y COMMERCIAL=PREMIUM (portal) | Vista 360 muestra los tres vigentes con su fuente; intentar un segundo AFFILIATION vigente falla por UNIQUE |
| J · Contacto compartido | Grupo familiar: celular del hijo (menor) vinculado al hijo como OWNER y a la madre como GUARDIAN | Un solo `CONTACT_POINT`; madre: PHONE/BENEFITS `ELIGIBLE`, PHONE/COMMERCIAL `SHARED_CONTACT_RESTRICTED`; hijo: COMMERCIAL `MINOR`; el teléfono compartido no suma puntos en el matching madre↔hijo |
| K · Zona gris entre owners | Probable entre SF_EC y CRM; steward escala | Se crean 2 `MATCH_REVIEW_TASK` (SF_EC y SAP_CRM); ambos deciden MERGE → merge `OWNER_CONSENSUS`; variante: uno decide NO_MATCH → resuelto `NO_MATCH` con ambas justificaciones |
| L · Unmerge | Auto-merge del caso A revertido por el steward con razón | Ambos parties restaurados desde `pre_merge_snapshot` (roles, contactos, XREF, consents), `MERGED` vuelve a `GOLDEN`, survivorship re-ejecutado, audit agrupado por `merge_sk` |
| M · Audiencia | `GET /audiences?purpose=COMMERCIAL&channel=EMAIL&role=AFFILIATE` | Excluye fallecidos, menores, RNE, sin consent y canal denegado; la ejecución queda auditada con conteo |
| N · Prevención en origen | `match-preview` con los datos del caso A antes de crearlo | Devuelve el golden existente con score ≥ 85 y nada se persiste |
| O · Relaciones P/O | Persona LEGAL_REP_OF organización; organización SUBSIDIARY_OF organización; padres PARENT_OF hijo | Las tres se consultan desde ambos extremos con la inversa generada; un `SPOUSE_OF` persona→organización es rechazado en DQ |
| P · Rehomologación | Registro CRM con `RLTYP=ZPRV` sin mapeo → `UNKNOWN` + DQ `VALIDITY`; se agrega el mapeo ZPRV→VENDOR y se ejecuta `rehomologate` | El rol queda VENDOR, el hallazgo cerrado (`resolved_at`), audit `REHOMOLOGATE`, sin nueva extracción |
| Q · Fallecido y SLA | SF_EC informa terminación por fallecimiento; una consulta ARCO creada hace 12 días hábiles | `party_status=DECEASED` y toda elegibilidad `DECEASED`; la solicitud aparece en `GET /arco/requests?sla=OVERDUE` |
| R · Vínculos de servicio | Afiliado con CUOTA_MONETARIA (CRM), dos CREDITO_SOCIAL (SD, referencias distintas, uno CLOSED) y SALUD_EPS (SD); el mismo registro trae una estadía en HOTEL y una compra en SUPERMERCADO | Cuatro `PARTY_SERVICE_ENROLLMENT` (uno CLOSED con `PARTY_DATA_RETENTION` FINANCIAL_10Y desde `closed_at`); HOTEL y SUPERMERCADO rechazados con `VALIDITY` "servicio transaccional no vinculable"; Vista 360 muestra los roles a nivel de UES y los vínculos debajo |
| S · Cobranza solo con obligación vigente | Titular con consent DATA_PROCESSING GRANTED y teléfono elegible, sin ningún vínculo de CREDITO activo | PHONE/COLLECTIONS → `NO_ACTIVE_SERVICE`; al cargar un CREDITO_SOCIAL ACTIVE en delta → `ELIGIBLE` (recálculo de caché por cambio de vínculo); PHONE/BENEFITS no cambia |
| T · Finalidades por contacto y teléfonos de cobranza | Cliente de CREDITO_SOCIAL ACTIVE con: email declarado con preferencias de contacto (BENEFITS true, COLLECTIONS true, COMMERCIAL false) aunque el canal EMAIL esté permitido para COMMERCIAL; celular declarado (OWNER, CONFIRMED_BY_TITULAR, sin filas de contacto); y tres teléfonos aportados por la gestión: origen COLLECTIONS_MANAGEMENT (OWNER, UNCONFIRMED), tercero (REFERENCE, UNCONFIRMED) y uno WRONG_PERSON, cada uno con sus filas (COLLECTIONS true, BENEFITS false, COMMERCIAL false) | Email: BENEFITS y COLLECTIONS `ELIGIBLE`, COMMERCIAL `CONTACT_PURPOSE_DENIED` (la fila de contacto prevalece sobre el canal); PHONE/COLLECTIONS: declarado, cobranza y referencia `ELIGIBLE`, WRONG_PERSON no elegible; PHONE/COMMERCIAL: solo el declarado `ELIGIBLE`, los demás `CONTACT_PURPOSE_DENIED` o `THIRD_PARTY_CONTACT`; `GET /audiences?purpose=COMMERCIAL&channel=PHONE` devuelve un único número y `channel=EMAIL` ninguno; al confirmar el de cobranza como `CONFIRMED_BY_TITULAR` y escribir (COMMERCIAL, true) vía `PUT .../purposes`, pasa a elegible comercial con audit; ninguno de los tres teléfonos de gestión puntúa en matching |
| U · Vitrina 360 (persona completa) | Una persona en las cinco fuentes (SF_EC, SAP_CRM, SAP_ECC_SD, SAP_ECC_MM, WEB_PORTAL) con el mismo documento, cuatro roles declarados por la fuente (EMPLOYEE, AFFILIATE, VENDOR, DIGITAL_USER), los tres tipos de segmento, vínculos de servicio en tres UES, relaciones persona↔organización (EMPLOYEE_OF con la empresa afiliadora, LEGAL_REP_OF y SHAREHOLDER_OF con su sociedad) y persona↔persona (SPOUSE_OF, PARENT_OF/CHILD_OF y BENEFICIARY_OF de su hija), grupo familiar, contactos por rol de uso y origen, autorizaciones y un segundo registro del portal sin documento | Un golden con cuatro merges AUTO y survivorship por campo; la Vista 360 muestra las ocho capas pobladas y la Consola de Stewardship el par `PROBABLE` con la evidencia A/B de roles, segmentos, servicios y relaciones |

`make demo` = levantar → migrar → sembrar RDM → generar sintéticos → ingerir las 5
fuentes → `rne-sync` → correr matching → dejar la consola con los casos B y K
pendientes. `DEMO.md` narra el guion sobre estos 21 casos.

---

## 14. PLAN DE CONSTRUCCIÓN POR FASES Y CRITERIOS DE ACEPTACIÓN

| Fase | Contenido | Criterios de aceptación (todos verificados por pytest donde aplique) |
|---|---|---|
| **F0** | Scaffolding: repo, docker-compose (db+api+ui) y `make db-local` sin Docker, Alembic, Makefile, healthchecks, `docs/reference/`, `docs/drive/` | `docker compose up` levanta los 3 servicios; `GET /health` OK; `make test` corre |
| **F1 · RDM** | Esquema `rdm` (con `data_owner`/`data_steward`), migración semilla (43 catálogos poblados, miembros 0/−1, EAV de relaciones, finalidades y servicios con `service_kind`), vistas (3 tipadas), endpoints RDM, trigger de inmutabilidad | Prueba canónica: (`SAP_CRM`,`GESCHL`,`1`) → `M` por vista y por endpoint; UPDATE a un canónico activo es rechazado; deprecar funciona; `VW_RDM_CROSSWALK` resuelve `SEXKZ=1` ↔ `GESCHL=1`; `VW_RDM_CAT_RELATIONSHIP_TYPE` expone from/to/inverso; ningún mapeo usa un sistema no registrado |
| **F2 · Staging + pipeline** | Esquema `staging` (5 RAW + `LOAD_BATCH`) + `mdm` (29 tablas; índices de §5.4; FKs cruzadas al final vía `ALTER TABLE`; índice de unicidad golden), generador sintético, etapas 1–5, CLI, `rehomologate` | Ingesta de las 5 fuentes deja registros `DQ_PASSED`/`DQ_QUARANTINE` correctos; homologación aplicada; hallazgos en `PARTY_DQ_ISSUE`; sin campos multivaluados; linaje presente en toda fila de hechos; contactos resueltos sin duplicar valores; casos I, O, P y R pasan |
| **F3 · Matching + Golden** | Etapas 6–7, blocking por tipo, scoring, umbrales, merge automático, survivorship, `pre_merge_snapshot`, `match-preview`, unmerge | Casos A, C, D, G, L y N pasan; `score_detail` desglosado presente; XREF evita re-matching; survivorship registra fuente ganadora por campo; el teléfono compartido o no confirmado no puntúa |
| **F4 · UI + workflow** | Consola de Stewardship con tareas por owner, Admin RDM, Vista 360 | Casos B y K decidibles desde la consola; regla de cierre entre owners verificada; unmerge desde UI; alta de valor y homologación desde Admin RDM sin tocar SKs; rehomologar desde UI |
| **F5 · Cumplimiento + demo** | Contactabilidad por contacto, consents multi-tipo, ARCO con SLA, `rne-sync`, audiencias, feed de cambios, purga simulada, `make demo`, `make export-drive`, `DEMO.md`, `README.md` | Casos E, F, H, J, M, Q, S y T pasan; `make demo` end-to-end en verde desde cero; suite completa en verde |

---

## 15. TRAZABILIDAD DE NECESIDADES → MODELO (verificación de cobertura)

| Necesidad | Resuelta por |
|---|---|
| Varios segmentos por party (afiliación, riesgo financiero...) | `PARTY_SEGMENT` + `CAT_SEGMENT_TYPE` jerárquico; caso I |
| Varias autorizaciones por finalidad (comercial, financiera, historia clínica) | `PARTY_CONSENT` una fila por `consent_type_cd`; `CAT_CONSENT_TYPE` ampliado; mapeo finalidad→consentimiento en EAV |
| Relaciones P↔P, O↔P, O↔O con tipo | `PARTY_RELATIONSHIP` sobre el supertipo `PARTY`; EAV de tipos permitidos e inversa; caso O |
| Todos los roles y el servicio | `PARTY_ROLE` N filas a nivel de UES + `PARTY_SERVICE_ENROLLMENT` por vínculo persistente (`CAT_SERVICE` con `service_kind`); survivorship `UNION`; casos R y S |
| Integración respetando IDs originales | `XREF_PARTY_SOURCE.external_id` nativo; regla dura §3.4; §7.1 |
| Contacto con identidad propia y extensible | `CONTACT_POINT.contact_point_sk` |
| Contacto compartido entre parties (grupo familiar) | `PARTY_CONTACT_POINT` N:M con `usage_role_cd`; caso J |
| Workflow de zona gris entre owners de fuente | `MATCH_REVIEW_TASK` + `SOURCE_SYSTEM.data_steward` + regla de cierre §8.5; caso K |
| Saber de qué fuente viene cada dato | Linaje por fila (§3.14) + `PARTY_SURVIVORSHIP` + `GET /parties/{sk}/sources` |
| Deshacer un matching errado (auto o manual) | `PARTY_MERGE_HISTORY.pre_merge_snapshot` + `merge_sk` en audit + unmerge; caso L |
| Fallecidos y estado de negocio | `party_status_cd`, `death_date`; precedencia (1) de elegibilidad; caso Q |
| Menores de edad | derivado de `birth_date`; `granted_by_party_sk`; `GUARDIAN_OF`; precedencia (2) y (4) |
| Unicidad de documento entre goldens | regla dura §3.16; matching forzado |
| Base de campaña en segundos (caso financiero 3) | `GET /audiences`; caso M |
| Prevención de duplicados en origen | `match-preview`; caso N |
| SLA ARCO | `due_at` + estado derivado; caso Q |
| Cambios RDM posteriores a la carga | `rehomologate`; caso P |
| Retención y purga | `CAT_RETENTION_RULE` con política corporativa, disparada por el cierre del vínculo; `purge --dry-run` |
| Versionado del golden | `golden_version`, `completeness_score`, `rule_version` |
| Servicio persistente vs transacción puntual | regla dura §3.18; `CAT_SERVICE_KIND`; DQ rechaza vínculos transaccionales; caso R |
| Cobranza solo sobre obligación vigente | precedencia (8) de elegibilidad, `NO_ACTIVE_SERVICE`; caso S |
| Contactos de cobranza no confirmados y de terceros | `PARTY_CONTACT_POINT.confirmation_status_cd`, `origin_cd`; rol `REFERENCE`; precedencias (5) y (7); caso T |
| Una o varias finalidades por contacto y party | `PARTY_CONTACT_PREF.party_contact_sk` (una fila por finalidad, prevalece sobre el canal); precedencia (6); `PUT .../purposes`; caso T |
| Bitácora de cada carga con contadores por etapa | `staging.LOAD_BATCH`; `GET /stats`; caso G |
| Publicación de cambios del golden a consumidores | `GET /changes` (feed derivado de auditoría; contrato del tópico de producción) |

---

## 16. REFERENCIAS NORMATIVAS Y TÉCNICAS DEL DISEÑO

Ley 1581/2012 arts. 4, 5, 6, 7, 8, 14, 15, 17 · Decreto 1377/2013 arts. 9 y 12 ·
Ley 1266/2008 art. 6 · Ley 23/1981 art. 34 · Res. 1995/1999 art. 15 · Ley 2300/2023
arts. 3, 5 y 9 · Resolución CRC 7356/2024 · DIVIPOLA (DANE) · CIIU (DIAN) ·
DAMA-DMBOK2 Caps. 5 y 10 · ISO/IEC 27001:2022 A.8.15 · NIST AI RMF 1.0
(GOVERN/MAP/MEASURE) · ISO/IEC 42001:2023 cl. 6.1 · Modelo lógico de referencia
derivado de IBM InfoSphere (`DomainDataModel.xml`).

---

## 17. REPOSITORIOS Y ENTORNO DE EJECUCIÓN (código, documentos y evidencia)

Google Drive es almacenamiento, no cómputo: **el prototipo no se ejecuta en Drive**.
La división de responsabilidades es:

| Activo | Dónde vive | Por qué |
|---|---|---|
| Código, migraciones, tests, `docker-compose.yml` | Repositorio GitHub del prototipo (`mdm-rdm-prototype`), commits por fase (`feat(fase-N)`) | Versionado, trazabilidad de cada decisión, reproducible en cualquier máquina |
| Ejecución y pruebas | (a) entorno remoto de Claude Code con PostgreSQL 16 local vía `make db-local`; (b) máquina del autor con `docker compose up` | Ambos corren el mismo DDL y la misma suite `pytest` |
| Documentación viva y evidencia por fase | Carpeta de Google Drive `MDM_RDM_Prototipo/` (estructura abajo), alimentada por `make export-drive` | Es lo que el Comité, Legal y las UES consultan; no necesitan el repositorio |
| Datos | Solo sintéticos, dentro del repositorio (`app/synth/`) y en los exports de Drive | Regla 6 de §0; ningún dato personal real en ningún lugar |

**Estructura de la carpeta de Drive** (creada en F0, poblada al cierre de cada fase):

```
MDM_RDM_Prototipo/
├── 00_Especificacion/      SPEC_PROTOTIPO_MDM_RDM_PARTY (v2.0 y siguientes)
├── 01_Modelo/              Diccionario de datos (Excel: 29 tablas + campos), diagrama ER y por capas (Mermaid → PNG)
├── 02_RDM/                 Catálogos RDM (Excel: 43 catálogos, valores, EAV, homologaciones por fuente)
├── 03_Matching/            Pesos, umbrales, survivorship (Excel) y evidencia de los casos A–D, K, L, N
├── 04_Cumplimiento/        Matriz de elegibilidad (12 precedencias), consents, ARCO, RNE, retención; evidencia de E, F, H, J, M, Q, S, T
├── 05_Evidencia_Fases/     Por fase: resultado de `make test`, capturas de UI, `LOAD_BATCH` exportado
├── 06_Demo/                DEMO.md (guion), video o capturas del recorrido de los 21 casos
└── 07_Comite/              Resumen ejecutivo por fase (una página) con trazabilidad al caso financiero
```

`make export-drive` genera en `docs/drive/` los archivos Excel, PNG y Markdown de la
fase cerrada; la carga a Drive se hace desde la sesión de Claude Code (conector
Google Drive) o manualmente. Nada se sube a Drive sin haber pasado los tests de la
fase.

---

## ANEXO A — PROMPT DE ARRANQUE SUGERIDO PARA CLAUDE CODE

> Lee completo el archivo `SPEC_PROTOTIPO_MDM_RDM_PARTY.md` de este repositorio.
> Es la especificación cerrada de un prototipo funcional MDM/RDM: no rediseñes el
> modelo, impleméntalo. Ejecuta la Fase 0 (§14) y detente cuando sus criterios de
> aceptación estén en verde; muéstrame el resultado antes de pasar a la Fase 1.
> Respeta sin excepción las reglas duras de la §3 y el inventario de tablas de la
> §5 — no crees nada fuera de él. Trabaja con commits por fase y tests pytest.

---

## ANEXO B — HISTORIAL DE VERSIONES (resumen)

| Versión | Cambio esencial |
|---|---|
| 1.0 | Diseño base: 26 tablas anunciadas, 37 catálogos, pipeline de 7 etapas, matching, survivorship, consola, cumplimiento. |
| 1.1 | Conteo corregido a 25; survivorship sobre las 5 fuentes activas; excepciones a la regla de los `_cd`; 15 catálogos operativos; RNE con caso H; orden de migración de FKs cruzadas. |
| 1.2 | Homologaciones por sistema exacto; `rne-sync` limitado a COMMERCIAL; `PARTY_SEGMENT`, `CONTACT_POINT` (N:M), `MATCH_REVIEW_TASK`; linaje por fila; snapshot pre-merge; fallecidos y menores; unicidad de documento entre goldens; audiencias; `match-preview`; SLA ARCO; rehomologación; purga simulada. |
| 1.3 | `PARTY_SERVICE_ENROLLMENT` (vínculo persistente vs transacción puntual); `CAT_SERVICE` jerárquico con `service_kind`; cobranza solo con obligación vigente; retención por cierre del vínculo. |
| 1.4 | Contexto y confianza del contacto: `confirmation_status_cd`, `origin_cd`, rol `REFERENCE`; el matching solo puntúa teléfonos confirmados por el titular. |
| 1.5 | Una o varias finalidades por contacto: preferencias a nivel de contacto en `PARTY_CONTACT_PREF` (reemplaza el alcance escalar de 1.4). |
| 2.0 | Consolidación: `staging.LOAD_BATCH`, caché de elegibilidad por vínculo, `MATCH_RULE.params`, feed de cambios, índices obligatorios, paginación, ejecución sin Docker, estrategia GitHub + Drive (§17). |
