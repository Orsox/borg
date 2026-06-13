.PHONY: dev backend frontend install test clean sandbox-image observability-up observability-down

# Install dependencies
install:
	cd backend && uv sync
	cd frontend && npm ci

# Start development servers
dev: backend frontend &

# Start backend only
backend:
	cd backend && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start frontend only
frontend:
	cd frontend && npm run dev

# Run tests
test:
	cd backend && uv run pytest -v

# Build the locked-down image agent_sandbox executes `active` skills in
sandbox-image:
	cd backend && docker build -t borg-agent-sandbox:latest -f app/agent_sandbox/Dockerfile .

# Run database migrations
migrate:
	cd backend && uv run alembic upgrade head

# Langfuse observability stack (separate compose project, see observability/).
# Note: borg's own compose declares the observability network as external —
# if you don't want to run Langfuse, a one-time `docker network create
# observability_default` is enough to keep `docker compose up` working.
observability-up:
	docker network inspect observability_default >/dev/null 2>&1 || docker network create observability_default
	docker compose -f observability/docker-compose.yml up -d

observability-down:
	docker compose -f observability/docker-compose.yml down

# Clean build artifacts
clean:
	rm -rf backend/__pycache__ backend/app/__pycache__
	rm -rf frontend/.svelte-kit frontend/node_modules/.vite
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
