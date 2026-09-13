# MDM/RDM Prototype · Colsubsidio · Dominio Party
SHELL := /bin/bash
LOCAL_DB_URL ?= postgresql+psycopg://mdm@127.0.0.1:5433/mdm_prototype
export DATABASE_URL ?= $(LOCAL_DB_URL)

.PHONY: up down logs db-local db-local-stop migrate seed ingest match rebuild demo test test-backend test-frontend test-e2e api ui export-drive

up:            ## Levanta db + api + ui con Docker
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f --tail=100

db-local:      ## Alternativa sin Docker: PostgreSQL 16 local en :5433
	scripts/db_local.sh start
db-local-stop:
	scripts/db_local.sh stop

migrate:       ## Aplica migraciones Alembic (una por fase)
	cd backend && alembic upgrade head

seed:          ## F1: siembra el RDM (43 catálogos, vistas, homologaciones)
	cd backend && python cli.py rdm-seed

demo:          ## F5: levantar → migrar → sembrar → sintéticos → ingerir → rne-sync → matching
	cd backend && python cli.py demo

rebuild:       ## Reconstruye rdm + mdm + staging desde cero con sintéticos (deja B y K en la consola)
	cd backend && python cli.py rebuild --yes

test: test-backend test-frontend   ## Suite completa (backend + build de la UI)
test-backend:
	cd backend && python -m pytest -q
test-frontend:
	cd frontend && npm run build
test-e2e:      ## F4: Playwright contra API :8001 y UI :5174 sobre una base reconstruida
	scripts/e2e.sh

api:           ## API local (sin Docker)
	cd backend && uvicorn app.main:app --reload --port 8000
ui:            ## UI local (sin Docker)
	cd frontend && npm run dev

export-drive:  ## F5: genera en docs/drive/ los entregables de la fase para Google Drive
	cd backend && python cli.py export-drive
