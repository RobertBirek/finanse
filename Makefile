.PHONY: dev dev-backend dev-frontend test lint typecheck migrate

dev:
	@echo "Starting development environment..."
	docker compose -f /docker/finanse/compose.yaml up -d postgres redis
	$(MAKE) dev-backend & $(MAKE) dev-frontend & wait

dev-backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

test:
	cd backend && pytest -v
	cd frontend && npm run test

lint:
	cd backend && ruff check app/ tests/
	cd frontend && npm run lint

typecheck:
	cd backend && mypy app/
	cd frontend && npm run typecheck

migrate:
	cd backend && alembic upgrade head

migration:
	cd backend && alembic revision --autogenerate -m "$(name)"
