.PHONY: help install env db-create migrate migrate-auto upgrade downgrade \
        history current heads reset run dev

# ── Default target ────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "eKYC Onboarding API — Development Commands"
	@echo "==========================================="
	@echo ""
	@echo "  Setup"
	@echo "    make install       Install Python dependencies"
	@echo "    make env           Copy .env.example → .env"
	@echo "    make db-create     Create the PostgreSQL database"
	@echo ""
	@echo "  Migrations"
	@echo "    make migrate       Run all pending migrations (upgrade head)"
	@echo "    make migrate-auto  Auto-generate migration from model changes"
	@echo "    make upgrade       Alias for migrate"
	@echo "    make downgrade     Roll back one migration step"
	@echo "    make history       Show migration history"
	@echo "    make current       Show current DB revision"
	@echo "    make heads         Show latest migration revision(s)"
	@echo "    make reset         DROP + recreate DB + run all migrations"
	@echo ""
	@echo "  Server"
	@echo "    make run           Start production server (port 8000)"
	@echo "    make dev           Start dev server with hot reload"
	@echo ""

# ── Setup ─────────────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt

env:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo ".env created — edit DATABASE_URL and SECRET_KEY before running"; \
	else \
		echo ".env already exists — skipping"; \
	fi

db-create:
	@echo "Creating database 'ekyc'..."
	psql -U postgres -c "CREATE DATABASE ekyc;" || echo "Database may already exist"

# ── Migrations ────────────────────────────────────────────────────────────────
migrate:
	alembic upgrade head

upgrade: migrate

downgrade:
	alembic downgrade -1

history:
	alembic history --verbose

current:
	alembic current

heads:
	alembic heads

# Auto-generate migration from model changes
# Usage: make migrate-auto msg="add column X to table Y"
migrate-auto:
	alembic revision --autogenerate -m "$(msg)"

# Drop everything and start fresh — DEV ONLY
reset:
	@echo "WARNING: Dropping and recreating database 'ekyc'..."
	psql -U postgres -c "DROP DATABASE IF EXISTS ekyc;"
	psql -U postgres -c "CREATE DATABASE ekyc;"
	alembic upgrade head
	@echo "Database reset complete."

# ── Server ────────────────────────────────────────────────────────────────────
run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000

dev:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
