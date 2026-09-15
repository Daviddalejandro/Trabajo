# Guía de pruebas manuales · consola visual y zona gris de matching

Cómo probar el prototipo desde la interfaz, con foco en los pares de la **zona gris** (score entre
50 y 85, decisiones `PROBABLE` y `POSSIBLE`, SPEC §8.4) que requieren decisión de un steward.
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
| Escenario demo (5 fuentes SAP/SF/portal, 20 casos A–T) | `make demo` | Caso **B** (portal sin documento vs. CRM, PROBABLE) y caso **K** (SF_EC vs. SAP_CRM, dos owners); caso **C** como POSSIBLE |
| Validación SAP ECC + sistema de crédito (casos V1–V28) | `make validation-load` | **V2** (tarjeta de identidad antigua vs. cédula, PROBABLE 70), **V18** (dígito transpuesto, PROBABLE 70), **V3** (homónimos con la misma fecha, POSSIBLE 62) |

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

## 4. Probar sus propios casos de zona gris

| Vía | Cómo | Cuándo usarla |
|---|---|---|
| **match-preview** (sin persistir) | `POST /api/v1/parties/match-preview` desde `http://localhost:8000/docs` con nombre, documento, fecha, correo o teléfono → devuelve los candidatos con score, decisión sugerida y `score_detail` | Probar rápidamente "¿con quién haría match este registro?" sin cargar nada |
| **Editar un CSV y reingerir** | Copiar `backend/data/validation/credito_core.csv` (o `ecc_kna1_validacion.csv`), modificar o agregar filas (documento con un dígito cambiado, apellido con error, tarjeta de identidad vs. cédula, homónimo con la misma fecha) y ejecutar `python backend/cli.py ingest --source credito_core --file <ruta>` | Ver el par aparecer en la cola y decidirlo en la consola |
| **Corrida delta** | Mismo `ingest` con `--mode delta`: las filas sin cambio de hash quedan `UNCHANGED`; las nuevas o modificadas entran por XREF (sin matching) o por matching (nuevas) | Simular la carga nocturna del sistema fuente |

Recetas para caer en cada zona con la regla v1 de personas (documento 30, primer apellido 20,
nombre 15, fecha 15, segundo apellido 10, correo 5, teléfono 3, municipio 2):

| Objetivo | Construcción | Score aproximado |
|---|---|---|
| `AUTO_MERGE` (≥ 85) | Mismo documento y mismo apellido/nombre, aunque cambien correo o municipio | 85–100 |
| `PROBABLE` (70–84) | Documento distinto (tipo distinto, dígito transpuesto o ausente) con nombre, apellidos, fecha y correo iguales | 70 |
| `POSSIBLE` (50–69) | Documentos distintos, homónimo con la misma fecha, sin correo ni teléfono en común | 50–65 |
| `NO_MATCH` (< 50) | Solo coincide el nombre o solo la fecha | < 50 |

Umbrales en `backend/app/matching/rules.py` (`MATCH_RULE` v1); cambiar un peso y volver a
ejecutar `python backend/cli.py match` permite ver cómo se mueven los pares entre zonas.

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
