# DEMO — Guion de demostración (se completa por fase)

El guion final recorre los 20 casos plantados de la especificación (§13, A–T) sobre
`make demo`. Cada fase agrega su tramo.

## Fase 0 · Plataforma

1. `make up` (o `make db-local && make migrate && make api`).
2. `curl localhost:8000/health` → `{"status":"ok","db":"ok","schemas_missing":[]}`.
3. Abrir `http://localhost:5173`: banner "Prototipo — datos sintéticos", estado del
   servicio en verde, módulos listados con su fase, leyenda de colores de las 8 capas.
4. `make test` → suite F0 en verde (salud, esquemas `rdm`/`mdm`/`staging`, `pg_trgm`,
   CLI con compuertas por fase).

## Fase 1 · RDM (pendiente)

Prueba canónica: `GET /api/v1/rdm/homologate?system=SAP_CRM&field=GESCHL&value=1` → `M`.

## Fases 2–5 (pendiente)

Casos A–T según §13.
