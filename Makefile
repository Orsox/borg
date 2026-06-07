.PHONY: dev backend frontend install test clean sandbox-image

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

# Clean build artifacts
clean:
	rm -rf backend/__pycache__ backend/app/__pycache__
	rm -rf frontend/.svelte-kit frontend/node_modules/.vite
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
