.PHONY: dev dev-backend dev-frontend test lint typecheck migrate migration

VENV = .venv/bin

dev:
	@echo "Starting development environment..."
	docker compose -f /docker/finanse/compose.yaml up -d postgres redis
	$(MAKE) dev-backend & $(MAKE) dev-frontend & wait

dev-backend:
	cd backend && $(VENV)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && $(VENV)/pytest -v
	cd frontend && npm run test

lint:
	cd backend && $(VENV)/ruff check app/ tests/
	cd frontend && npm run lint

typecheck:
	cd backend && $(VENV)/mypy app/
	cd frontend && npm run typecheck

migrate:
	cd backend && $(VENV)/alembic upgrade head

migration:
	cd backend && $(VENV)/alembic revision --autogenerate -m "$(name)"
