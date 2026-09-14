# MDM/RDM Prototype · Colsubsidio · Dominio Party
SHELL := /bin/bash
LOCAL_DB_URL ?= postgresql+psycopg://mdm@127.0.0.1:5433/mdm_prototype
export DATABASE_URL ?= $(LOCAL_DB_URL)

.PHONY: up down logs db-local db-local-stop migrate seed ingest match rebuild rne-sync purge demo test test-backend test-frontend test-e2e test-validation validation-load api ui export-drive ui-colab zip-colab

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

rne-sync:      ## F5: sincroniza el RNE simulado (solo finalidad COMMERCIAL)
	cd backend && python cli.py rne-sync
purge:         ## F5: purga simulada (nunca borra)
	cd backend && python cli.py purge --dry-run
demo:          ## F5: rebuild → rne-sync → caso Q → verificación de los 20 casos; deja B y K en la consola
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
test-validation: ## Conjunto de validación: SAP ECC + sistema de crédito, todas las funcionalidades
	cd backend && python -m pytest -q tests/test_validation_suite.py
validation-load: ## Deja el conjunto de validación (ECC + crédito) en la consola para pruebas manuales de la zona gris
	cd backend && python cli.py validation-load

api:           ## API local (sin Docker)
	cd backend && uvicorn app.main:app --reload --port 8000
ui:            ## UI local (sin Docker)
	cd frontend && npm run dev

export-drive:  ## F5: genera en docs/drive/ los entregables por carpeta de Drive (SPEC §17)
	cd backend && python cli.py export-drive --out ../docs/drive

ui-colab:      ## Compila la UI con base relativa (/api/v1) para servirla desde la API (Colab, un solo puerto)
	cd frontend && VITE_API_BASE=/api/v1 npx vite build --outDir ../colab/ui --emptyOutDir
zip-colab:     ## Empaqueta el prototipo para subirlo a Drive (MDM_RDM_Prototipo/08_Colab/mdm-rdm-prototype.zip)
	cd .. && rm -f mdm-rdm-prototype.zip && zip -qr mdm-rdm-prototype.zip mdm-rdm-prototype SPEC_PROTOTIPO_MDM_RDM_PARTY.md CLAUDE.md \
	  -x "*/node_modules/*" "*/.pgdata/*" "*/__pycache__/*" "*.pyc" "*/frontend/dist/*" "*/docs/evidence/*" "*/docs/drive/*" \
	  "*/frontend/e2e-report/*" "*/frontend/test-results/*" "*/.pytest_cache/*" "*/frontend/tsconfig.tsbuildinfo" && ls -la mdm-rdm-prototype.zip
