.PHONY: dev dev-backend dev-frontend test test-secrets test-unit test-simulate build docker-up docker-down

dev:
	@echo "Starting full system (backend & frontend)..."
	@echo "Run 'make dev-backend' and 'make dev-frontend' in separate windows, or 'make docker-up'."

dev-backend:
	.venv/Scripts/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

dev-frontend:
	cd frontend && npm run dev

test: test-secrets test-unit
	@echo "All fast tests passed."

test-secrets:
	.venv/Scripts/python scripts/check_no_secrets.py

test-unit:
	.venv/Scripts/python -m pytest tests

test-simulate:
	.venv/Scripts/python scripts/simulate_call.py

build:
	cd frontend && npm run build

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

