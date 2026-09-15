# Estado y continuidad del prototipo MDM/RDM Party

Documento de traspaso: qué está hecho, qué se decidió y por qué, qué falta, y cómo retomar el trabajo en
una sesión nueva de Claude Code sin perder el contexto. Se actualiza al cierre de cada jornada de trabajo.

Última actualización: 2026-09-15 (direcciones únicas, Vista 360 completa) · rama `claude/pensive-ptolemy-bg3ikj` · PR #1 de `Daviddalejandro/Trabajo`.

## 1. Estado por fase (SPEC Anexo A)

| Fase | Contenido | Estado | Evidencia |
|---|---|---|---|
| F0 | Scaffolding: Docker/PostgreSQL local, Alembic, FastAPI, CLI, React | Aprobada | `tests/test_f0_scaffolding.py` (6) |
| F1 | RDM: 43 catálogos, inmutabilidad, homologaciones, crosswalk, vistas | Aprobada | `tests/test_f1_rdm.py` (19) |
| F2 | Staging, MDM (29 tablas), pipeline de 7 etapas, DQ, XREF, delta, rehomologación | Aprobada | `tests/test_f2_pipeline.py` (17) |
| F3 | Matching, merge/unmerge con snapshot, survivorship, stewardship con owners | Aprobada | `tests/test_f3_matching.py` (14) |
| F4 | UI: Tablero, Consola de Stewardship, Admin RDM, Vista 360; e2e Playwright | Aprobada | `tests/test_f4_ui_api.py` (9), `e2e/f4.spec.ts` (6), `docs/evidence/f4/` |
| F5 | Cumplimiento: elegibilidad (12 precedencias), consentimientos, ARCO, RNE, audiencias, purga simulada, feed; `make demo`; export a Drive | Aprobada | `tests/test_f5_compliance.py` (14), `e2e/f5.spec.ts` (1), `docs/evidence/f5/` |
| Validación | Fuentes SAP ECC KNA1 + sistema de crédito (`CREDITO_CORE`), casos V1–V25 | Completa | `tests/test_validation_suite.py` (32), `docs/validation/README.md`, `docs/evidence/validation/` |
| Pruebas manuales | `make validation-load`, guía y actor `steward.credito` | Completa | `docs/GUIA_PRUEBAS_MANUALES.md` |
| Colab | Cuaderno autocontenido, UI servida desde la API (`UI_DIST_DIR`), zip en Drive `08_Colab` | Completa (celdas de API verificadas aquí; la instalación de PostgreSQL en Colab queda por confirmar en la primera corrida) | `colab/` |

Totales verificados: backend 113 pruebas, e2e 7, `make demo` 20/20 casos, `npm run build` correcto.

## 2. Decisiones tomadas (y dónde viven)

| Decisión | Razón | Dónde |
|---|---|---|
| Umbrales 85 / 70 / 50 y pesos v1 de personas (documento 30, apellido 20, nombre 15, fecha 15, segundo apellido 10, correo 5, teléfono 3, municipio 2) | SPEC §8.2–§8.4 | `backend/app/matching/rules.py`, tabla `mdm.match_rule` |
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
Fases F0–F5 y el conjunto de validación están completos y aprobados; no rehagas nada.
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
