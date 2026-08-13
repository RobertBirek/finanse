.PHONY: dev dev-backend dev-frontend test test-db-up test-integration lint typecheck migrate migration

VENV = .venv/bin
TEST_COMPOSE = /docker/finanse/compose.test.yaml
TEST_DATABASE_URL = postgresql+asyncpg://finanse:finanse@127.0.0.1:55432/finanse_test

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

test-db-up:
	docker compose -f $(TEST_COMPOSE) up -d --wait postgres-test

test-integration:
	@trap 'exit_code=$$?; trap - EXIT INT TERM; docker compose -f "$(TEST_COMPOSE)" down; exit $$exit_code' EXIT INT TERM; \
	docker compose -f "$(TEST_COMPOSE)" up -d --wait postgres-test; \
	exit_code=$$?; \
	if [ $$exit_code -ne 0 ]; then exit $$exit_code; fi; \
	(cd backend && TEST_DATABASE_URL="$(TEST_DATABASE_URL)" $(VENV)/pytest -v -m integration)

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
