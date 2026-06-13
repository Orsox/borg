# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Install
```bash
make install          # uv sync (backend) + npm ci (frontend)
```

### Dev servers
```bash
make backend          # FastAPI on :8000, hot-reload
make frontend         # SvelteKit on :5173, proxies /api → :8000
```

### Tests (backend only)
```bash
cd backend && uv run pytest -v                    # all tests
cd backend && uv run pytest tests/test_api.py -v  # single file
cd backend && uv run pytest -k "test_name" -v     # single test
```

### Frontend type-check
```bash
cd frontend && npm run check
```

### Docker
```bash
docker compose up     # backend on :1742, frontend on :1701
```

### DB migrations (Alembic)
```bash
cd backend && uv run alembic upgrade head
```

## Architecture

**Stack:** FastAPI (async) + SQLAlchemy 2.0 + SQLite/PostgreSQL / SvelteKit 5 + Tailwind 4 + D3

### Backend — `backend/app/`

Each feature is a self-contained module with `models.py`, `schemas.py`, `service.py`, `router.py`:

| Module | Route prefix | Purpose |
|---|---|---|
| `auth/` | `/api/auth` | JWT login/refresh, user management |
| `archon_hub/` | `/api/archon` | Scan + cache Archon YAML/JSON assets from `ARCHON_PATH` |
| `archon_system/` | `/api/archon-system` | Mirror live Archon API (`:3090`) to local DB; serve cached data on failure |
| `second_brain/` | `/api/brain` | Markdown notes with `[[wiki-links]]`, full-text search, NoteLink graph |
| `second_brain/action_*` | `/api/brain/actions` | Seeded action memories (JSON store) |
| `vault/` | `/api/vault` | Read-only scanner for the Obsidian vault at `~/Memory/` |
| `task_automation/` | `/api/tasks` | APScheduler cron tasks — shell commands or Archon workflow triggers |
| `observability/` | `/api/observability` | Server-side proxy to the Langfuse public API (status, traces, trace detail) — secret key never reaches the browser |

**Startup sequence** (`main.py` lifespan): create tables → seed default user → seed action memories → ingest Archon run failures → start APScheduler.

**DB session:** `get_session()` from `database.py` is the FastAPI dependency. All ORM work is `async`. No Alembic auto-migrations; new columns are added via raw DDL at startup with exception swallowing (SQLite workaround).

**Settings:** `app/config.py` — `pydantic-settings`, reads from `backend/.env`. Key vars: `DATABASE_URL`, `SECRET_KEY`, `ARCHON_PATH`, `ARCHON_API_URL`, `CORS_ORIGINS`, `LANGFUSE_*`, `AGENT_MODE_LLM_PROXY_URL`.

### Frontend — `frontend/src/`

SvelteKit with static adapter for Docker build. Dev server proxies `/api` to `localhost:8000`.

- `lib/api/client.ts` — base `apiFetch<T>()` wrapper; reads JWT from `localStorage` key `borgos_token`
- `lib/api/*.ts` — per-module typed API clients
- `lib/stores/auth.ts` — writable auth store (`authStore`, `isAuthenticated`, `currentUser`)
- `lib/components/` — Borg design system: `BorgPanel`, `BorgButton`, `BorgInput`, `BorgBadge`, `BorgTable`, `HexLoader`, `BorgNav`, `BorgStatusBar`, `BorgToast`
- `routes/` — one directory per page; `brain/graph/` uses D3 force simulation for the note link graph

### Archon integration

Two distinct Archon surfaces:
1. **Archon Hub** (`archon_hub/`) — reads local filesystem at `ARCHON_PATH` for static assets (workflow YAML, skill files)
2. **Archon System** (`archon_system/`) — calls live Archon REST API at `ARCHON_API_URL` (:3090) and mirrors results to DB for offline resilience; uses `ArchonClient` with `ArchonUnavailable` exception for graceful degradation

### Observability (Langfuse)

Optional, **off by default** — the app must behave identically without it (tests never touch Langfuse).

- `app/shared/tracing.py` — no-op-safe wrapper around the Langfuse SDK: `trace_span(...)` / `generation(...)` context managers yield a no-op when `LANGFUSE_ENABLED=false` or keys are missing. Convention: `session_id` = run_id, `user_id` = persona (`locutus`/`seven`), `tags` = surface.
- Instrumented surfaces: persona chats (`discord_bot/service.py` + the single LLM chokepoint `discord_bot/llm.py::LlmClient.chat`), Agent Mode runs and skill executions (`agent_sandbox/service.py`), dreaming cycles (`dreaming/service.py`).
- Langfuse v3 stack is a **separate compose project** in `observability/` (`make observability-up`, UI on :3052, headless init creates project `borg` with the keys from `observability/.env`). Borg's compose declares the `observability_default` network as external — without the stack, `docker network create observability_default` once keeps `docker compose up` working.
- Agent Mode interception: pi inside the sandbox talks to LM Studio directly, so its calls are invisible to the backend. When `AGENT_MODE_LLM_PROXY_URL` is set (e.g. `http://litellm:4000/v1`), pi's generated `models.json` points at the `litellm` proxy service (config: `observability/litellm-config.yaml`), which logs every request to Langfuse. Empty = direct to LM Studio, today's behavior.
- Privacy note: traces contain full prompts/outputs, including recalled memories in system prompts — local-only by design.
- Borg-themed trace browser at `/observability` in the frontend (`routes/observability/`, client `lib/api/observability.ts`): filter by surface tag/persona, trace detail with observation tree, deep links into the Langfuse UI via `LANGFUSE_UI_URL`. Shows a setup hint when unconfigured.

### Vault integration

`vault/` module scans `~/Memory/` (Obsidian vault) using `python-frontmatter`. Parses YAML frontmatter + extracts `[[wiki-links]]` for graph rendering. Read-only — never writes to vault.

### Tests

Tests use an in-memory SQLite DB, created fresh per test (see `conftest.py` `setup_db` autouse fixture — drops/recreates all tables). `asyncio_mode = "auto"` in `pyproject.toml`; no `@pytest.mark.asyncio` needed.

## Default credentials

- Username: `borg`
- Password: `borgborg` (override via `INITIAL_PASSWORD` env var)
