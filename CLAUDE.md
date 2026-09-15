# CLAUDE.md · Prototipo MDM/RDM Party (Colsubsidio)

Este archivo se carga automáticamente en cada sesión de Claude Code sobre este repositorio. Es el punto de
entrada para continuar el trabajo sin perder contexto. Léelo completo antes de actuar y luego
`mdm-rdm-prototype/docs/ESTADO_Y_CONTINUIDAD.md` (estado detallado, decisiones y pendientes).

## Contexto de trabajo (fijo)

- Contexto **"De Trabajo"**: tono corporativo C-Level, preciso, basado en evidencia. Toda recomendación
  cita su fuente: norma colombiana primero (Ley 1581/2012, Decreto 1377/2013, Ley 2300/2023, Circulares SIC),
  luego el marco internacional (DAMA-DMBOK2, ISO/IEC 27001:2022, ISO 31000:2018, ISO/IEC 42001:2023,
  NIST CSF 2.0, COBIT 2019). Nunca "buenas prácticas" sin nombrar la fuente.
- Autor y decisor: David Alejandro Ballesteros Díaz, Jefatura de Gobierno de Datos (ARC), Colsubsidio.
- Datos **exclusivamente sintéticos** (Faker es_CO, seeds fijas). Nunca datos reales de personas.
- Idioma de código, commits, docs y UI: español (identificadores técnicos en inglés cuando el modelo lo exige).

## Qué es este repositorio

Prototipo funcional in-house de Master Data Management (MDM) y Reference Data Management (RDM) para el
dominio Party (personas y organizaciones), construido por fases según `SPEC_PROTOTIPO_MDM_RDM_PARTY.md`
(v2.0, fuente de verdad funcional; sus secciones se citan como "SPEC §n").

```
SPEC_PROTOTIPO_MDM_RDM_PARTY.md   especificación v2.0 (29 tablas mdm en 8 capas, 43 catálogos rdm, 20 casos demo A–T, fases F0–F5)
mdm-rdm-prototype/
  README.md                       arranque, arquitectura, comandos, módulos de la UI, convenciones
  DEMO.md                         guion de demostración por fase (casos A–T)
  Makefile                        todos los comandos operativos (make help no existe: leer el Makefile)
  backend/  (FastAPI + SQLAlchemy 2 + Alembic + typer)   app/, alembic/versions/, cli.py, tests/, data/synth, data/validation
  frontend/ (React 18 + Vite + Tailwind v4 + Playwright)  src/pages/{Dashboard,Stewardship,AdminRdm,Vista360,Compliance}.tsx
  docs/GUIA_PRUEBAS_MANUALES.md   cómo probar desde la interfaz y trabajar la zona gris de matching
  docs/ESTADO_Y_CONTINUIDAD.md    estado actual, decisiones tomadas, pendientes, prompt de arranque
  docs/validation/README.md       conjunto de validación SAP ECC + sistema de crédito (casos V1–V25)
  docs/evidence/{f4,f5,validation}/  capturas de la UI
  docs/drive/                     entregables generados por `make export-drive` (espejo de la carpeta de Drive)
  colab/                          cuaderno de Google Colab (build_notebook.py → MDM_Prototipo_Colab.ipynb) y UI compilada con base relativa
```

## Estado (2026-09-14)

Fases F0–F5 completas y aprobadas por el autor; conjunto de validación (dos fuentes adicionales) completo;
guía de pruebas manuales publicada. Todo está en la rama `claude/pensive-ptolemy-bg3ikj` y en el
PR #1 (`Daviddalejandro/Trabajo`), limpio y sin conflictos, pendiente solo de que el autor lo fusione a `main`.
Si el PR ya fue fusionado, continuar desde `main` en una rama nueva.

## Cómo arrancar el entorno

Sin Docker (entorno remoto de Claude Code): 
```bash
cd mdm-rdm-prototype
PGDATA_LOCAL=/home/mdm/pgdata scripts/db_local.sh start   # PostgreSQL 16 en 127.0.0.1:5433 (si el clúster no existe, el script lo crea)
pip install -r backend/requirements.txt && (cd frontend && npm install)
make migrate && make seed                                  # o directamente: make demo / make validation-load
```
Con Docker (máquina del autor): `cp .env.example .env && make up` → UI `:5173`, API `:8000/docs`.
En Google Colab (sin instalar nada): cuaderno `colab/MDM_Prototipo_Colab.ipynb`, también en Drive `MDM_RDM_Prototipo/08_Colab/`;
tras cambiar la UI, `make ui-colab` y subir el cambio: el cuaderno clona la rama pública de GitHub (o un zip de Drive con `make zip-colab`).
`DATABASE_URL` por defecto: `postgresql+psycopg://mdm@127.0.0.1:5433/mdm_prototype`.

## Comandos que importan

| Objetivo | Comando |
|---|---|
| Escenario demo (20 casos A–T) en la consola | `make demo` |
| Conjunto SAP ECC + crédito (V1–V25) en la consola | `make validation-load` |
| Suite backend completa (113 pruebas, reconstruye la base) | `make test-backend` |
| Solo validación (32) | `make test-validation` |
| UI compilada + e2e Playwright (7) | `make test-frontend` · `make test-e2e` |
| Entregables para Drive | `make export-drive` |
| API / UI locales | `make api` · `cd frontend && npm run dev` |

Antes de subir cambios: `make test-backend` (o las suites afectadas) y `cd frontend && npm run build` en verde.

## Convenciones de trabajo

- Commits: `feat(fase-N): …`, `test(validacion): …`, `docs(…): …`, `fix(…): …`; mensaje en español.
- Rama de trabajo: la indicada por la sesión; nunca empujar a otra rama sin autorización explícita.
- GitHub es la fuente de verdad; Google Drive (carpeta `MDM_RDM_Prototipo`) guarda evidencia y entregables.
- Trabajar por fases y detenerse a pedir aprobación al cerrar cada una (SPEC Anexo A). Para ajustes
  puntuales fuera de una fase, entregar y reportar sin bloquear.
- Reglas duras de la SPEC §3 que el código respeta (no romperlas): RDM inmutable (deprecar y crear, §3.7),
  el RDM existe antes del MDM, unicidad de documento golden (§3.16), justificación obligatoria en toda
  decisión de stewardship (§3.12), auditoría por trigger con `app.actor` en la sesión, purga solo simulada (§10.5).
- Matching: `MATCH_RULE` v1 en `backend/app/matching/rules.py`, umbrales 85/70/50 (SPEC §8.4).
  Survivorship: `SOURCE_PRIORITY` en `backend/app/survivorship/engine.py` (SF_EC, SAP_CRM, SAP_ECC_SD,
  SAP_ECC_MM, CREDITO_CORE, WEB_PORTAL) más MOST_RECENT / MOST_COMPLETE (SPEC §9).
- Nueva fuente = adaptador en `backend/app/pipeline/sources/`, fila en `SOURCE_SYSTEMS` y homologaciones en
  `backend/app/rdm/seed_data.py`, tabla `staging.stg_<fuente>_raw` por migración Alembic, actor en
  `frontend/src/api.ts` (ACTORS) si tiene owner que decide en la consola.

## Pendientes que decide el autor

Ver la sección "Pendientes" de `docs/ESTADO_Y_CONTINUIDAD.md`. Resumen: fusionar el PR #1; probar
`docker compose up`; definir con la UES de Crédito si `CREDITO_CORE` es autoritativa para algún atributo;
validar campos Z de SAP ECC con la UES.
