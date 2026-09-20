# Guía de pruebas manuales · consola visual y zona gris de matching

Cómo probar el prototipo desde la interfaz, con foco en los pares de la **zona gris** (decisiones
`PROBABLE` y `POSSIBLE`, SPEC §8.4 y §8.4 bis) que requieren decisión de un steward, y en la
**política de matching** afinable desde `#/matching`.
Todo con datos sintéticos.

## 1. Arranque (una vez)

| Opción | Comandos | URL |
|---|---|---|
| A · Docker | `cp .env.example .env` → `make up` | UI `http://localhost:5173` · API `http://localhost:8000/docs` |
| B · Sin Docker | `make db-local` → `pip install -r backend/requirements.txt` → `make migrate` → `make api` (terminal 1) → `cd frontend && npm install && npm run dev` (terminal 2) | UI `http://localhost:5173` · API `http://localhost:8000/docs` |
| C · Google Colab | Abrir `MDM_RDM_Prototipo/08_Colab/MDM_Prototipo_Colab.ipynb` en Drive → *Ejecutar todo* → enlace de la sección 5 | Consola y Swagger en el enlace que imprime el cuaderno |

Verificación: `curl localhost:8000/health` responde `{"status":"ok","db":"ok","schemas_missing":[]}`
y el tablero (`#/`) muestra el estado del servicio en verde.

## 2. Elegir el conjunto de datos

| Conjunto | Comando | Qué deja en la cola de stewardship |
|---|---|---|
| Escenario demo (5 fuentes SAP/SF/portal, 21 casos A–U) | `make demo` | Caso **B** (portal re-registrado sin documento y con correo nuevo: PROBABLE por G3), caso **K** (SF_EC vs. SAP_CRM, pasaporte vs. cédula, dos owners: PROBABLE por G2) y caso **U** (vitrina 360: PROBABLE por G3); caso **C** como POSSIBLE |
| Validación SAP ECC + sistema de crédito (casos V1–V28) | `make validation-load` | **V2** (tarjeta de identidad antigua vs. cédula: tipos no comparables, PROBABLE por G3), **V18** (dígito transpuesto: el veto del documento baja G4 a revisión, PROBABLE), **V3** (homónimos con la misma fecha y documentos distintos, PROBABLE por G2 con evidencia 62) |

Ambos comandos parten de cero (el segundo conserva el RDM) y aplican el matching; al terminar
imprimen el resumen de pares por decisión. Se pueden alternar tantas veces como se quiera.

## 3. Trabajar la zona gris en la Consola de Stewardship (`#/stewardship`)

1. **Actúa como** → `steward.mdm` (rol STEWARD). Pestaña **Cola de casos**, filtros
   `PROBABLE` / `PENDING` (o `POSSIBLE`, o *Todas*).
2. Abrir un par. La pantalla muestra, de arriba abajo:
   - cabecera con `total_score`, decisión y estado;
   - los dos parties lado a lado (documento, fuentes, fecha de nacimiento) con enlace a su Vista 360;
   - **Desglose por atributo (`score_detail`)**: barra de puntos por atributo, valores A y B con la
     diferencia resaltada y el algoritmo aplicado (EXACT, JARO_WINKLER, SOUNDEX_ES, EXACT_OR_1Y);
   - **Evidencia A / B**: roles, segmentos, servicios, relaciones y contactos con su confirmación;
   - **Fuentes y owners involucrados** (owner y steward de cada sistema);
   - **Decisión del steward** con justificación obligatoria (regla dura 3.12).
3. Decidir:
   - **Fusionar**: si el par tiene una sola fuente/owner, fusiona de inmediato (`STEWARD`);
     si tiene dos owners, el botón dice **Fusionar (pedir a owners)** y crea una
     `MATCH_REVIEW_TASK` por owner (§8.5). Cambiar **Actúa como** a cada owner
     (`steward.sd`, `steward.credito`, `steward.crm`, `steward.sfec`) y decidir en
     **Tareas por owner**: dos MERGE → `OWNER_CONSENSUS`; un NO_MATCH cierra el par;
     decisiones divididas escalan a `jefatura.gd` (rol JEFATURA, `MANUAL_OVERRIDE`).
   - **No es la misma persona**: `NO_MATCH` vinculante, el par no vuelve a proponerse.
   - **Escalar**: deja el par en manos de Jefatura.
4. En la **Vista 360** de cualquiera de los dos parties, la cabecera resume el estado antes de decidir:
   elegibilidad por finalidad con la razón de exclusión, servicios activos por UES, hallazgos DQ abiertos y
   los **pares de matching pendientes** del party (capa 7, con enlace al detalle en la consola). Tras el merge,
   el sobreviviente muestra el par resuelto y el absorbido queda `MERGED`.
5. Revisar el resultado en **Historial de merges** (`pre_merge_snapshot` por tabla, auditoría por
   `merge_sk`) y, si hace falta, **Deshacer merge** con razón. En **Vista 360** del golden
   sobreviviente se ve la fuente ganadora por campo (survivorship §9).

Capturas de referencia: [`docs/evidence/validation/`](evidence/validation/README.md) y
[`docs/evidence/f4/`](evidence/f4/README.md).

## 3 ter. Vitrina S1–S10: digitación muy parecida, homónimo, tres documentos, NIT, todo mal digitado, cobertura parcial, G1, homónimas

`make demo` deja cargada la vitrina (diez casos en modo DELTA) e imprime `party_sk` y `match_sk`; `make showcase` la carga sola sobre la base actual (demo o validación) y es idempotente. La cola de `#/stewardship` arranca así con B, K, U, S1, S2, S3, S6, S8 y S10:

| Caso | Ir a | Qué mirar |
|---|---|---|
| S1 cédula con dígito transpuesto | `#/stewardship` → par PROBABLE (evidencia 82) | Fila `document` en amarillo «parcial · posible error de digitación»; base de la decisión: G4 satisfecho + veto de digitación. Con «Vetar también el posible error de digitación» apagado en `#/matching`, **Simular** lo muestra pasando a AUTO_MERGE |
| S2 sin documento, nombre/fecha/correo mal digitados | `#/stewardship` → par PROBABLE (evidencia 90 sobre cobertura 70) | `birth_date` «día y mes intercambiados», `email` «posible error de digitación», `document` «sin dato»; decidido por umbral de evidencia, sin grupo |
| S3 homónimo | `#/stewardship` → filtro Posible | `document` «contradice»; evidencia 57 |
| S4 tres identificadores | `#/party/<sk>` capa 3 · Identity | CC golden verificada + pasaporte + TI, cada uno con su fuente; capa 7 con tres merges AUTO |
| S5 NIT con razón social mal digitada | `#/party/<sk>` | Organización con dos fuentes (SD y MM) y survivorship de la razón social |
| S6 todos los campos con un error de digitación | `#/stewardship` → filtro **Posible** (evidencia 59) | Todas las filas en amarillo salvo el nombre (Jaro-Winkler lo absorbe): documento, fecha, correo y celular «digitación», apellidos «parecido»; base de la decisión: umbral de evidencia, ningún grupo. Para que un caso así suba a PROBABLE hay que subir los puntos parciales en `MATCH_RULE` (`partial_typo`, `partial_near`) o bajar el umbral en `#/matching`; para que fusione solo haría falta apagar `auto_requires_group`, lo que no se recomienda |
| S7 igual que S6 pero el apellido cambia de Soundex | `#/modelo` → Cargas y buckets → explorador con el `party_sk` | 0 vecinos en todas las claves: el registro nunca se comparó. Límite del bloqueo exacto |
| S8 cobertura parcial: solo nombres, apellidos y correo | `#/stewardship` → filtro **Posible** (evidencia 100 sobre cobertura 52) | `document`, `birth_date` y `phone` «sin dato»; base de la decisión «umbral sobre puntos brutos» (52) porque la cobertura no llega al mínimo (60). Subir `min_raw_points` por encima de 52 en `#/matching` lo vuelve NO_MATCH; bajar el umbral «probable» por debajo de 52 lo sube a PROBABLE (simular antes de publicar) |
| S9 mismo documento y apellido, nombre y fecha distintos | `#/party/<sk>` capa 7 (merges) | Fusión AUTO con justificación `group:G1`; `first_name` contradice y `birth_date` contradice pero G1 (documento + primer apellido) basta. Para exigir la fecha, editar el grupo G1 en `#/matching` y simular |
| S10 organizaciones homónimas, NIT distinto | `#/stewardship` → par PROBABLE de organización | `nit` «contradice» (veto), `legal_name` y `city` coinciden: base `group:O2` con `nit` en los vetos, por eso nunca pasa de PROBABLE; se decide con justificación como cualquier par |

Y en `#/modelo` → **Cargas y buckets**: los lotes DELTA de la vitrina con sus etapas, el simulador de carga transaccional,
la explicación visual «archivador con cajones» (recorra los cinco pasos con «Siguiente» y cambie de escenario: en S7 ningún
cajón coincide y el registro no se compara con nadie) y el explorador de buckets (pruebe con el `party_sk` de S4 o de S7: el
explorador añade el escenario «Party real» a la explicación).

## 3 bis. Caso U · vitrina 360: una persona con todas las capas pobladas

Tras `make demo`, el caso **U** deja en la base una sola persona sintética con todo lo que el
modelo Party sabe representar. Sirve para revisar de un vistazo que roles, segmentos y relaciones
se ven donde deben verse.

**Cómo encontrarla:** `#/party` → buscar **`Mariana Lucía Restrepo Vanegas`** (también funciona
sin tildes, por documento o por el correo `mariana.restrepo.vitrina@ejemplo.test`). La fila
`U` de la tabla que imprime `make demo` trae su `party_sk`.

Al entrar, la barra **Nivel de detalle** está en *Estándar*: cada capa abierta con lo vigente y lo
histórico detrás de «+ N históricos» (por ejemplo, el segmento Categoría A cerrado). *Resumen* pliega las
8 capas a su tira de chips (cabe en una pantalla; el «+» de cada capa la abre sola); *Completo* muestra
históricos, columnas técnicas, linaje, auditoría y JSON. El navegador de capas de la barra salta a la capa
y la abre.

| Capa de la Vista 360 | Qué debe verse |
|---|---|
| 1 · Sources | Cinco sistemas: SF_EC, SAP_CRM, SAP_ECC_SD, SAP_ECC_MM y WEB_PORTAL, con su ID externo y linaje por tabla |
| 2 · Core | Fuente ganadora por campo: SF_EC por `SOURCE_PRIORITY` en nombres, fecha y documento; correo y teléfono por `MOST_RECENT` |
| 3 · Identity | Cédula verificada y el nombre legal aportado por cada una de las cinco fuentes |
| 4 · Roles y Relaciones | **Roles por UES**: EMPLOYEE/EMPLOYEE_PERMANENT (SUBSIDIO, SF_EC), AFFILIATE/AFFILIATE_WORKER (SUBSIDIO, SD y CRM), VENDOR/VENDOR_SERVICES (SAP_ECC_MM), DIGITAL_USER/DIGITAL_REGISTERED (WEB_PORTAL). **Servicios** en tres UES: CREDITO_SOCIAL, SALUD_EPS y CUOTA_MONETARIA. **Segmentos** en los tres tipos: FINANCIAL_RISK=LOW, AFFILIATION=A y COMMERCIAL=PREMIUM. **Relaciones**: `EMPLOYEE_OF` → Textiles del Norte S.A.S., `LEGAL_REP_OF` y `SHAREHOLDER_OF` → Inversiones Vanegas Ltda., `SPOUSE_OF` ↔ Andrés Felipe Cardona Bermúdez, `PARENT_OF`/`CHILD_OF` y `BENEFICIARY_OF` ← Sofía Cardona Restrepo, más el grupo familiar con sus miembros |
| 5 · Contactability | Correo propio confirmado y tres teléfonos por rol de uso y origen (declarado, aportado en cobranza, referencia de tercero) con sus finalidades por contacto y por canal |
| 6 · Governance | Un hallazgo DQ abierto: la estadía de hotel del registro de SD no es vinculable como servicio (regla dura §3.18) |
| 7 · Golden Record | Cuatro merges AUTO vigentes y el survivorship campo a campo; el par pendiente enlaza a la consola |
| 8 · Consents | DATA_PROCESSING (SF_EC) y COMMERCIAL (SAP_CRM), ambos GRANTED |

**En la Consola de Stewardship** el mismo caso deja un par `PROBABLE` (evidencia ≈ 93 % sobre cobertura 70 %, grupo G3): el segundo
registro del portal no trae documento, así que `document` puntúa 0/30. Al abrirlo, la tarjeta
**Evidencia A · roles, segmentos, relaciones y contactos** muestra los cuatro roles, los tres
segmentos, los servicios y las relaciones de la persona consolidada, y la **Evidencia B**
el registro pobre del portal: es la comparación que sustenta la decisión.

Capturas: [`09_stewardship_vitrina_evidencia.png`](evidence/f4/README.md),
[`10_vista360_vitrina_capa4.png`](evidence/f4/README.md) y
[`11_vista360_vitrina_resumen.png`](evidence/f4/README.md).

## 3 quater. Consola RDM: construir un catálogo de principio a fin

`#/rdm-consola` recorre las cinco capas del RDM en el orden en que se construyen (regla dura §3.1). Para una demostración
de diez minutos:

| Paso | Dónde | Qué mirar |
|---|---|---|
| Recorrido guiado → «Ejecutar el recorrido» | tarjeta bajo las estaciones | Ocho pasos «hecho» (o «ya existía» si se repite): dominio `EXPERIENCIA`, catálogo `CAT_CANAL_PREFERIDO`, tres campos personalizados, cuatro valores más uno rechazado por el diccionario, sistema `APP_MOVIL`, integración y homologaciones, deprecación de `SMS` con versionado de `sms → SMS_RCS`, auditoría |
| 1 · Dominios | «Nuevo dominio» | Código en MAYÚSCULAS; queda auditado con el actor de «Actúa como» |
| 2 · Catálogos | «Nuevo catálogo» | El dominio debe existir antes; el código empieza por `CAT_`; fuente oficial y jerarquía |
| 3 · Campos personalizados | seleccionar `CAT_ID_TYPE` | El diccionario inferido de la semilla: `validation_regex` (expresión regular), `has_check_digit` (sí/no), `applies_to` (código). Declarar un campo obligatorio sobre valores que no lo tienen se rechaza |
| 4 · Listas de referencia | `CAT_CANAL_PREFERIDO`, «incluir deprecados» | Campos como columnas, `SMS` deprecado, «atributos» corrige un atributo (el código y el nombre siguen inmutables: la base rechaza el cambio) |
| 5 · Sistemas fuente | «Registrar sistema fuente» | Sin sistema registrado no se puede declarar integración ni homologar (regla dura §3.4) |
| 6 · Integraciones y homologación | «Nueva homologación» sobre un valor fuente ya homologado | La anterior se cierra y la nueva queda vigente; «cerrar» deja el valor fuente en UNKNOWN; la prueba canónica lo confirma |
| 7 · Ciclo de vida | «Ver versiones» con `APP_MOVIL / canal_pref / CAT_CANAL_PREFERIDO / sms` | Dos versiones con vigencia; auditoría por capa con antes y después; rehomologar con conteo previo |
| Flujo con contexto | 2 · Catálogos → «valores» en `CAT_CANAL_PREFERIDO` → «homologar este catálogo →» | La barra «Trabajando sobre» y la URL (`?catalogo=…`) conservan el catálogo; Homologación llega filtrada (solo `APP_MOVIL`) y con los formularios prefijados; el pie «Siguiente: …» está contextualizado en cada estación |
| Desvío con retorno | en 6 · Homologación, selector de sistema → «＋ registrar una fuente nueva…» | Va a 5 · Sistemas fuente con el aviso ámbar de desvío; «Registrar y volver a homologar» regresa a Homologación con la fuente seleccionada (`?catalogo=…&sistema=…`) y un aviso verde; «atrás» del navegador respeta el recorrido |

## 4. Probar sus propios casos de zona gris

| Vía | Cómo | Cuándo usarla |
|---|---|---|
| **match-preview** (sin persistir) | `POST /api/v1/parties/match-preview` desde `http://localhost:8000/docs` con nombre, documento, fecha, correo o teléfono → devuelve los candidatos con score, decisión sugerida y `score_detail` | Probar rápidamente "¿con quién haría match este registro?" sin cargar nada |
| **Editar un CSV y reingerir** | Copiar `backend/data/validation/credito_core.csv` (o `ecc_kna1_validacion.csv`), modificar o agregar filas (documento con un dígito cambiado, apellido con error, tarjeta de identidad vs. cédula, homónimo con la misma fecha) y ejecutar `python backend/cli.py ingest --source credito_core --file <ruta>` | Ver el par aparecer en la cola y decidirlo en la consola |
| **Corrida delta** | Mismo `ingest` con `--mode delta`: las filas sin cambio de hash quedan `UNCHANGED`; las nuevas o modificadas entran por XREF (sin matching) o por matching (nuevas) | Simular la carga nocturna del sistema fuente |

Recetas para caer en cada zona con los pesos v1 de personas (documento 30, primer apellido 20,
nombre 15, fecha 15, segundo apellido 10, correo 5, teléfono 3, municipio 2) y la política v2
inicial (SPEC §8.4 bis). Lo que no viaja en uno de los dos registros queda **sin dato**: no suma ni
resta, y la **evidencia** se mide sobre lo comparable (la **cobertura** dice cuánto se pudo comparar).

| Objetivo | Construcción | Qué lo decide |
|---|---|---|
| `AUTO_MERGE` | Mismo documento (tipo y número) y mismo primer apellido, aunque cambien correo o municipio | grupo G1 |
| `AUTO_MERGE` sin documento | Sin documento en uno de los dos, con nombre, dos apellidos, fecha, correo **y** celular confirmado iguales | grupo G4 |
| `PROBABLE` | Sin documento comparable (ausente o cédula vs. pasaporte) con nombre, apellidos y fecha iguales, y como mucho un contacto en común | grupos G2 / G3 |
| `PROBABLE` con posible error de digitación | Mismo tipo y números a un solo dígito transpuesto o sustituido (`1026256980` vs `1026259680`: parcial, +12) y todo lo demás igual: sigue vetado por defecto; desmarcar "Vetar también el posible error de digitación" lo convierte en `AUTO_MERGE` por G4 | G4 + `veto_typo` |
| `PROBABLE` con documento contradictorio | Mismo tipo con distinto número (dos o más dígitos) y todo lo demás igual: el veto impide fusionar solo | G4 + veto en modo `REVIEW` |
| `PROBABLE` por errores de digitación | Sin documento comparable; nombre, correo o celular a un carácter, fecha con día y mes intercambiados (`12/08` vs `08/12`): parciales que suman evidencia 70–84 sin satisfacer ningún grupo | vía de umbrales (nunca AUTO sin grupo) |
| `POSSIBLE` | Homónimo con fecha a menos de un año (parcial) o segundo apellido distinto: ningún grupo, evidencia 50–69 | vía de umbrales |
| `NO_MATCH` | Solo coincide el nombre o solo la fecha (menos de 50 puntos brutos); o documento contradictorio con el veto en modo `NO_MATCH` | piso de puntos / veto |

Para mover un par de zona no hace falta tocar código: en `#/matching` se cambia la decisión de un grupo,
el modo del veto o los umbrales, **Simular** muestra qué pares cambiarían (y el acuerdo con lo que ya
decidieron los stewards), **Publicar** crea la versión siguiente (solo `jefatura.gd`) y **Recalcular
pendientes** la aplica a la cola. Los pesos siguen en `backend/app/matching/rules.py` (`MATCH_RULE` v1).

## 5. Verificaciones rápidas de cierre

- `GET /api/v1/stats` (o el tablero): pares por decisión, goldens y candidatos.
- En **Vista 360**, capa 4: el rol que aporta SAP ECC SD sale de `BPROL` (AFFILIATE con sub-rol trabajador o
  beneficiario, VENDOR, AFFILIATING_COMPANY) con la UES SUBSIDIO cuando aplica; `CUSTOMER` aparece solo desde
  `CREDITO_CORE` con la UES CREDITO. Un registro con `BPROL` multivalor produce dos filas de rol.
- En la misma capa se ven los **segmentos por tipo** (AFFILIATION desde la categoría de SD y FINANCIAL_RISK desde
  el riesgo de SD y la calificación de crédito) y las **relaciones party a party** (beneficiario del titular en SD,
  codeudor en crédito, con su inversa).
- En **Vista 360** de un golden con varias fuentes, cada correo, teléfono y dirección aparece una sola vez
  (`CONTACT_POINT` único por canal y hash; `PARTY_ADDRESS` único por party y `address_hash`) y hay una sola
  dirección principal (★). La columna *Fuente* muestra la primera fuente que aportó el dato.
- `GET /api/v1/matches?decision=PROBABLE&status=PENDING` debe quedar vacío al terminar la sesión
  de stewardship; los resueltos aparecen con `match_status=RESOLVED`.
- `make test-validation` y `make demo` devuelven todo en verde: dejan la base en un estado conocido
  para la siguiente sesión.

## Base normativa de la actividad

- Ley 1581/2012 art. 4 lit. e) (veracidad y calidad) y art. 17 lit. a) (deber de garantizar el
  ejercicio del habeas data): la decisión de fusionar dos identidades exige evidencia y trazabilidad;
  por eso la justificación es obligatoria y queda en `PARTY_MERGE_HISTORY` y `PARTY_AUDIT_LOG`.
- DAMA-DMBOK2 Cap. 10 (Reference and Master Data), actividad "Manage identity resolution and
  match rules": umbrales explícitos, revisión humana en la zona gris y capacidad de unmerge.
- ISO/IEC 27001:2022 Anexo A 8.15 (registro de eventos) para la auditoría de decisiones por actor.
