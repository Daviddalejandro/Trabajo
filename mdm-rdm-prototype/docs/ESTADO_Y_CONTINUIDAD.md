# Estado y continuidad del prototipo MDM/RDM Party

Documento de traspaso: qué está hecho, qué se decidió y por qué, qué falta, y cómo retomar el trabajo en
una sesión nueva de Claude Code sin perder el contexto. Se actualiza al cierre de cada jornada de trabajo.

Última actualización: 2026-09-19 (política de decisión de matching v2 afinable · SPEC v2.1) · rama `claude/pensive-ptolemy-bg3ikj` · PR #1 de `Daviddalejandro/Trabajo`.

## 1. Estado por fase (SPEC Anexo A)

| Fase | Contenido | Estado | Evidencia |
|---|---|---|---|
| F0 | Scaffolding: Docker/PostgreSQL local, Alembic, FastAPI, CLI, React | Aprobada | `tests/test_f0_scaffolding.py` (6) |
| F1 | RDM: 43 catálogos, inmutabilidad, homologaciones, crosswalk, vistas | Aprobada | `tests/test_f1_rdm.py` (20) |
| F2 | Staging, MDM (29 tablas), pipeline de 7 etapas, DQ, XREF, delta, rehomologación | Aprobada | `tests/test_f2_pipeline.py` (17) |
| F3 | Matching, merge/unmerge con snapshot, survivorship, stewardship con owners | Aprobada | `tests/test_f3_matching.py` (14) |
| F4 | UI: Tablero, Consola de Stewardship, Admin RDM, Vista 360; e2e Playwright | Aprobada | `tests/test_f4_ui_api.py` (11), `e2e/f4.spec.ts` (6), `docs/evidence/f4/` |
| F5 | Cumplimiento: elegibilidad (12 precedencias), consentimientos, ARCO, RNE, audiencias, purga simulada, feed; `make demo`; export a Drive | Aprobada | `tests/test_f5_compliance.py` (14), `e2e/f5.spec.ts` (1), `docs/evidence/f5/` |
| Política v2 | Decisión de matching por estado de atributo, evidencia sobre lo comparable, grupos de suficiencia y vetos; versionada en `mdm.match_policy`; módulo `#/matching` (simular, publicar, recalcular); guarda §3.16 en fusiones AUTO | Implementada, pendiente de afinar con las UES | `tests/test_f6_policy.py` (12), SPEC §8.4 bis |
| Validación | Fuentes SAP ECC KNA1 + sistema de crédito (`CREDITO_CORE`), casos V1–V28 | Completa | `tests/test_validation_suite.py` (37), `docs/validation/README.md`, `docs/evidence/validation/` |
| Pruebas manuales | `make validation-load`, guía y actor `steward.credito` | Completa | `docs/GUIA_PRUEBAS_MANUALES.md` |
| Vitrina y cargas | vitrina S1–S10 en DELTA (incluida en `make demo`; `make showcase` sola), carga transaccional TX por API, modelo relacional y buckets en `#/modelo` | Completa | `tests/test_showcase.py` (4), `docs/evidence/f4/18–22`, DEMO.md «Vitrina» |
| Colab | Cuaderno autocontenido, UI servida desde la API (`UI_DIST_DIR`), zip en Drive `08_Colab` | Completa (celdas de API verificadas aquí; la instalación de PostgreSQL en Colab queda por confirmar en la primera corrida) | `colab/` |

Totales verificados: backend 136 pruebas, e2e 8, `make demo` 21/21 casos + vitrina S1–S10, `npm run build` correcto.

## 2. Decisiones tomadas (y dónde viven)

| Decisión | Razón | Dónde |
|---|---|---|
| Umbrales 85 / 70 / 50 y pesos v1 de personas (documento 30, apellido 20, nombre 15, fecha 15, segundo apellido 10, correo 5, teléfono 3, municipio 2) | SPEC §8.2–§8.4 | `backend/app/matching/rules.py`, tabla `mdm.match_rule` |
| **Política de decisión v2, afinable en caliente**: estado por atributo (`AGREE`/`PARTIAL`/`DISAGREE`/`MISSING`; lo que no viaja no suma ni resta), evidencia normalizada sobre el peso comparable y cobertura, grupos de suficiencia (G1 documental → AUTO, G2 demográfica → PROBABLE, G3 = G2 + un contacto confirmado → PROBABLE, G4 = G2 + correo y teléfono confirmados → AUTO; O1/O2 para organizaciones), umbrales solo sobre la evidencia con cobertura ≥ 60 % y piso de 50 puntos brutos, nunca AUTO sin grupo, veto por documento/NIT contradictorio en modo `REVIEW` (a revisión) o `NO_MATCH`. Versionada en `mdm.match_policy` (publica solo la Jefatura; nunca se edita una versión), `party_match.decision_basis` guarda con cuál se decidió; simular sin persistir y recalcular la cola desde `#/matching`. Los casos B, K, U y V2 se replantaron para que cada uno quede en la zona gris por un grupo distinto | Petición del autor (par #693: "era realmente un 100"): un documento ausente se trataba igual que uno contradictorio; SPEC §8.4 bis; Fellegi & Sunter (1969); Ley 1581/2012 art. 4 lit. d y art. 17; ISO/IEC 42001:2023 cl. 6.1; NIST AI RMF 1.0 MEASURE | Migración `f6_0006`, `backend/app/matching/policy.py`, `scoring.py`, `engine.py`, `api/matches.py`, `frontend/src/pages/Matching.tsx`, `tests/test_f6_policy.py` |
| Documento del mismo tipo a **un solo dígito** transpuesto o sustituido (Damerau-Levenshtein = 1) → `PARTIAL` "posible error de digitación" (+12 de 30, `reason` TYPO) en vez de contradicción; sigue vetado por defecto (`veto_typo`, el steward decide) y la Jefatura puede levantar el veto desde `#/matching`. La misma tolerancia en fecha (día/mes intercambiados +10, un dígito +8), correo (+3), celular (+2) y nombres (un carácter o JW ≥ 0,85, mitad del peso), siempre `PARTIAL` con `reason`; los grupos exigen `AGREE`, así que los errores de digitación suman evidencia pero no fusionan solos por grupo | Preguntas del autor sobre `1026256980` vs `1026259680` y sobre fechas `12/08/2020` vs `08/12/2020`; Ley 1581/2012 art. 4 lit. d y art. 17 lit. a; Fellegi & Sunter (1969): un casi-acierto en el identificador tiene mayor probabilidad de coincidencia fortuita (cédulas secuenciales) | `backend/app/matching/scoring.py`, `policy.py`, `rules.py` (`partial_typo`), `frontend/src/pages/Matching.tsx` |
| La consola muestra las **descripciones en español** del RDM (`value_name`) para todos los códigos canónicos, con el código en tooltip o en línea; endpoint `GET /rdm/labels` y componente `Cd`/`Src` en `frontend/src/labels.tsx` | Petición del autor (Vista 360 en Colab); DAMA-DMBOK2 Cap. 10: el dato de referencia lleva su descripción de negocio y la interfaz no la duplica | `backend/app/rdm/service.py` (`labels`), `frontend/src/labels.tsx`, páginas Vista360, Stewardship, Dashboard, Compliance |
| **Vista 360 por niveles de detalle** (divulgación progresiva): barra de control con Resumen · Estándar · Completo, «Mostrar históricos», Expandir/Contraer todo y navegador de capas con conteos vigentes +históricos; cada capa plegable (+ / −) a una tira de chips; bloques internos con conteo vigente/histórico y lo cerrado (nombres anteriores, roles y vínculos terminados, contactos retirados, autorizaciones revocadas, merges revertidos) detrás de «+ N históricos»; columnas técnicas, linaje, auditoría y JSON solo en Completo. Preferencias en `localStorage` del navegador | Petición del autor (UX de la Vista 360 en Colab); ISO 9241-110:2020 cl. 4.3 (autodescripción) y cl. 4.6 (controlabilidad); Nielsen, divulgación progresiva | `frontend/src/pages/Vista360.tsx` (`Block`, `Rows`, `Counts`), `components/ui.tsx` (`LayerSection` plegable, `Table.rowClass`) |
| **Vitrina S1–S10** (`app/synth/showcase.py`; `make demo` la carga al final y `make showcase` la carga sola, idempotente): casos sintéticos cargados en modo DELTA sobre la base actual, verificados y con `party_sk`/`match_sk` impresos (S6: todos los campos con un error de digitación → POSSIBLE 59, lo decide el steward; S7: el mismo caso cuando el apellido cambia de Soundex → sin bucket común, nunca se compara; S8: cobertura parcial 52 % → decisión sobre puntos brutos, POSSIBLE; S9: mismo documento con nombre y fecha distintos → fusiona por G1; S10: organizaciones homónimas con NIT distinto → PROBABLE por O2 con veto). La cola de la consola arranca con B, K, U y S1, S2, S3, S6, S8, S10; **carga transaccional** `POST /pipeline/{fuente}/record` (modo `TX` en `LOAD_BATCH`, migración `f6_0007`; `run_ingest(rows=…)`), bitácora `GET /pipeline/batches`, ejemplo nativo `GET /pipeline/{fuente}/example`; **modelo relacional** `GET /model/erd` desde `information_schema` y **buckets** `GET /matching/buckets` y `/matching/buckets/party/{sk}`; módulo `#/modelo` (Modelo relacional · Cargas y buckets) | Petición del autor: ejemplos para mostrar toda la funcionalidad, vista del modelo y de cómo entran cargas masivas y transaccionales a los buckets | `backend/app/synth/showcase.py`, `cli.py showcase`, `app/api/model.py`, `app/api/pipeline.py`, `frontend/src/pages/Modelo.tsx`, `tests/test_showcase.py` |
| Cola de la consola: el filtro «Todas»/«Todos» envía `ALL` a `GET /matches` (antes el parámetro omitido caía en el valor por defecto PROBABLE y los pares POSSIBLE de la zona gris no se listaban; el contador de la pestaña también los cuenta ahora) | Defecto detectado al montar la vitrina S1–S10 en `make demo` | `backend/app/api/matches.py`, `frontend/src/pages/Stewardship.tsx`, `tests/test_showcase.py` |
| Toda fusión `AUTO` verifica antes la unicidad de documento golden (§3.16): si el documento de uno de los dos ya es golden en un tercero, el par se fuerza a revisión en vez de fusionar (defecto detectado al permitir merges entre dos candidatos del mismo lote) | Regla dura §3.16 | `backend/app/matching/engine.py` (`golden_conflict`) |
| `SOURCE_PRIORITY` = SF_EC > SAP_CRM > SAP_ECC_SD > SAP_ECC_MM > CREDITO_CORE > WEB_PORTAL | SPEC §9; `CREDITO_CORE` entró al final del bloque SAP a falta de definición de la UES de Crédito | `backend/app/survivorship/engine.py` |
| Toda fusión de la zona gris exige justificación; pares con dos owners requieren consenso (`OWNER_CONSENSUS`); un NO_MATCH es vinculante; desacuerdo escala a Jefatura | SPEC §3.12, §8.5; Ley 1581/2012 art. 17 lit. a) | `backend/app/stewardship/decisions.py`, `merge.py` |
| Merge AUTO conserva `pre_merge_snapshot` y es reversible con unmerge | SPEC §8.7; DAMA-DMBOK2 Cap. 10 | `backend/app/stewardship/merge.py` |
| Elegibilidad por (contacto, finalidad) con 12 precedencias, persistida y recalculada tras cada evento | SPEC §10.3; Ley 2300/2023 arts. 3 y 5; Ley 1581/2012 | `backend/app/compliance/eligibility.py` |
| RNE afecta solo la finalidad COMMERCIAL; cobranza con obligación vigente sigue elegible | Ley 2300/2023 art. 5 y art. 3 | `backend/app/compliance/service.py` |
| ARCO con SLA en días hábiles (festivos Colombia 2026): ACCESS 10, otros 15 | Ley 1581/2012 arts. 14 y 15 | `backend/app/compliance/service.py` |
| Purga siempre simulada (`PURGE_SIMULATED`); excluye retención legal y vínculos activos | SPEC §10.5 | `backend/app/compliance/service.py` |
| Obligación con producto sin homologar se conserva con servicio UNKNOWN y se corrige con rehomologar | SPEC §7.2 (hallazgo de la validación) | `backend/app/pipeline/dq.py`, `rehomologate.py` |
| Banderas S/N del core de crédito con helper propio `sn()` | Hallazgo de la validación | `backend/app/pipeline/sources/credito_core.py` |
| Escrituras internas (ARCO, consentimientos, preferencias) con sistema fuente `MDM_CONSOLE` | Trazabilidad de origen | `backend/app/rdm/seed_data.py` |
| El rol del party lo declara la fuente: SAP ECC SD lo homologa desde `BPROL` (afiliado, beneficiario, proveedor, empresa afiliadora; multivalor como BUT100) y `CUSTOMER` queda reservado al cliente de crédito (`CREDITO_CORE`, UES CREDITO). La UES del rol sale de `default_business_unit` en `CAT_PARTY_ROLE` cuando la fuente no la envía | Hallazgo del autor en la Vista 360 (todo aparecía como CUSTOMER sin UES); SPEC §5.2 y §7.1 (el RDM decide, no el adaptador) | `backend/app/rdm/seed_data.py`, `backend/app/pipeline/sources/ecc_sd.py`, `load.py` (`_roles`) |
| El escenario demo incluye un caso vitrina (**U**) con las ocho capas pobladas en una sola persona: cinco fuentes, cuatro roles, los tres tipos de segmento, servicios en tres UES y relaciones persona↔organización y persona↔persona, más un par `PROBABLE` para verlo también en la Consola de Stewardship | Petición del autor: poder revisar de un vistazo que roles, segmentos y relaciones se ven donde deben verse | `backend/app/synth/generator.py` (caso U), `backend/app/demo.py`, `docs/GUIA_PRUEBAS_MANUALES.md` §3 bis |
| La búsqueda de parties normaliza el texto buscado igual que el nombre almacenado (mayúsculas, sin acentos ni puntuación) | El nombre se guarda en `full_name_normalized`; buscar "Mariana Lucía Restrepo" no devolvía nada | `backend/app/api/parties.py` (`search`) |
| La clave de homologación incluye el catálogo destino: un mismo campo fuente alimenta varios catálogos (`BPROL` → rol y sub-rol) | Defecto latente encontrado al homologar BPROL: el rol quedaba UNKNOWN porque el sub-rol pisaba la entrada | `backend/app/pipeline/homologate.py`, `app/rdm/service.py` (`homologate` admite `catalog`) |
| Vista 360 con resumen ejecutivo (elegibilidad por finalidad y razón, servicios activos por UES, DQ abiertos, pares pendientes, fuentes/merges/autorizaciones, menor/fallecido) y completitud de capas: nombres por tipo, verificación de identificadores, rol del vínculo, miembros del grupo, validez técnica del contacto, geocodificación, línea de tiempo filtrable, otorgante del consentimiento, pares pendientes enlazados a la consola | Revisión del autor contra SPEC §5.2 y §12 (2026-09-15); Ley 2300/2023 arts. 3 y 5; DAMA-DMBOK2 Cap. 10 | `backend/app/api/parties.py` (`/golden`: `summary`, `pending_matches`, `groups.members`), `frontend/src/pages/Vista360.tsx` |
| Dirección única por party (`address_hash` = línea normalizada + país + DIVIPOLA) y una sola principal; la misma dirección desde dos fuentes es una fila con el linaje de la primera. Los contactos ya eran únicos por `CONTACT_POINT` | Hallazgo de las pruebas manuales (Vista 360 mostraba la dirección repetida por fuente); Ley 1581/2012 art. 4 lit. e); DAMA-DMBOK2 Cap. 10 | Migración `f5_0005`, `backend/app/pipeline/load.py` (`_addresses`), `merge.py` |

## 3. Pendientes

Del autor (decisiones o acciones fuera del código):

1. Fusionar el PR #1 a `main`.
2. Ejecutar `docker compose up` en una máquina con Docker (aquí solo se verificó la ruta sin Docker).
3. Definir con la UES de Crédito si `CREDITO_CORE` debe ser autoritativa para calificación de riesgo u
   obligaciones. Se ajusta con `authoritative_source` en el EAV o moviendo `SOURCE_PRIORITY`, sin cambiar el modelo.
4. Validar con la UES los campos Z de SAP ECC (`ZZ_CONTRATOS` y similares son nombres sintéticos).
5. Subir a la carpeta de Drive `MDM_RDM_Prototipo` las capturas de `docs/evidence/validation/` y la guía de
   pruebas (05_Evidencia_Fases), si se quiere el espejo completo.

Del prototipo (posibles siguientes iteraciones, no comprometidas):

- Ajustes que surjan de las pruebas manuales del autor (pesos, umbrales, reglas de bloqueo, textos de la UI).
- Afinar la política de matching con las UES desde `#/matching` (simular → publicar → recalcular): decidir si G3 fusiona solo, si el veto del documento debe ser `NO_MATCH`, y calibrar con los pares ya decididos por los stewards (acuerdo con humanos que reporta la simulación).
- Extractores reales SAP (RFC/OData) en lugar de CSV, cuando la UES entregue los campos definitivos.
- SSO real en lugar del selector "Actúa como" (SPEC §2 lo deja fuera del prototipo).

## 4. Cómo retomar el trabajo en Claude Code

Tres formas, de la más simple a la más general. En todas, `CLAUDE.md` (raíz del repositorio) se carga solo
y este documento da el detalle.

**A. Reanudar esta misma sesión.** En `claude.ai/code`, abrir la sesión del prototipo (enlace en la
descripción del PR #1). Conserva la conversación completa (resumida cuando es larga) y la rama.

**B. Sesión nueva sobre el repositorio (recomendada tras fusionar el PR).** En `claude.ai/code` crear una
sesión con el repositorio `Daviddalejandro/Trabajo` y pegar el prompt de arranque de la sección 5.
Claude lee `CLAUDE.md`, este documento y el README, y continúa con las mismas convenciones.

**C. Google Colab.** Abrir `MDM_RDM_Prototipo/08_Colab/MDM_Prototipo_Colab.ipynb` desde Drive y *Ejecutar todo*:
levanta el prototipo en una máquina temporal de Google y entrega el enlace a la consola. Para pruebas manuales sin
instalar nada; los ajustes de código siguen haciéndose en Claude Code (A o B) y luego `make ui-colab && make zip-colab`.

**D. Claude Code en la máquina del autor.** Clonar el repositorio, abrir una terminal en la carpeta raíz
y ejecutar `claude`. `CLAUDE.md` se carga igual; Docker permite `make up` y las pruebas e2e locales.

## 5. Prompt de arranque para una sesión nueva

Copiar tal cual y completar la última línea:

```
Contexto: De Trabajo.
Proyecto: prototipo MDM/RDM Party de Colsubsidio en este repositorio (Daviddalejandro/Trabajo).
Lee CLAUDE.md, mdm-rdm-prototype/docs/ESTADO_Y_CONTINUIDAD.md y mdm-rdm-prototype/README.md antes de actuar.
Fases F0–F5, el conjunto de validación y la política de matching v2 (#/matching) están completos; no rehagas nada.
Mantén las convenciones: datos sintéticos, commits en español con prefijo, pruebas en verde antes de subir,
citación normativa (norma colombiana primero, luego marco internacional).
Trabaja en la rama que indique la sesión y no empujes a otra.
Hoy quiero: <describir la prueba, el hallazgo o el ajuste>.
```

Ejemplos de última línea para las pruebas de mañana:

- "Hoy quiero: cargar `make validation-load`, revisar la zona gris y ajustar el peso del correo a 8 puntos; muéstrame cómo cambian los pares."
- "Hoy quiero: reportar hallazgos de las pruebas manuales: <lista>. Corrígelos en la rama, con pruebas, y actualiza la guía."
- "Hoy quiero: agregar una fuente nueva <nombre> con estos campos <lista> siguiendo la receta de nueva fuente de CLAUDE.md."

## 6. Recursos externos

- PR #1: `https://github.com/Daviddalejandro/Trabajo/pull/1`.
- Google Drive, carpeta `MDM_RDM_Prototipo` (subcarpetas 00–07 según SPEC §17): evidencia de fases,
  matching, cumplimiento y resumen ejecutivo para comité. `make export-drive` regenera el contenido en `docs/drive/`.
- Cuaderno de Colab en Drive `MDM_RDM_Prototipo/08_Colab/MDM_Prototipo_Colab.ipynb`
  (`https://colab.research.google.com/drive/1D7nkpyOs-Mr0LCU_MhszmrNU_MDkkWT-`), copia del `colab/MDM_Prototipo_Colab.ipynb`
  del commit `a6bb8d5` (2026-09-20, demo con vitrina S1–S10 y celda 6 bis idempotente); tras cambiar el cuaderno, reemplazar la copia (subir la nueva y enviar la anterior a la papelera).
